"""
Orchestrator: punto de entrada central del sistema.

Responsabilidades:
  1. Esperar a que PostgreSQL y Redis estén listos
  2. Ejecutar migraciones Alembic
  3. Exponer /health en puerto 8080
  4. Monitorear salud de agentes cada 60s
  5. Analizar contexto de mercado cada 5 min
  6. Llamar Claude API cuando el mercado es anómalo
"""
import asyncio
import subprocess
import sys
from contextlib import asynccontextmanager

import structlog
import redis.asyncio as aioredis
import asyncpg
from fastapi import FastAPI
import uvicorn

from shared.config import settings
from shared.utils import configure_logging
from shared.redis_bus import bus

from .agent_supervisor import AgentSupervisor
from .market_context import MarketContextAnalyzer
from .claude_advisor import ClaudeAdvisor
from .schemas import SystemHealth, ThresholdAdvice

log = structlog.get_logger(__name__)

supervisor = AgentSupervisor()
market_analyzer = MarketContextAnalyzer()
claude_advisor = ClaudeAdvisor()


# ── FastAPI health app ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()

    # Esperar servicios y correr migraciones
    await _wait_for_services()
    await _run_migrations()

    # Conectar clientes internos
    await bus.connect()
    await supervisor.connect()
    await market_analyzer.connect()
    await claude_advisor.connect()

    log.info("orchestrator.ready", paper_trading=settings.paper_trading)

    # Lanzar loops en segundo plano
    tasks = [
        asyncio.create_task(supervisor.monitor_loop(interval_seconds=60)),
        asyncio.create_task(_market_analysis_loop()),
    ]

    yield  # servidor corriendo

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await bus.disconnect()
    log.info("orchestrator.shutdown")


health_app = FastAPI(title="Orchestrator Health", lifespan=lifespan)


@health_app.get("/health")
async def health() -> SystemHealth:
    return await supervisor.get_system_health()


@health_app.get("/health/agents/{name}")
async def agent_health(name: str):
    system = await supervisor.get_system_health()
    for agent in system.agents:
        if agent.name == name:
            return agent
    return {"error": f"Agent '{name}' not found"}


# ── Loops de background ───────────────────────────────────────────────────────

async def _market_analysis_loop() -> None:
    """Analiza el mercado cada 5 min y llama a Claude si hay anomalías."""
    log.info("orchestrator.market_analysis_loop_started")
    while True:
        await asyncio.sleep(300)
        try:
            context = await market_analyzer.analyze()
            if context.is_anomalous:
                advice: ThresholdAdvice | None = await claude_advisor.advise(context)
                if advice and advice.action != "keep_threshold":
                    await _apply_threshold_advice(advice)
        except Exception:
            log.exception("orchestrator.market_analysis_error")


async def _apply_threshold_advice(advice: ThresholdAdvice) -> None:
    """Publica el ajuste de umbral recomendado por Claude en Redis."""
    if advice.new_threshold is None:
        return

    import redis.asyncio as aioredis
    import json

    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    await r.hset("config:runtime_overrides", "alert_threshold", json.dumps(advice.new_threshold))
    await r.aclose()

    log.info(
        "orchestrator.threshold_adjusted",
        action=advice.action,
        new_threshold=advice.new_threshold,
        reason=advice.reason,
        confidence=advice.confidence,
    )

    try:
        from telegram import Bot
        bot = Bot(token=settings.telegram_bot_token.get_secret_value())
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=(
                f"⚙️ <b>Orchestrator — Ajuste automático</b>\n"
                f"Acción: {advice.action}\n"
                f"Nuevo umbral: {advice.new_threshold}\n"
                f"Razón: {advice.reason}\n"
                f"Confianza: {advice.confidence:.0%}"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        log.error("orchestrator.telegram_notify_failed", error=str(e))


# ── Inicialización ────────────────────────────────────────────────────────────

async def _wait_for_services(retries: int = 30, delay: float = 2.0) -> None:
    """Espera a que PostgreSQL y Redis estén listos."""
    for attempt in range(1, retries + 1):
        try:
            conn = await asyncpg.connect(
                settings.database_url.replace("postgresql+asyncpg://", "postgresql://"),
                timeout=3,
            )
            await conn.close()

            r = aioredis.from_url(settings.redis_url)
            await r.ping()
            await r.aclose()

            log.info("orchestrator.services_ready")
            return
        except Exception as e:
            log.warning(
                "orchestrator.waiting_for_services",
                attempt=attempt,
                error=str(e),
            )
            await asyncio.sleep(delay)

    log.error("orchestrator.services_unavailable")
    sys.exit(1)


async def _run_migrations() -> None:
    """Ejecuta `alembic upgrade head` de forma sincrónica en un subprocess."""
    log.info("orchestrator.running_migrations")
    result = subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd="/app",
    )
    if result.returncode != 0:
        log.error("orchestrator.migration_failed", stderr=result.stderr)
        sys.exit(1)
    log.info("orchestrator.migrations_done", stdout=result.stdout.strip())


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    configure_logging()
    import sentry_sdk
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.05)

    uvicorn.run(
        health_app,
        host="0.0.0.0",
        port=8080,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
