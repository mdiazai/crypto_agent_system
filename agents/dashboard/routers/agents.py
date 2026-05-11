from fastapi import APIRouter, Depends
from shared.redis_bus import bus, Channel
from agents.dashboard.auth import get_current_user
from agents.dashboard.schemas import MessageResponse

router = APIRouter(prefix="/agents", tags=["agents"])

_CTRL_DISCOVERY = "channel:control:discovery:run"
_CTRL_MONITOR = "channel:control:monitor:run"
_CTRL_LEARNER = "channel:control:learner:evaluate"


@router.post("/discovery/run", response_model=MessageResponse, status_code=202)
async def trigger_discovery(_: dict = Depends(get_current_user)):
    """Solicita al agente Discovery que ejecute un ciclo de escaneo inmediato."""
    await bus.publish(_CTRL_DISCOVERY, {"trigger": "manual", "source": "dashboard"})
    return MessageResponse(message="Ciclo de Discovery encolado.")


@router.post("/monitor/run", response_model=MessageResponse, status_code=202)
async def trigger_monitor(_: dict = Depends(get_current_user)):
    """Solicita al agente Monitor que ejecute un ciclo de monitoreo inmediato."""
    await bus.publish(_CTRL_MONITOR, {"trigger": "manual", "source": "dashboard"})
    return MessageResponse(message="Ciclo de Monitor encolado.")


@router.post("/learner/evaluate", response_model=MessageResponse, status_code=202)
async def trigger_learner(_: dict = Depends(get_current_user)):
    """Solicita al agente Learner que ejecute un ciclo de aprendizaje inmediato."""
    await bus.publish(_CTRL_LEARNER, {"trigger": "manual", "source": "dashboard"})
    return MessageResponse(message="Ciclo de Learner encolado.")


@router.get("/status", response_model=dict)
async def agents_status(_: dict = Depends(get_current_user)):
    """Estado básico de los agentes (basado en Redis heartbeats)."""
    import redis.asyncio as aioredis
    from shared.config import settings
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    circuit_breaker = bool(await r.exists("executor:circuit_breaker"))
    cb_triggered_at = await r.get("executor:cb_triggered_at")
    await r.aclose()

    return {
        "circuit_breaker_active": circuit_breaker,
        "circuit_breaker_triggered_at": cb_triggered_at,
        "paper_trading": settings.paper_trading,
    }
