"""
Research Agent — Narrative Swing Module
Ciclo cada NARRATIVE_CYCLE_HOURS: escanea narrativa + onchain + técnico
sobre TOKEN_UNIVERSE, genera un score combinado (0-100) y notifica según threshold.
"""
import asyncio
import time
from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from sqlalchemy import select, text

from shared.config import settings
from shared.models import NarrativeCandidate, NarrativeCandidateStatus, get_session
from agents.monitor.onchain_client import OnchainClient

from .cryptopanic_client import CryptoPanicClient
from .lunarcrush_client import LunarCrushClient
from .nansen_client import NansenClient
from .notifier import NarrativeNotifier
from .scorer import NarrativeScorer
from .technical_client import TechnicalClient

log = structlog.get_logger(__name__)

# Universo de tokens monitoreados
TOKEN_UNIVERSE = [
    # Portfolio existente de Marce
    "XRP", "HBAR", "XLM", "XDC", "ONDO",
    # Tokens de utilidad adicionales
    "BTC", "ETH", "LINK", "SOL", "MATIC",
    "ADA", "DOT", "ATOM", "AVAX", "UNI",
]

# symbol -> id de CoinGecko, verificado contra /coins/list en vivo (2026-07-12)
TOKEN_COINGECKO_MAP = {
    "XRP": "ripple", "HBAR": "hedera-hashgraph", "XLM": "stellar",
    "XDC": "xdce-crowd-sale", "ONDO": "ondo-finance",
    "BTC": "bitcoin", "ETH": "ethereum", "LINK": "chainlink",
    "SOL": "solana", "MATIC": "polygon-ecosystem-token",
    "ADA": "cardano", "DOT": "polkadot", "ATOM": "cosmos",
    "AVAX": "avalanche-2", "UNI": "uniswap",
}

_NANSEN_CHAIN_TO_ONCHAIN_CHAIN = {"ethereum": "evm", "solana": "solana"}

# Símbolos sin ninguna cobertura Nansen posible (L1 nativo sin contrato ni override en
# nansen_client._NATIVE_TOKEN_OVERRIDE) -- clasificación estática, no depende de si la
# resolución de contrato falló este ciclo por rate-limit. Ver scorer.calculate()
# onchain_coverage_available para el rebalanceo Narrativa 50 + Técnico 50 que aplica
# a estos símbolos. Confirmado en vivo 2026-07-18 contra la API real de Nansen; SOL
# tiene cobertura vía _NATIVE_TOKEN_OVERRIDE por eso NO está en este set, ETH sí está
# porque el endpoint de netflow no expone ETH nativo ni con include_native_tokens=true.
NO_ONCHAIN_COVERAGE = frozenset({
    "XRP", "HBAR", "XLM", "XDC", "BTC", "ADA", "DOT", "ATOM", "ETH",
})

# ── Prometheus metrics ────────────────────────────────────────────────────────
SYMBOLS_PROCESSED = Counter("narrative_symbols_processed_total", "Total símbolos procesados")
SYMBOL_ERRORS = Counter("narrative_symbol_errors_total", "Errores al procesar un símbolo")
ALERTS_SENT = Counter("narrative_alerts_sent_total", "Alertas enviadas", ["mode"])
CYCLE_DURATION = Histogram(
    "narrative_cycle_duration_seconds",
    "Duración del ciclo completo",
    buckets=[30, 60, 120, 300, 600],
)
LAST_CYCLE_SCORE_MAX = Gauge("narrative_last_cycle_max_score", "Score combinado más alto del último ciclo")


