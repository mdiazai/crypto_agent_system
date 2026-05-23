"""
Clientes on-chain multi-fuente (gratuitos, sin Glassnode):
  - Coinglass   : funding rate, open interest, long/short ratio (sin API key)
  - Etherscan V2: holder concentration ERC-20 Ethereum (chainid=1, API key gratuita)
  - BscClient   : holder concentration BEP-20 BNB Chain (chainid=56, misma API key)
  - Helius      : holder concentration SPL (Solana, API key gratuita)
  - CryptoQuant : exchange inflow (API key gratuita con registro)

Todos los métodos devuelven None si la fuente no está disponible o falla.
El sistema continúa normalmente usando señales alternativas.
"""
import asyncio
import httpx
import structlog
from typing import Optional

from shared.config import settings
from shared.utils.retry import http_retry

log = structlog.get_logger(__name__)

COINGLASS_BASE      = "https://open-api.coinglass.com/public/v2"
ETHERSCAN_V2_BASE   = "https://api.etherscan.io/v2/api"
HELIUS_RPC_BASE     = "https://mainnet.helius-rpc.com"
CRYPTOQUANT_BASE    = "https://api.cryptoquant.com/v1"


def _detect_chain(contract_address: str) -> str:
    """Detecta la chain de un token por el formato del contrato."""
    if not contract_address:
        return "unknown"
    # Solana: base58, >= 32 chars, sin prefijo 0x
    if not contract_address.startswith("0x") and len(contract_address) >= 32:
        return "solana"
    # EVM: empieza con 0x y tiene exactamente 42 chars
    if contract_address.startswith("0x") and len(contract_address) == 42:
        return "evm"
    return "unknown"


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


# ── Etherscan V2 (Ethereum, chainid=1) ────────────────────────────────────────

