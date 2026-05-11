"""
Clientes para datos on-chain.

Glassnode: inflow de tokens hacia exchanges + distribución de holders.
Etherscan: fallback para tokens ERC-20 (requiere contract address).

Si las API keys no están configuradas, todos los métodos devuelven None
y el sistema continúa con los datos de exchange disponibles.
"""
import httpx
import structlog
from datetime import datetime, timezone, timedelta
from typing import Optional

from shared.config import settings
from shared.utils.retry import http_retry

log = structlog.get_logger(__name__)

GLASSNODE_BASE = "https://api.glassnode.com/v1/metrics"

# Mapeo de símbolo → asset ID de Glassnode (solo los más comunes)
GLASSNODE_ASSET_MAP = {
    "BTC": "BTC", "ETH": "ETH", "BNB": "BNB", "SOL": "SOL",
    "MATIC": "MATIC", "AVAX": "AVAX", "LINK": "LINK", "UNI": "UNI",
    "AAVE": "AAVE", "LTC": "LTC", "XRP": "XRP", "ADA": "ADA",
}


class GlassnodeClient:
    def __init__(self) -> None:
        self._api_key = settings.glassnode_api_key.get_secret_value()
        self._available = bool(self._api_key)
        if not self._available:
            log.warning("glassnode.no_api_key", msg="On-chain data disabled — set GLASSNODE_API_KEY")

    def _asset_id(self, symbol: str) -> Optional[str]:
        return GLASSNODE_ASSET_MAP.get(symbol.upper())

    @http_retry
    async def _get(self, client: httpx.AsyncClient, endpoint: str, asset: str, since_ts: int) -> list[dict]:
        resp = await client.get(
            f"{GLASSNODE_BASE}/{endpoint}",
            params={
                "a": asset,
                "api_key": self._api_key,
                "s": since_ts,
                "i": "1h",
                "f": "JSON",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_exchange_inflow_usd(self, symbol: str, hours: int = 4) -> Optional[float]:
        """Retorna el inflow total hacia exchanges en las últimas `hours` horas (USD)."""
        if not self._available:
            return None
        asset = self._asset_id(symbol)
        if not asset:
            return None

        since_ts = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp())
        try:
            async with httpx.AsyncClient() as client:
                data = await self._get(
                    client,
                    "transactions/transfers_volume_to_exchanges_sum",
                    asset,
                    since_ts,
                )
            if not data:
                return None
            total = sum(d.get("v", 0) for d in data if d.get("v") is not None)
            return float(total)
        except Exception:
            log.exception("glassnode.inflow_error", symbol=symbol)
            return None

    async def get_top10_holder_pct(self, symbol: str) -> Optional[float]:
        """Retorna el % del supply en manos del top-10% de holders."""
        if not self._available:
            return None
        asset = self._asset_id(symbol)
        if not asset:
            return None

        since_ts = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())
        try:
            async with httpx.AsyncClient() as client:
                data = await self._get(
                    client,
                    "distribution/balance_1pct_holders",
                    asset,
                    since_ts,
                )
            if not data:
                return None
            latest = max(data, key=lambda d: d.get("t", 0))
            return float(latest.get("v", 0)) * 100
        except Exception:
            log.exception("glassnode.holders_error", symbol=symbol)
            return None


class EtherscanClient:
    """Placeholder para inflow ERC-20 via Etherscan. Requiere contract address."""

    def __init__(self) -> None:
        self._api_key = settings.etherscan_api_key.get_secret_value()
        self._available = bool(self._api_key)

    async def get_exchange_inflow_usd(
        self,
        contract_address: str,
        price_usd: float,
        hours: int = 4,
    ) -> Optional[float]:
        """
        Suma de tokens ERC-20 enviados hacia exchange wallets conocidas.
        Implementación futura: requiere lista de exchange hot wallets.
        """
        # TODO: implementar con lista de exchange wallets (Binance, MEXC, Bitget, etc.)
        # Por ahora retorna None — el Detector usará señales alternativas.
        return None
