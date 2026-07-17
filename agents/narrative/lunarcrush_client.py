"""
Cliente LunarCrush API4 público — métricas de narrativa social por coin.
Endpoint verificado en vivo: GET /api4/public/coins/{symbol}/v1

No existe un campo de "cambio de AltRank" en esta API — se calcula
comparando contra el alt_rank guardado en el ciclo anterior
(ver research_agent._compute_alt_rank_change).
"""
from dataclasses import dataclass
from typing import Optional

import httpx
import structlog

from shared.config import settings
from shared.utils.retry import http_retry

log = structlog.get_logger(__name__)

_BASE = "https://lunarcrush.com/api4/public"


@dataclass
class LunarCrushMetrics:
    symbol: str
    galaxy_score: Optional[float] = None
    alt_rank: Optional[int] = None
    price_usd: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    market_cap_usd: Optional[float] = None
    percent_change_24h: Optional[float] = None


class LunarCrushClient:
    def __init__(self) -> None:
        self._headers = {
            "Authorization": f"Bearer {settings.lunarcrush_api_key.get_secret_value()}"
        }

    @http_retry
    async def _get(self, path: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_BASE}{path}", headers=self._headers)
            resp.raise_for_status()
            return resp.json()

    async def get_metrics(self, symbol: str) -> LunarCrushMetrics:
        """None silencioso en cada campo si la API falla — el ciclo continúa con otras señales."""
        try:
            payload = await self._get(f"/coins/{symbol}/v1")
        except Exception as e:
            log.warning("lunarcrush_client.error", symbol=symbol, error=str(e))
            return LunarCrushMetrics(symbol=symbol)

        data = (payload or {}).get("data") or {}
        if not data:
            log.warning("lunarcrush_client.empty_response", symbol=symbol)
            return LunarCrushMetrics(symbol=symbol)

        return LunarCrushMetrics(
            symbol=symbol,
            galaxy_score=data.get("galaxy_score"),
            alt_rank=data.get("alt_rank"),
            price_usd=data.get("price") or data.get("close"),
            volume_24h_usd=data.get("volume_24h"),
            market_cap_usd=data.get("market_cap"),
            percent_change_24h=data.get("percent_change_24h"),
        )
