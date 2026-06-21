"""
Clientes on-chain multi-fuente (gratuitos, sin Glassnode):
  - CCXTDerivatives: funding rate, open interest via MEXC/Bitget perpetuals (reemplaza Coinglass)
  - Etherscan V2  : holder concentration ERC-20 Ethereum (chainid=1, API key gratuita)
  - BscClient     : holder concentration BEP-20 BNB Chain (chainid=56, misma API key)
  - Helius        : holder concentration SPL (Solana, API key gratuita)
  - CryptoQuant   : exchange inflow (API key gratuita con registro)

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

ETHERSCAN_BASE      = "https://api.etherscan.io/v2/api"
HELIUS_RPC_BASE     = "https://mainnet.helius-rpc.com"
CRYPTOQUANT_BASE    = "https://api.cryptoquant.com/v1"

_CACHE_MISS = object()  # sentinel para distinguir "no cacheado" de None cacheado


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


# ── CCXTDerivatives ───────────────────────────────────────────────────────────

class CCXTDerivativesClient:
    """Funding rate y open interest via CCXT (MEXC + Bitget perpetuals).

    Reemplaza Coinglass para small-caps que no están en esa plataforma.
    None silencioso si el token no tiene contrato perpetuo — no es error.
    Cache Redis 5 min para no repetir llamadas en cada ciclo del Monitor.
    """

    _PAIR_SUFFIX = "/USDT:USDT"

    def __init__(self) -> None:
        import ccxt.async_support as ccxt_async
        self._mexc = ccxt_async.mexc({
            "apiKey": settings.mexc_api_key.get_secret_value(),
            "secret": settings.mexc_secret.get_secret_value(),
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })
        self._bitget = ccxt_async.bitget({
            "apiKey": settings.bitget_api_key.get_secret_value(),
            "secret": settings.bitget_secret.get_secret_value(),
            "password": settings.bitget_passphrase.get_secret_value(),
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })
        self._redis = None

    async def _redis_client(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def _cache_get(self, key: str):
        """Retorna el valor cacheado (float o None), o _CACHE_MISS si no existe."""
        try:
            r = await self._redis_client()
            val = await r.get(key)
            if val is None:
                return _CACHE_MISS
            return None if val == "null" else float(val)
        except Exception:
            return _CACHE_MISS

    async def _cache_set(self, key: str, value: Optional[float]) -> None:
        try:
            r = await self._redis_client()
            await r.setex(key, 300, "null" if value is None else str(value))
        except Exception:
            pass

    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        """Funding rate del perpetuo (fracción decimal). None si no existe contrato."""
        key = f"deriv:funding:{symbol}"
        cached = await self._cache_get(key)
        if cached is not _CACHE_MISS:
            return cached

        pair = f"{symbol}{self._PAIR_SUFFIX}"
        result = None
        for exchange in (self._mexc, self._bitget):
            try:
                data = await exchange.fetch_funding_rate(pair)
                val = data.get("fundingRate")
                if val is not None:
                    result = float(val)
                    break
            except Exception:
                continue

        await self._cache_set(key, result)
        return result

    async def get_open_interest(self, symbol: str) -> Optional[float]:
        """Open interest en USD. None si no existe contrato perpetuo."""
        key = f"deriv:oi:{symbol}"
        cached = await self._cache_get(key)
        if cached is not _CACHE_MISS:
            return cached

        pair = f"{symbol}{self._PAIR_SUFFIX}"
        result = None
        for exchange in (self._mexc, self._bitget):
            try:
                data = await exchange.fetch_open_interest(pair)
                val = data.get("openInterestValue")
                if val is not None:
                    result = float(val)
                    break
            except Exception:
                continue

        await self._cache_set(key, result)
        return result

    async def get_long_short_ratio(self, symbol: str) -> Optional[float]:
        """CCXT no expone L/S ratio directamente — retorna None."""
        return None

    async def close(self) -> None:
        for ex in (self._mexc, self._bitget):
            try:
                await ex.close()
            except Exception:
                pass
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass


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
                    ETHERSCAN_BASE,
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
                        ETHERSCAN_BASE,
                        params={
                            'chainid': 1,
                            'module': 'token',
                            'action': 'tokenholderlist',
                            'contractaddress': contract_address,
                            'page': 1,
                            'offset': 10,
                            'apikey': self._api_key,
                        },
                        timeout=10,
                    ),
                    client.get(
                        ETHERSCAN_BASE,
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
                        ETHERSCAN_BASE,
                        params={
                            'chainid': 56,
                            'module': 'token',
                            'action': 'tokenholderlist',
                            'contractaddress': contract_address,
                            'page': 1,
                            'offset': 10,
                            'apikey': self._api_key,
                        },
                        timeout=10,
                    ),
                    client.get(
                        ETHERSCAN_BASE,
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


# ── Moralis (EVM holder concentration) ───────────────────────────────────────

_MORALIS_SEM = asyncio.Semaphore(3)       # max 3 requests simultáneos
_MORALIS_CACHE_TTL = 21_600               # 6 horas en segundos


class MoralisClient:
    """Holder concentration via Moralis Deep Index API.
    Free tier: 40,000 req/mes. Endpoint: GET /erc20/{address}/owners
    """

    BASE       = "https://deep-index.moralis.io/api/v2.2"
    _CHAIN_ETH = "eth"
    _CHAIN_BSC = "0x38"   # BNB Chain hex chainId

    def __init__(self) -> None:
        self._api_key = settings.moralis_api_key.get_secret_value()
        self._available = bool(self._api_key)
        if not self._available:
            log.info("moralis.no_api_key",
                     msg="Holder concentration disabled — set MORALIS_API_KEY")
        self._cache: dict[str, tuple[float, float]] = {}  # contract -> (pct, expiry)

    def _cache_get(self, key: str) -> Optional[float]:
        entry = self._cache.get(key)
        if entry and asyncio.get_event_loop().time() < entry[1]:
            return entry[0]
        return None

    def _cache_set(self, key: str, value: float) -> None:
        expiry = asyncio.get_event_loop().time() + _MORALIS_CACHE_TTL
        self._cache[key] = (value, expiry)

    async def _fetch(self, contract_address: str, chain: str) -> Optional[float]:
        """Llama al endpoint para una chain específica (con semáforo y delay)."""
        try:
            async with _MORALIS_SEM:
                await asyncio.sleep(1.0)
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{self.BASE}/erc20/{contract_address}/owners",
                        headers={"X-API-Key": self._api_key},
                        params={"chain": chain, "limit": 10, "order": "DESC"},
                        timeout=12,
                    )
            if resp.status_code == 401:
                log.warning("moralis.unauthorized",
                            msg="Invalid API key — check MORALIS_API_KEY")
                return None
            if resp.status_code == 429:
                log.warning("moralis.rate_limited", chain=chain)
                return None
            if resp.status_code >= 400:
                log.debug("moralis.http_error", status=resp.status_code, chain=chain)
                return None
            holders = resp.json().get("result", [])
            if not holders:
                return None
            if "percentage_relative_to_total_supply" in holders[0]:
                return round(
                    sum(float(h.get("percentage_relative_to_total_supply") or 0)
                        for h in holders[:10]),
                    2,
                )
            log.debug("moralis.no_percentage_field", chain=chain)
            return None
        except httpx.TimeoutException:
            log.debug("moralis.timeout", contract=contract_address, chain=chain)
            return None
        except Exception:
            log.debug("moralis.failed", contract=contract_address, chain=chain)
            return None

    async def get_holder_concentration(self, contract_address: str) -> Optional[float]:
        """Intenta Ethereum, luego BNB Chain. Cache 6h para no exceder rate limit."""
        if not self._available or not contract_address:
            return None

        cached = self._cache_get(contract_address)
        if cached is not None:
            return cached

        pct = await self._fetch(contract_address, self._CHAIN_ETH)
        if pct is None:
            pct = await self._fetch(contract_address, self._CHAIN_BSC)

        if pct is not None:
            self._cache_set(contract_address, pct)
            log.debug("moralis.cached", contract=contract_address[:10], pct=pct)

        return pct


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
    """Combina CCXTDerivatives + Moralis + Etherscan V2 + BscClient + Helius + CryptoQuant."""

    def __init__(self) -> None:
        self.derivatives = CCXTDerivativesClient()
        self.moralis     = MoralisClient()
        self.etherscan   = EtherscanClient()
        self.bsc         = BscClient()
        self.helius      = HeliusClient()
        self.cryptoquant = CryptoQuantClient()

    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        return await self.derivatives.get_funding_rate(symbol)

    async def get_long_short_ratio(self, symbol: str) -> Optional[float]:
        return await self.derivatives.get_long_short_ratio(symbol)

    async def get_open_interest(self, symbol: str) -> Optional[float]:
        return await self.derivatives.get_open_interest(symbol)

    async def get_holder_count(self, contract_address: Optional[str] = None) -> Optional[int]:
        return await self.etherscan.get_holder_count(contract_address)

    async def get_holder_concentration(
        self,
        contract_address: Optional[str],
        chain: Optional[str] = None,
    ) -> tuple[Optional[float], Optional[str]]:
        """
        Retorna (pct_top10, source_name). Detecta la chain automáticamente si no se provee.
        Para chain='evm': intenta Etherscan chainid=1 primero, luego chainid=56 (BSC).
        Para chain='solana': usa Helius sin cambios.
        """
        if not contract_address:
            return None, None

        detected = chain or _detect_chain(contract_address)

        if detected == "solana":
            pct = await self.helius.get_holder_concentration(contract_address)
            return (pct, "Helius") if pct is not None else (None, None)

        if detected == "evm":
            # 1. Moralis: concentration real (top-10 % de supply)
            pct = await self.moralis.get_holder_concentration(contract_address)
            if pct is not None:
                return pct, "Moralis"
            # 2. Etherscan V2 chainid=1 (Ethereum)
            pct = await self.etherscan.get_holder_concentration(contract_address)
            if pct is not None:
                return pct, "Etherscan"
            # 3. Etherscan V2 chainid=56 (BSC)
            pct = await self.bsc.get_holder_concentration(contract_address)
            if pct is not None:
                return pct, "BSC"

        return None, None

    async def get_exchange_inflow(self, symbol: str) -> Optional[float]:
        return await self.cryptoquant.get_exchange_inflow(symbol)
