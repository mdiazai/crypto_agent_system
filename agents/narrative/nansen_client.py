"""
Cliente Nansen API v1 — smart money net flow por token.
Endpoint y schema verificados en vivo: POST /api/v1/smart-money/netflow
Auth header verificado: "apikey" (minúsculas).

Nansen solo cubre tokens con contrato en chains EVM/Solana. Para activos
nativos de layer-1 sin contrato propio (ej. XRP, HBAR, BTC, SOL nativo,
ADA, DOT, ATOM) no hay cobertura — get_smart_money() retorna netflow=None
sin error, mismo patrón "None silencioso" que agents/monitor/onchain_client.py.

Resolución de contrato vía CoinGecko /coins/{id} (mismo patrón que
agents/discovery/exchange_scanner.py.get_eth_contracts), cacheada en Redis 24h
porque un contrato no cambia.
"""
from dataclasses import dataclass
from typing import Optional

import httpx
import structlog

from shared.config import settings
from shared.utils.retry import http_retry

log = structlog.get_logger(__name__)

_NANSEN_BASE = "https://api.nansen.ai/api/v1"
_COINGECKO_BASE = "https://api.coingecko.com/api/v3"


@dataclass
class NansenSmartMoney:
    symbol: str
    net_flow_24h_usd: Optional[float] = None
    trader_count: Optional[int] = None
    chain: Optional[str] = None


class NansenClient:
    def __init__(self) -> None:
        self._headers = {
            "apikey": settings.nansen_api_key.get_secret_value(),
            "Content-Type": "application/json",
        }
        cg_key = settings.coingecko_api_key.get_secret_value()
        self._cg_headers = {"x-cg-demo-api-key": cg_key} if cg_key else {}
        self._redis = None

    async def _redis_client(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def resolve_contract(self, coingecko_id: str) -> Optional[tuple[str, str]]:
        """(contract_address, chain) para tokens EVM/Solana, o None si es L1 nativo sin contrato."""
        key = f"narrative:contract:{coingecko_id}"
        r = await self._redis_client()
        try:
            cached = await r.get(key)
            if cached is not None:
                return None if cached == "null" else tuple(cached.split("|"))
        except Exception:
            pass

        try:
            platforms = await self._fetch_platforms(coingecko_id)
        except Exception as e:
            # No cachear: un fallo de red/429 no significa "sin contrato" — sin esto,
            # una falla transitoria queda envenenando el resultado por 24h.
            log.warning("nansen_client.contract_resolve_error", coingecko_id=coingecko_id, error=str(e))
            return None

        addr = platforms.get("ethereum")
        if addr:
            result = (addr, "ethereum")
        elif platforms.get("solana"):
            result = (platforms["solana"], "solana")
        else:
            result = None

        try:
            await r.setex(key, 86400, "null" if result is None else "|".join(result))
        except Exception:
            pass
        return result

    @http_retry
    async def _fetch_platforms(self, coingecko_id: str) -> dict:
        """GET /coins/{id} con retry — CoinGecko free/demo tier rate-limita rápido con >1 req/s."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_COINGECKO_BASE}/coins/{coingecko_id}",
                params={
                    "localization": "false", "tickers": "false", "market_data": "false",
                    "community_data": "false", "developer_data": "false",
                },
                headers=self._cg_headers,
            )
            resp.raise_for_status()
            return resp.json().get("platforms", {})

    @http_retry
    async def _post(self, path: str, body: dict) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{_NANSEN_BASE}{path}", headers=self._headers, json=body)
            resp.raise_for_status()
            return resp.json()

    async def get_smart_money(
        self, symbol: str, contract: Optional[tuple[str, str]]
    ) -> NansenSmartMoney:
        """contract = (address, chain) ya resuelto por el caller (ver resolve_contract) —
        no se resuelve de nuevo acá para no duplicar requests a CoinGecko."""
        if contract is None:
            return NansenSmartMoney(symbol=symbol)

        address, chain = contract
        try:
            payload = await self._post("/smart-money/netflow", {
                "chains": [chain],
                "filters": {"token_address": [address]},
                "pagination": {"page": 1, "per_page": 1},
            })
        except Exception as e:
            log.warning("nansen_client.netflow_error", symbol=symbol, error=str(e))
            return NansenSmartMoney(symbol=symbol, chain=chain)

        rows = (payload or {}).get("data") or []
        if not rows:
            return NansenSmartMoney(symbol=symbol, chain=chain)

        row = rows[0]
        return NansenSmartMoney(
            symbol=symbol,
            net_flow_24h_usd=row.get("net_flow_24h_usd"),
            trader_count=row.get("trader_count"),
            chain=chain,
        )
