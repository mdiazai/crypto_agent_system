import json
from fastapi import APIRouter, Depends
from typing import Optional
import redis.asyncio as aioredis

from shared.config import settings
from agents.dashboard.auth import get_current_user
from agents.dashboard.schemas import ConfigResponse, ConfigUpdateRequest, MessageResponse

router = APIRouter(prefix="/config", tags=["config"])

_OVERRIDE_KEY = "config:runtime_overrides"


async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


@router.get("", response_model=ConfigResponse)
async def get_config(_: dict = Depends(get_current_user)):
    """Devuelve la configuración actual del sistema (sin secrets)."""
    r = await _get_redis()
    raw = await r.hgetall(_OVERRIDE_KEY)
    await r.aclose()

    overrides = {k: json.loads(v) for k, v in raw.items()} if raw else {}

    return ConfigResponse(
        paper_trading=overrides.get("paper_trading", settings.paper_trading),
        capital_total_usd=overrides.get("capital_total_usd", settings.capital_total_usd),
        mexc_allocation_pct=overrides.get("mexc_allocation_pct", settings.mexc_allocation_pct),
        bitget_allocation_pct=overrides.get("bitget_allocation_pct", settings.bitget_allocation_pct),
        alert_threshold=overrides.get("alert_threshold", settings.alert_threshold),
        llm_validation_threshold=overrides.get("llm_validation_threshold", settings.llm_validation_threshold),
        monitor_interval_seconds=overrides.get("monitor_interval_seconds", settings.monitor_interval_seconds),
        discovery_schedule_hour=overrides.get("discovery_schedule_hour", settings.discovery_schedule_hour),
        stop_loss_pct=overrides.get("stop_loss_pct", settings.stop_loss_pct),
        take_profit_1_pct=overrides.get("take_profit_1_pct", settings.take_profit_1_pct),
        take_profit_2_pct=overrides.get("take_profit_2_pct", settings.take_profit_2_pct),
        take_profit_3_pct=overrides.get("take_profit_3_pct", settings.take_profit_3_pct),
        max_daily_loss_pct=overrides.get("max_daily_loss_pct", settings.max_daily_loss_pct),
        max_consecutive_losses=overrides.get("max_consecutive_losses", settings.max_consecutive_losses),
        inflow_threshold_usd=overrides.get("inflow_threshold_usd", settings.inflow_threshold_usd),
        holder_concentration_threshold=overrides.get(
            "holder_concentration_threshold", settings.holder_concentration_threshold
        ),
    )


@router.put("", response_model=MessageResponse)
async def update_config(
    req: ConfigUpdateRequest,
    _: dict = Depends(get_current_user),
):
    """
    Actualiza parámetros de configuración en Redis.
    Los agentes leen estos overrides en su próximo ciclo.
    Nota: algunos cambios (intervalos de scheduler) requieren reinicio del agente.
    """
    r = await _get_redis()
    updates = req.model_dump(exclude_none=True)
    if updates:
        pipeline = r.pipeline()
        for key, value in updates.items():
            pipeline.hset(_OVERRIDE_KEY, key, json.dumps(value))
        await pipeline.execute()
    await r.aclose()

    return MessageResponse(
        message=f"Configuración actualizada: {list(updates.keys())}",
        detail=updates,
    )
