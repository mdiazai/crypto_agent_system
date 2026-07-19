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
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx
import structlog
import redis.asyncio as aioredis
from sqlalchemy import select, func

from shared.config import settings
from sqlalchemy import and_
from shared.models import TokenCandidate, Alert, Trade, LearningLog, get_session

from .schemas import AgentHealth, AgentStatus, SystemHealth

log = structlog.get_logger(__name__)

_HEALTHY_WINDOW = timedelta(minutes=10)
_DEGRADED_WINDOW = timedelta(minutes=30)
_MAX_RESTARTS = 3

_ALERT_COOLDOWN_KEY_PREFIX = "supervisor:alert_cooldown:"
_ALERT_COOLDOWN_SECONDS = 3600  # no reenviar la misma alerta más de 1 vez por hora


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
        """Envía alerta Telegram cuando un agente no responde (máx. 1 vez por hora
        para el mismo conjunto de agentes — ver _ALERT_COOLDOWN_SECONDS)."""
        names = sorted(a.name for a in agents)
        alert_hash = hashlib.sha256(",".join(names).encode("utf-8")).hexdigest()[:16]

        if self._redis:
            cooldown_key = _ALERT_COOLDOWN_KEY_PREFIX + alert_hash
            if await self._redis.exists(cooldown_key):
                log.info(
                    "supervisor.alert_suppressed_cooldown",
                    agents=names,
                    alert_hash=alert_hash,
                )
                return

        try:
            from telegram import Bot
            bot = Bot(token=settings.telegram_bot_token.get_secret_value())
            await bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=f"⚠️ <b>Agentes sin actividad</b>\n{', '.join(names)}\nVerifica los contenedores.",
                parse_mode="HTML",
            )
            if self._redis:
                await self._redis.setex(
                    _ALERT_COOLDOWN_KEY_PREFIX + alert_hash, _ALERT_COOLDOWN_SECONDS, "1"
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
        # Discovery corre una vez al día: ventana de 25h es "sano"
        return _make_health(
            "discovery", last, now,
            healthy_window=timedelta(hours=25),
            degraded_window=timedelta(hours=50),
            no_data_detail="sin candidatos en DB",
        )

    async def _check_monitor(self, now: datetime) -> AgentHealth:
        async with get_session() as session:
            last = (
                await session.execute(
                    select(func.max(TokenCandidate.last_checked))
                )
            ).scalar_one_or_none()
        return _make_health("monitor", last, now, degraded_window=timedelta(minutes=12))

    async def _check_detector(self, now: datetime) -> AgentHealth:
        # El Detector actualiza detection_score en token_candidates; no depende de alertas
        async with get_session() as session:
            last = (
                await session.execute(
                    select(func.max(TokenCandidate.last_checked)).where(
                        TokenCandidate.detection_score.is_not(None)
                    )
                )
            ).scalar_one_or_none()
        return _make_health(
            "detector", last, now,
            degraded_window=timedelta(minutes=15),
            no_data_detail="esperando primera señal",
        )

    async def _check_scorer(self, now: datetime) -> AgentHealth:
        # Heartbeat escrito por el scorer cada vez que procesa un token ≥ umbral
        if self._redis:
            hb = await self._redis.get("scorer:heartbeat")
            if hb is not None:
                return AgentHealth(
                    name="scorer",
                    status="healthy",
                    last_activity=now,
                    detail=f"activo — última señal: {hb}",
                )
        # Fallback: última alerta guardada en DB
        async with get_session() as session:
            last = (
                await session.execute(select(func.max(Alert.sent_at)))
            ).scalar_one_or_none()
        return _make_health(
            "scorer", last, now,
            degraded_window=timedelta(hours=2),
            no_data_detail="esperando primer score ≥ umbral",
        )

    async def _check_executor(self, now: datetime) -> AgentHealth:
        # Heartbeat escrito por el position_monitor_loop cada 30s
        if self._redis:
            hb = await self._redis.get("executor:heartbeat")
            if hb is not None:
                open_pos = int(hb)
                detail = (
                    f"activo — {open_pos} posición{'es' if open_pos != 1 else ''} abierta{'s' if open_pos != 1 else ''}"
                    if open_pos > 0 else "activo — sin posiciones abiertas"
                )
                return AgentHealth(
                    name="executor",
                    status="healthy",
                    last_activity=now,
                    detail=detail,
                )
        # Fallback: última entrada en DB si el heartbeat expiró
        async with get_session() as session:
            last = (
                await session.execute(select(func.max(Trade.entry_time)))
            ).scalar_one_or_none()
        return _make_health(
            "executor", last, now,
            degraded_window=timedelta(hours=6),
            no_data_detail="esperando primera señal de trade",
        )

    async def _check_learner(self, now: datetime) -> AgentHealth:
        async with get_session() as session:
            last_log = (
                await session.execute(
                    select(LearningLog).order_by(LearningLog.created_at.desc()).limit(1)
                )
            ).scalar_one_or_none()

        if last_log is None:
            return AgentHealth(name="learner", status="unknown", detail="esperando primer trade cerrado")

        # insufficient_data = estado de espera, no error → "unknown" en lugar de "degraded"
        if last_log.notes == "insufficient_data":
            return AgentHealth(
                name="learner",
                status="unknown",
                last_activity=last_log.created_at,
                detail=f"esperando más trades cerrados ({last_log.tokens_evaluated} evaluados — mínimo requerido no alcanzado)",
            )

        # Learner corre una vez al día → ventana de 25h para "sano"
        return _make_health(
            "learner", last_log.created_at, now,
            healthy_window=timedelta(hours=25),
            degraded_window=timedelta(hours=50),
            no_data_detail="esperando primer trade cerrado",
        )

    async def _check_dashboard(self) -> AgentHealth:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(settings.dashboard_health_url)
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
    healthy_window: timedelta = _HEALTHY_WINDOW,
    degraded_window: timedelta = _DEGRADED_WINDOW,
    no_data_detail: str = "sin datos en DB",
) -> AgentHealth:
    if last is None:
        return AgentHealth(name=name, status="unknown", detail=no_data_detail)

    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    delta = now - last
    if delta <= healthy_window:
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
