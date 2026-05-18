import asyncio
import time
from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from sqlalchemy import select, update

from shared.config import settings
from shared.models import TokenCandidate, TokenStatus, get_session
from shared.redis_bus import bus, Channel

from .data_fetcher import DataFetcher
from .schemas import TokenSnapshot, MonitorCycleResult

log = structlog.get_logger(__name__)

# ── Prometheus metrics ────────────────────────────────────────────────────────
TOKENS_CHECKED = Counter("monitor_tokens_checked_total", "Total individual token checks")
API_ERRORS = Counter("monitor_api_errors_total", "Failed data fetches", ["reason"])
CYCLE_DURATION = Histogram(
    "monitor_cycle_duration_seconds",
    "Time for a full monitoring cycle",
    buckets=[5, 10, 30, 60, 120, 300],
)
ACTIVE_TOKENS = Gauge("monitor_active_tokens", "Tokens currently in watchlist")


class MonitorAgent:
    def __init__(self) -> None:
        self._fetcher = DataFetcher()
        self._scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        await bus.connect()

        start_http_server(9101)
        log.info("monitor_agent.prometheus_started", port=9101)

        self._scheduler.add_job(
            self.run_cycle,
            trigger="interval",
            seconds=settings.monitor_interval_seconds,
            id="monitor_cycle",
            replace_existing=True,
            max_instances=1,           # no se solapa con sí mismo
        )
        self._scheduler.start()
        log.info(
            "monitor_agent.scheduled",
            interval_seconds=settings.monitor_interval_seconds,
        )

        # Primer ciclo inmediato
        await self.run_cycle()

        try:
            while True:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            self._scheduler.shutdown(wait=False)
            await self._fetcher.close()
            await bus.disconnect()

    async def run_cycle(self) -> MonitorCycleResult:
        t0 = time.monotonic()
        result = MonitorCycleResult(cycle_at=datetime.now(timezone.utc))
        log.info("monitor_agent.cycle_started")

        # 1. Leer tokens activos desde PostgreSQL
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(TokenCandidate.symbol, TokenCandidate.exchange, TokenCandidate.contract_address, TokenCandidate.chain)
                    .where(TokenCandidate.status == TokenStatus.active)
                )
            ).all()

        active_tokens = [
            {"symbol": r.symbol, "exchange": r.exchange, "contract_address": r.contract_address, "chain": r.chain}
            for r in rows
        ]
        result.tokens_checked = len(active_tokens)
        ACTIVE_TOKENS.set(len(active_tokens))

        if not active_tokens:
            log.info("monitor_agent.no_active_tokens")
            return result

        # 2. Fetch en paralelo con semáforo interno en DataFetcher
        tasks = [
            self._fetch_and_publish(t["symbol"], t["exchange"], t.get("contract_address"), t.get("chain"))
            for t in active_tokens
        ]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for outcome in outcomes:
            if isinstance(outcome, Exception):
                result.fetch_errors += 1
                API_ERRORS.labels(reason="gather_exception").inc()
            elif outcome:
                result.snapshots_published += 1

        TOKENS_CHECKED.inc(len(active_tokens))

        # 3. Actualizar last_checked en DB para los tokens procesados
        symbols = [t["symbol"] for t in active_tokens]
        async with get_session() as session:
            await session.execute(
                update(TokenCandidate)
                .where(TokenCandidate.symbol.in_(symbols))
                .values(last_checked=datetime.now(timezone.utc))
            )

        result.duration_seconds = time.monotonic() - t0
        CYCLE_DURATION.observe(result.duration_seconds)

        log.info(
            "monitor_agent.cycle_done",
            tokens=result.tokens_checked,
            published=result.snapshots_published,
            errors=result.fetch_errors,
            duration=f"{result.duration_seconds:.1f}s",
        )
        return result

    async def _fetch_and_publish(self, symbol: str, exchange: str, contract_address: str | None = None, chain: str | None = None) -> bool:
        snapshot: TokenSnapshot | None = await self._fetcher.fetch_all(symbol, exchange, contract_address, chain)
        if snapshot is None:
            API_ERRORS.labels(reason="no_snapshot").inc()
            return False

        await bus.publish(Channel.MONITOR_PUMP_SIGNAL, snapshot.model_dump())
        return True