class ResearchAgent:
    def __init__(self) -> None:
        self._lunarcrush = LunarCrushClient()
        self._nansen = NansenClient()
        self._cryptopanic = CryptoPanicClient()
        self._technical = TechnicalClient()
        self._onchain = OnchainClient()
        self._scorer = NarrativeScorer()
        self._notifier = NarrativeNotifier()
        self._scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        start_http_server(9106)
        log.info("research_agent.prometheus_started", port=9106)

        self._scheduler.add_job(
            self.run_cycle,
            trigger="interval",
            hours=settings.narrative_cycle_hours,
            id="narrative_cycle",
            replace_existing=True,
            max_instances=1,
        )
        self._scheduler.start()
        log.info("research_agent.scheduled", hours=settings.narrative_cycle_hours)

        await self.run_cycle()

        try:
            while True:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            self._scheduler.shutdown(wait=False)
            await self._technical.close()

    async def run_cycle(self) -> None:
        t0 = time.monotonic()
        log.info("research_agent.cycle_start", symbols=len(TOKEN_UNIVERSE))

        max_score = 0.0
        processed = 0
        errors = 0

        for i, symbol in enumerate(TOKEN_UNIVERSE):
            if i > 0:
                # Pacing entre símbolos — LunarCrush/CoinGecko rate-limitan con requests
                # seguidos sin espacio (visto en vivo: 429 en casi todos los símbolos sin esto).
                await asyncio.sleep(3.0)
            try:
                score_value = await self._process_symbol(symbol)
                if score_value is not None:
                    max_score = max(max_score, score_value)
                processed += 1
                SYMBOLS_PROCESSED.inc()
            except Exception as e:
                errors += 1
                SYMBOL_ERRORS.inc()
                log.error("research_agent.symbol_error", symbol=symbol, error=str(e))
                continue

        duration = time.monotonic() - t0
        CYCLE_DURATION.observe(duration)
        LAST_CYCLE_SCORE_MAX.set(max_score)

        await self._write_memory(processed, errors, max_score, duration)

        log.info(
            "research_agent.cycle_complete",
            processed=processed, errors=errors,
            max_score=max_score, duration=f"{duration:.1f}s",
        )

    async def _process_symbol(self, symbol: str) -> float | None:
        coingecko_id = TOKEN_COINGECKO_MAP.get(symbol)

        lc_data = await self._lunarcrush.get_metrics(symbol)
        cp_data = await self._cryptopanic.get_news(symbol)
        technical_data = await self._technical.get_snapshot(symbol)

        # Resuelto una sola vez y reutilizado para Nansen + holder concentration —
        # dos resoluciones por símbolo duplicaban las requests a CoinGecko y
        # disparaban 429 en casi todo el ciclo.
        contract = await self._nansen.resolve_contract(coingecko_id)
        nansen_data = await self._nansen.get_smart_money(symbol, contract)

        holder_pct = None
        if contract:
            address, nansen_chain = contract
            onchain_chain = _NANSEN_CHAIN_TO_ONCHAIN_CHAIN.get(nansen_chain)
            holder_pct, _source = await self._onchain.get_holder_concentration(address, onchain_chain)

        previous = await self._get_previous(symbol)
        alt_rank_change = self._delta(lc_data.alt_rank, previous.alt_rank if previous else None)
        holder_change = self._delta(holder_pct, previous.holder_concentration if previous else None)

        score = self._scorer.calculate(
            lc_data, cp_data, nansen_data, technical_data,
            holder_concentration_pct=holder_pct,
            alt_rank_change=alt_rank_change,
            holder_concentration_change=holder_change,
            onchain_coverage_available=symbol not in NO_ONCHAIN_COVERAGE,
        )

        await self._save_candidate(symbol, score, lc_data, cp_data, nansen_data, technical_data, holder_pct, previous)

        if score.combined >= settings.narrative_alert_threshold:
            await self._notifier.send_high_confidence(symbol, score)
            ALERTS_SENT.labels(mode="auto").inc()
        elif score.combined >= settings.narrative_consult_threshold:
            await self._notifier.send_consult_marce(symbol, score)
            ALERTS_SENT.labels(mode="consult").inc()

        log.info("research_agent.symbol_processed", symbol=symbol, score=score.combined)
        return score.combined

    @staticmethod
    def _delta(current, previous) -> float | None:
        if current is None or previous is None:
            return None
        return float(current) - float(previous)

    async def _get_previous(self, symbol: str) -> NarrativeCandidate | None:
        async with get_session() as session:
            return (
                await session.execute(
                    select(NarrativeCandidate)
                    .where(NarrativeCandidate.symbol == symbol)
                    .order_by(NarrativeCandidate.last_checked.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

    async def _save_candidate(
        self, symbol, score, lc_data, cp_data, nansen_data, technical_data, holder_pct, previous
    ) -> None:
        now = datetime.now(timezone.utc)
        alert_sent = score.combined >= settings.narrative_consult_threshold

        values = dict(
            exchange="spot",
            narrative_score=score.narrative_score,
            onchain_score=score.onchain_score,
            technical_score=score.technical_score,
            combined_score=score.combined,
            narrative_description=score.narrative_desc,
            galaxy_score=lc_data.galaxy_score,
            alt_rank=lc_data.alt_rank,
            social_volume_24h=None,
            panic_score=cp_data.avg_panic_score,
            latest_news=" | ".join(cp_data.top_headlines) if cp_data.top_headlines else None,
            smart_money_netflow=nansen_data.net_flow_24h_usd,
            holder_concentration=holder_pct,
            rsi_1d=technical_data.rsi_1d,
            volume_24h_usd=technical_data.volume_24h_usd,
            price_usd=technical_data.price_usd or lc_data.price_usd,
            status=NarrativeCandidateStatus.candidate,
            alert_sent=alert_sent,
            last_checked=now,
        )

        async with get_session() as session:
            if previous:
                obj = await session.get(NarrativeCandidate, previous.id)
                for k, v in values.items():
                    setattr(obj, k, v)
            else:
                session.add(NarrativeCandidate(symbol=symbol, created_at=now, **values))

    async def _write_memory(self, processed: int, errors: int, max_score: float, duration: float) -> None:
        summary = (
            f"Ciclo research_agent: {processed} símbolos procesados, {errors} errores, "
            f"score máximo {max_score:.0f}/100, duración {duration:.0f}s"
        )
        try:
            async with get_session() as session:
                await session.execute(
                    text(
                        "INSERT INTO lab_memory (tipo, agente, clave, valor, proyecto) "
                        "VALUES ('operativa', 'research_agent', :clave, :valor, 'narrative_swing')"
                    ),
                    {"clave": f"cycle_{datetime.now(timezone.utc):%Y%m%d_%H%M}", "valor": summary},
                )
        except Exception as e:
            log.warning("research_agent.lab_memory_error", error=str(e))
