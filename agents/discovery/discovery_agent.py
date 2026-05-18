import asyncio
from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from sqlalchemy import select, update

from shared.config import settings
from shared.models import TokenCandidate, TokenStatus, PatternType, get_session
from shared.redis_bus import bus, Channel

from .exchange_scanner import ExchangeScanner
from .pre_screener import PreScreener
from .schemas import TokenData, DiscoveryResult

log = structlog.get_logger(__name__)

# ── Prometheus metrics ────────────────────────────────────────────────────────
TOKENS_SCANNED = Counter("discovery_tokens_scanned_total", "Total tokens scanned")
CANDIDATES_FOUND = Gauge("discovery_candidates_found", "Active candidates in watchlist")
CANDIDATES_REMOVED = Counter("discovery_candidates_removed_total", "Tokens removed from watchlist")
RUN_DURATION = Histogram("discovery_run_duration_seconds", "Time for a full discovery run")


class DiscoveryAgent:
    def __init__(self) -> None:
        self._scanner = ExchangeScanner()
        self._screener = PreScreener()
        self._scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        await bus.connect()

        start_http_server(9100)
        log.info("discovery_agent.prometheus_started", port=9100)

        # Schedule daily run
        self._scheduler.add_job(
            self.run,
            trigger="cron",
            hour=settings.discovery_schedule_hour,
            minute=0,
            id="discovery_daily",
            replace_existing=True,
        )
        self._scheduler.start()
        log.info(
            "discovery_agent.scheduled",
            hour=settings.discovery_schedule_hour,
        )

        # Listen for manual triggers from Dashboard
        await bus.subscribe("channel:control:discovery:run", self._handle_manual_trigger)
        await bus.start_listening()

        # Run immediately on startup
        await self.run()

        # Keep alive
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self._scheduler.shutdown(wait=False)
            await bus.disconnect()

    async def _handle_manual_trigger(self, payload: dict) -> None:
        source = payload.get("source", "unknown")
        log.info("discovery_agent.manual_trigger", source=source)
        await self.run()

    @RUN_DURATION.time()
    async def run(self) -> DiscoveryResult:
        log.info("discovery_agent.run_started")
        result = DiscoveryResult(run_at=datetime.now(timezone.utc))

        # 1. Scan exchanges
        all_tokens: list[TokenData] = await self._scanner.scan()
        result.tokens_scanned = len(all_tokens)
        TOKENS_SCANNED.inc(len(all_tokens))

        # 2. Load existing active symbols to detect removals
        async with get_session() as session:
            existing_rows = (
                await session.execute(
                    select(TokenCandidate.symbol, TokenCandidate.id)
                    .where(TokenCandidate.status == TokenStatus.active)
                )
            ).all()
        existing_symbols = {row.symbol: row.id for row in existing_rows}

        # 3. Load blacklist (symbols previously removed — soft blacklist)
        async with get_session() as session:
            removed_rows = (
                await session.execute(
                    select(TokenCandidate.symbol)
                    .where(TokenCandidate.status == TokenStatus.removed)
                )
            ).scalars().all()
        self._screener.blacklist = set(removed_rows)

        # 4. Pre-screen
        passing, rejected = self._screener.screen(all_tokens)
        passing_symbols = {t.symbol for t in passing}

        # 4b. Enriquecer tokens passing con contract address + chain
        contracts = await self._scanner.get_eth_contracts(passing)
        if contracts:
            passing = [
                t.model_copy(update={
                    "eth_contract": contracts[t.symbol][0],
                    "chain": contracts[t.symbol][1],
                }) if t.symbol in contracts else t
                for t in passing
            ]

        # 5. Upsert candidates into DB
        async with get_session() as session:
            for token in passing:
                if token.symbol in existing_symbols:
                    await session.execute(
                        update(TokenCandidate)
                        .where(TokenCandidate.symbol == token.symbol)
                        .values(
                            last_checked=datetime.now(timezone.utc),
                            contract_address=token.eth_contract,
                            chain=token.chain,
                        )
                    )
                else:
                    # New candidate
                    session.add(TokenCandidate(
                        symbol=token.symbol,
                        exchange=token.exchange,
                        status=TokenStatus.active,
                        pattern_type=PatternType.unknown,
                        inflow_usd=0.0,
                        contract_address=token.eth_contract,
                        chain=token.chain,
                        notes=f"mcap={token.market_cap_usd:.0f} vol_ratio={token.volume_to_mcap_ratio:.3f}"
                        if token.market_cap_usd and token.volume_to_mcap_ratio else None,
                    ))
                    log.info("discovery_agent.new_candidate", symbol=token.symbol, has_contract=bool(token.eth_contract))

            # 6. Mark tokens that no longer pass as removed
            to_remove = set(existing_symbols.keys()) - passing_symbols
            if to_remove:
                await session.execute(
                    update(TokenCandidate)
                    .where(TokenCandidate.symbol.in_(to_remove))
                    .values(status=TokenStatus.removed)
                )
                result.candidates_removed = len(to_remove)
                CANDIDATES_REMOVED.inc(len(to_remove))
                log.info("discovery_agent.candidates_removed", count=len(to_remove), symbols=list(to_remove))

        result.candidates_found = len(passing)
        result.candidate_symbols = [t.symbol for t in passing]
        CANDIDATES_FOUND.set(len(passing))

        # 7. Publish to Redis
        await bus.publish(Channel.DISCOVERY_NEW_CANDIDATES, result.model_dump())

        log.info(
            "discovery_agent.run_completed",
            scanned=result.tokens_scanned,
            candidates=result.candidates_found,
            removed=result.candidates_removed,
        )
        return result
