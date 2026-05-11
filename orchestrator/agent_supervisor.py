"""
AgentSupervisor: monitorea la salud de cada agente consultando actividad en DB y Redis.

Estrategia de health check sin modificar los agentes:
  - Discovery → última fecha en token_candidates.last_checked
  - Monitor   → última fecha en token_candidates.last_checked (más reciente)
  - Detector  → última alerta en alerts.sent_at
  - Scorer    → última alerta en alerts.sent_at
  - Executor  → último trade en trades.entry_time
  - Learner   → último log en learning_logs.created_at
  - Dashboard → HTTP GET /health en puerto 8001
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx
import structlog
import redis.asyncio as aioredis
from sqlalchemy import select, func

from shared.config import settings
from shared.models import TokenCandidate, Alert, Trade, LearningLog, get_session

from .schemas import AgentHealth, AgentStatus, SystemHealth

log = structlog.get_logger(__name__)

_HEALTHY_WINDOW = timedelta(minutes=10)
_DEGRADED_WINDOW = timedelta(minutes=30)
_MAX_RESTARTS = 3


class AgentSupervisor:
    def __init__(self) -> None:
        self._restart_counts: dict[str, int] = {}
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    async def get_system_health(self) -> SystemHealth:
        now = datetime.now(timezone.utc)
        agents = await asyncio.gather(
            self._check_discovery(now),
            self._check_monitor(now),
            self._check_detector(now),
            self._check_scorer(now),
            self._check_executor(now),
            self._check_learner(now),
            self._check_dashboard(),
            return_exceptions=True,
        )

        agent_list: list[AgentHealth] = []
        for result in agents:
            if isinstance(result, Exception):
                agent_list.append(AgentHealth(name="unknown", status="unknown", detail=str(result)))
            else:
                agent_list.append(result)

        # Circuit breaker
        cb_active = False
        if self._redis:
            cb_active = bool(await self._redis.exists("executor:circuit_breaker"))

        overall = _compute_overall(agent_list)

        return SystemHealth(
            overall=overall,
            paper_trading=settings.paper_trading,
            circuit_breaker_active=cb_active,
            agents=agent_list,
            checked_at=now,
        )

    async def monitor_loop(self, interval_seconds: int = 60) -> None:
        log.info("supervisor.monitor_loop_started", interval=interval_seconds)
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                health = await self.get_system_health()
                unhealthy = [a for a in health.agents if a.status == "unhealthy"]
                if unhealthy:
                    names = [a.name for a in unhealthy]
                    log.warning("supervisor.unhealthy_agents", agents=names)
                    await self._notify_unhealthy(unhealthy)
                else:
                    log.debug("supervisor.all_healthy", overall=health.overall)
            except Exception:
                log.exception("supervisor.monitor_error")

    async def _notify_unhealthy(self, agents: list[AgentHealth]) -> None:
        """Envía alerta Telegram cuando un agente no responde."""
        try:
            from telegram import Bot
            bot = Bot(token=settings.telegram_bot_token.get_secret_value())
            names = ", ".join(a.name for a in agents)
            await bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=f"⚠️ <b>Agentes sin actividad</b>\n{names}\nVerifica los contenedores.",
                parse_mode="HTML",
            )
        except Exception as e:
            log.error("supervisor.notify_failed", error=str(e))

    # ── Checks individuales ───────────────────────────────────────────────────

    async def _check_discovery(self, now: datetime) -> AgentHealth:
        async with get_session() as session:
            last = (
                await session.execute(
                    select(func.max(TokenCandidate.added_at))
                )
            ).scalar_one_or_none()
        return _make_health("discovery", last, now)

    async def _check_monitor(self, now: datetime) -> AgentHealth:
        async with get_session() as session:
            last = (
                await session.execute(
                    select(func.max(TokenCandidate.last_checked))
                )
            ).scalar_one_or_none()
        return _make_health("monitor", last, now, degraded_window=timedelta(minutes=12))

    async def _check_detector(self, now: datetime) -> AgentHealth:
        async with get_session() as session:
            last = (
                await session.execute(select(func.max(Alert.sent_at)))
            ).scalar_one_or_none()
        # Detector no siempre genera alertas; usar ventana más amplia
        return _make_health("detector", last, now, degraded_window=timedelta(hours=2))

    async def _check_scorer(self, now: datetime) -> AgentHealth:
        async with get_session() as session:
            last = (
                await session.execute(select(func.max(Alert.sent_at)))
            ).scalar_one_or_none()
        return _make_health("scorer", last, now, degraded_window=timedelta(hours=2))

    async def _check_executor(self, now: datetime) -> AgentHealth:
        async with get_session() as session:
            last = (
                await session.execute(select(func.max(Trade.entry_time)))
            ).scalar_one_or_none()
        # Executor puede no tener trades si no hay señales
        return _make_health("executor", last, now, degraded_window=timedelta(hours=6))

    async def _check_learner(self, now: datetime) -> AgentHealth:
        async with get_session() as session:
            last = (
                await session.execute(select(func.max(LearningLog.created_at)))
            ).scalar_one_or_none()
        return _make_health("learner", last, now, degraded_window=timedelta(hours=26))

    async def _check_dashboard(self) -> AgentHealth:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get("http://dashboard:8001/health")
                if resp.status_code == 200:
                    return AgentHealth(
                        name="dashboard",
                        status="healthy",
                        last_activity=datetime.now(timezone.utc),
                        detail="HTTP 200 OK",
                    )
                return AgentHealth(name="dashboard", status="degraded", detail=f"HTTP {resp.status_code}")
        except Exception as e:
            return AgentHealth(name="dashboard", status="unhealthy", detail=str(e))


def _make_health(
    name: str,
    last: Optional[datetime],
    now: datetime,
    degraded_window: timedelta = _DEGRADED_WINDOW,
) -> AgentHealth:
    if last is None:
        return AgentHealth(name=name, status="unknown", detail="sin datos en DB")

    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    delta = now - last
    if delta <= _HEALTHY_WINDOW:
        status: AgentStatus = "healthy"
    elif delta <= degraded_window:
        status = "degraded"
    else:
        status = "unhealthy"

    return AgentHealth(
        name=name,
        status=status,
        last_activity=last,
        detail=f"última actividad hace {int(delta.total_seconds() // 60)} min",
    )


def _compute_overall(agents: list[AgentHealth]) -> str:
    statuses = {a.status for a in agents}
    if "unhealthy" in statuses:
        return "unhealthy"
    if "degraded" in statuses or "unknown" in statuses:
        return "degraded"
    return "healthy"
