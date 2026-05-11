"""
Clientes on-chain multi-fuente (gratuitos, sin Glassnode):
  - Coinglass : funding rate, open interest, long/short ratio (sin API key)
  - Etherscan : holder count aproximado (API key gratuita)
  - CryptoQuant: exchange inflow (API key gratuita con registro)

Todos los métodos devuelven None si la fuente no está disponible o falla.
El sistema continúa normalmente usando señales alternativas.
"""
import httpx
import structlog
from typing import Optional

from shared.config import settings
from shared.utils.retry import http_retry

log = structlog.get_logger(__name__)

COINGLASS_BASE  = "https://open-api.coinglass.com/public/v2"
ETHERSCAN_BASE  = "https://api.etherscan.io/api"
CRYPTOQUANT_BASE = "https://api.cryptoquant.com/v1"


# ── Coinglass ─────────────────────────────────────────────────────────────────

class CoinglassClient:
    """Datos de derivados cross-exchange. Endpoints públicos, sin API key.

    Devuelve None para tokens pequeños que Coinglass no cubre (500/404 esperados).
    No se reintentan errores HTTP — solo errores de red.
    """

    async def _get(self, client: httpx.AsyncClient, endpoint: str, params: dict) -> dict | None:
        try:
            resp = await client.get(
                f"{COINGLASS_BASE}/{endpoint}",
                params=params,
                headers={"accept": "application/json"},
                timeout=8,
            )
            if resp.status_code >= 400:
                return None  # token sin datos en Coinglass — no reintentar
            return resp.json()
        except httpx.TimeoutException:
            return None
        except Exception:
            return None

    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        """Funding rate promedio cross-exchange (fracción decimal). None si falla."""
        try:
            async with httpx.AsyncClient() as client:
                data = await self._get(client, "indicator/funding_avg", {"symbol": symbol.upper()})
            if not data:
                return None
            rows = data.get("data", [])
            values = [r["rate"] for r in rows if r.get("rate") is not None]
            return sum(values) / len(values) if values else None
        except Exception:
            log.debug("coinglass.funding_rate_failed", symbol=symbol)
            return None

    async def get_long_short_ratio(self, symbol: str) -> Optional[float]:
        """Ratio longs/shorts (cuenta). > 1 = más longs. None si falla."""
        try:
            async with httpx.AsyncClient() as client:
                data = await self._get(
                    client,
                    "indicator/long_short_account_ratio",
                    {"symbol": symbol.upper(), "interval": "0h", "limit": 1},
                )
            if not data:
                return None
            rows = data.get("data", [])
            if not rows:
                return None
            ratio = rows[-1].get("longRatio")
            short = rows[-1].get("shortRatio")
            if ratio and short and float(short) > 0:
                return float(ratio) / float(short)
            return float(ratio) if ratio else None
        except Exception:
            log.debug("coinglass.long_short_failed", symbol=symbol)
            return None

    async def get_open_interest(self, symbol: str) -> Optional[float]:
        """OI total agregado cross-exchange (USD). None si falla."""
        try:
            async with httpx.AsyncClient() as client:
                data = await self._get(
                    client, "indicator/open_interest", {"symbol": symbol.upper()}
                )
            if not data:
                return None
            rows = data.get("data", [])
            total = sum(r.get("openInterest", 0) for r in rows)
            return float(total) if total else None
        except Exception:
            log.debug("coinglass.open_interest_failed", symbol=symbol)
            return None


# ── Etherscan ─────────────────────────────────────────────────────────────────

class EtherscanClient:
    """Holder count aproximado via Etherscan (requiere API key gratuita)."""

    def __init__(self) -> None:
        self._api_key = settings.etherscan_api_key.get_secret_value()
        self._available = bool(self._api_key)
        if not self._available:
            log.info("etherscan.no_api_key", msg="Holder data disabled — set ETHERSCAN_API_KEY")

    async def get_holder_count(self, contract_address: Optional[str]) -> Optional[int]:
        """Total de holders únicos para un ERC-20. Proxy inverso de concentración."""
        if not self._available or not contract_address:
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    ETHERSCAN_BASE,
                    params={
                        "module": "token",
                        "action": "tokeninfo",
                        "contractaddress": contract_address,
                        "apikey": self._api_key,
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
            if data.get("status") != "1":
                return None
            result = data.get("result", [])
            if isinstance(result, list) and result:
                raw = result[0].get("holdersCount")
                return int(raw) if raw else None
            return None
        except Exception:
            log.debug("etherscan.holder_count_failed", contract=contract_address)
            return None


# ── CryptoQuant ───────────────────────────────────────────────────────────────

class CryptoQuantClient:
    """Exchange inflow via CryptoQuant (free tier con API key)."""

    # Símbolos soportados por CryptoQuant free tier
    _SUPPORTED = {"BTC", "ETH", "XRP", "LTC", "BCH", "EOS", "TRX", "BNB"}

    def __init__(self) -> None:
        self._api_key = settings.cryptoquant_api_key.get_secret_value()
        self._available = bool(self._api_key)
        if not self._available:
            log.info("cryptoquant.no_api_key", msg="CQ inflow disabled — set CRYPTOQUANT_API_KEY")

    async def get_exchange_inflow(self, symbol: str) -> Optional[float]:
        """Inflow total a exchanges en las últimas horas (USD). None si falla."""
        if not self._available or symbol.upper() not in self._SUPPORTED:
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{CRYPTOQUANT_BASE}/{symbol.lower()}/exchange-flows/inflow",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Accept": "application/json",
                    },
                    params={"window": "hour", "limit": 4},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
            rows = data.get("result", {}).get("data", [])
            total = sum(r.get("inflow_usd", 0) for r in rows if r.get("inflow_usd"))
            return float(total) if total else None
        except Exception:
            log.debug("cryptoquant.inflow_failed", symbol=symbol)
            return None


# ── Fachada unificada ─────────────────────────────────────────────────────────

class OnchainClient:
    """Combina Coinglass + Etherscan + CryptoQuant en una interfaz única."""

    def __init__(self) -> None:
        self.coinglass   = CoinglassClient()
        self.etherscan   = EtherscanClient()
        self.cryptoquant = CryptoQuantClient()

    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        return await self.coinglass.get_funding_rate(symbol)

    async def get_long_short_ratio(self, symbol: str) -> Optional[float]:
        return await self.coinglass.get_long_short_ratio(symbol)

    async def get_open_interest(self, symbol: str) -> Optional[float]:
        return await self.coinglass.get_open_interest(symbol)

    async def get_holder_count(self, contract_address: Optional[str] = None) -> Optional[int]:
        return await self.etherscan.get_holder_count(contract_address)

    async def get_exchange_inflow(self, symbol: str) -> Optional[float]:
        return await self.cryptoquant.get_exchange_inflow(symbol)