class EtherscanClient:
    """Holder concentration via Etherscan V2 para tokens ERC-20 (Ethereum)."""

    _CHAIN_ID = 1  # Ethereum mainnet

    def __init__(self) -> None:
        self._api_key = settings.etherscan_api_key.get_secret_value()
        self._available = bool(self._api_key)
        if not self._available:
            log.info("etherscan.no_api_key", msg="Holder data disabled — set ETHERSCAN_API_KEY")

    async def get_holder_count(self, contract_address: Optional[str]) -> Optional[int]:
        """Total de holders únicos para un ERC-20."""
        if not self._available or not contract_address:
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    ETHERSCAN_V2_BASE,
                    params={
                        "chainid": self._CHAIN_ID,
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
                log.debug("etherscan.holder_count_notok", msg=data.get("message"),
                          result=str(data.get("result", ""))[:80])
                return None
            result = data.get("result", [])
            if isinstance(result, list) and result:
                raw = result[0].get("holdersCount")
                return int(raw) if raw else None
            return None
        except Exception:
            log.debug("etherscan.holder_count_failed", contract=contract_address)
            return None

    async def get_holder_concentration(self, contract_address: str) -> Optional[float]:
        """% del supply en top-10 wallets para un ERC-20."""
        if not self._available or not contract_address:
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp_holders, resp_supply = await asyncio.gather(
                    client.get(
                        ETHERSCAN_V2_BASE,
                        params={
                            "chainid": self._CHAIN_ID,
                            "module": "token",
                            "action": "tokenholderlist",
                            "contractaddress": contract_address,
                            "page": 1,
                            "offset": 10,
                            "apikey": self._api_key,
                        },
                        timeout=10,
                    ),
                    client.get(
                        ETHERSCAN_V2_BASE,
                        params={
                            "chainid": self._CHAIN_ID,
                            "module": "stats",
                            "action": "tokensupply",
                            "contractaddress": contract_address,
                            "apikey": self._api_key,
                        },
                        timeout=10,
                    ),
                )
            holders_data = resp_holders.json()
            supply_data = resp_supply.json()
            if holders_data.get("status") != "1" or supply_data.get("status") != "1":
                log.debug("etherscan.holder_concentration_notok",
                          holders_msg=holders_data.get("message"),
                          holders_result=str(holders_data.get("result", ""))[:60])
                return None
            holders = holders_data.get("result", [])
            total_supply = int(supply_data.get("result", 0))
            if not holders or not total_supply:
                return None
            top10_sum = sum(int(h.get("TokenHolderQuantity", 0)) for h in holders[:10])
            return round(top10_sum / total_supply * 100, 2)
        except Exception:
            log.debug("etherscan.holder_concentration_failed", contract=contract_address)
            return None


# ── BscClient (BNB Chain, chainid=56) via Etherscan V2 ───────────────────────

class BscClient:
    """Holder concentration via Etherscan V2 para tokens BEP-20 (BNB Chain).
    Usa la misma ETHERSCAN_API_KEY — no requiere BSCSCAN_API_KEY separada.
    """

    _CHAIN_ID = 56  # BNB Chain

    def __init__(self) -> None:
        self._api_key = settings.etherscan_api_key.get_secret_value()
        self._available = bool(self._api_key)
        if not self._available:
            log.debug("bsc.no_api_key", msg="BEP-20 holder data disabled — set ETHERSCAN_API_KEY")

    async def get_holder_concentration(self, contract_address: str) -> Optional[float]:
        """% del supply en top-10 wallets para un BEP-20."""
        if not self._available or not contract_address:
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp_holders, resp_supply = await asyncio.gather(
                    client.get(
                        ETHERSCAN_V2_BASE,
                        params={
                            "chainid": self._CHAIN_ID,
                            "module": "token",
                            "action": "tokenholderlist",
                            "contractaddress": contract_address,
                            "page": 1,
                            "offset": 10,
                            "apikey": self._api_key,
                        },
                        timeout=10,
                    ),
                    client.get(
                        ETHERSCAN_V2_BASE,
                        params={
                            "chainid": self._CHAIN_ID,
                            "module": "stats",
                            "action": "tokensupply",
                            "contractaddress": contract_address,
                            "apikey": self._api_key,
                        },
                        timeout=10,
                    ),
                )
            holders_data = resp_holders.json()
            supply_data = resp_supply.json()
            if holders_data.get("status") != "1" or supply_data.get("status") != "1":
                log.debug("bsc.holder_concentration_notok",
                          holders_msg=holders_data.get("message"),
                          holders_result=str(holders_data.get("result", ""))[:60])
                return None
            holders = holders_data.get("result", [])
            total_supply = int(supply_data.get("result", 0))
            if not holders or not total_supply:
                return None
            top10_sum = sum(int(h.get("TokenHolderQuantity", 0)) for h in holders[:10])
            return round(top10_sum / total_supply * 100, 2)
        except Exception:
            log.debug("bsc.holder_concentration_failed", contract=contract_address)
            return None


# ── Helius (Solana) ───────────────────────────────────────────────────────────

class HeliusClient:
    """Holder concentration via Helius RPC para tokens SPL (Solana)."""

    def __init__(self) -> None:
        self._api_key = settings.helius_api_key.get_secret_value()
        self._available = bool(self._api_key)
        if not self._available:
            log.info("helius.no_api_key", msg="Solana holder data disabled — set HELIUS_API_KEY")

    async def get_holder_concentration(self, mint_address: str) -> Optional[float]:
        """% del supply en top-10 wallets para un token SPL."""
        if not self._available or not mint_address:
            return None
        url = f"{HELIUS_RPC_BASE}/?api-key={self._api_key}"
        try:
            async with httpx.AsyncClient() as client:
                resp_large, resp_supply = await asyncio.gather(
                    client.post(url, json={
                        "jsonrpc": "2.0", "id": 1,
                        "method": "getTokenLargestAccounts",
                        "params": [mint_address],
                    }, timeout=10),
                    client.post(url, json={
                        "jsonrpc": "2.0", "id": 2,
                        "method": "getTokenSupply",
                        "params": [mint_address],
                    }, timeout=10),
                )
            accounts = resp_large.json().get("result", {}).get("value", [])
            supply_val = resp_supply.json().get("result", {}).get("value", {})
            total_ui = float(supply_val.get("uiAmount") or 0)
            if not accounts or not total_ui:
                return None
            top10_ui = sum(float(a.get("uiAmount") or 0) for a in accounts[:10])
            return round(top10_ui / total_ui * 100, 2)
        except Exception:
            log.debug("helius.holder_concentration_failed", mint=mint_address)
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
    """Combina Coinglass + Etherscan V2 + BscClient + Helius + CryptoQuant."""

    def __init__(self) -> None:
        self.coinglass   = CoinglassClient()
        self.etherscan   = EtherscanClient()
        self.bsc         = BscClient()
        self.helius      = HeliusClient()
        self.cryptoquant = CryptoQuantClient()

    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        return await self.coinglass.get_funding_rate(symbol)

    async def get_long_short_ratio(self, symbol: str) -> Optional[float]:
        return await self.coinglass.get_long_short_ratio(symbol)

    async def get_open_interest(self, symbol: str) -> Optional[float]:
        return await self.coinglass.get_open_interest(symbol)

    async def get_holder_count(self, contract_address: Optional[str] = None) -> Optional[int]:
        return await self.etherscan.get_holder_count(contract_address)

    async def get_holder_concentration(
        self,
        contract_address: Optional[str],
        chain: Optional[str] = None,
    ) -> tuple[Optional[float], Optional[str]]:
        """
        Retorna (pct_top10, source_name). Detecta la chain automáticamente si no se provee.
        Orden de intento: Etherscan → BSCScan → Helius.
        """
        if not contract_address:
            return None, None

        detected = chain or _detect_chain(contract_address)

        if detected == "solana":
            pct = await self.helius.get_holder_concentration(contract_address)
            return (pct, "Helius") if pct is not None else (None, None)

        if detected == "evm":
            # Intentar Ethereum (chainid=1) primero, luego BNB Chain (chainid=56)
            pct = await self.etherscan.get_holder_concentration(contract_address)
            if pct is not None:
                return pct, "Etherscan"
            pct = await self.bsc.get_holder_concentration(contract_address)
            if pct is not None:
                return pct, "BSC"

        return None, None

    async def get_exchange_inflow(self, symbol: str) -> Optional[float]:
        return await self.cryptoquant.get_exchange_inflow(symbol)
