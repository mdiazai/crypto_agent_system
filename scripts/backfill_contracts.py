"""
Backfill de contract_address y chain para tokens activos sin contrato.
Corre UNA SOLA VEZ dentro del container discovery.

Uso:
  docker exec crypto_agent_system-discovery-1 python scripts/backfill_contracts.py
"""
import asyncio
import sys

import httpx

sys.path.insert(0, "/app")

from sqlalchemy import select, update

from shared.models import TokenCandidate, TokenStatus, get_session

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
DELAY     = 2.0   # segundos entre cada request (<=30 req/min free tier)
DELAY_429 = 60.0  # espera al recibir rate limit

CHAIN_PRIORITY = [
    "ethereum",
    "binance-smart-chain",
    "solana",
    "polygon-pos",
    "arbitrum-one",
    "optimistic-ethereum",
    "avalanche",
]

CHAIN_MAP = {
    "ethereum":            "evm",
    "binance-smart-chain": "evm",
    "polygon-pos":         "evm",
    "arbitrum-one":        "evm",
    "optimistic-ethereum": "evm",
    "avalanche":           "evm",
    "solana":              "solana",
}


async def cg_get(client: httpx.AsyncClient, url: str, params: dict | None = None):
    """GET con reintento automatico en 429. Retorna dict o None."""
    while True:
        try:
            resp = await client.get(url, params=params, timeout=15)
        except Exception as e:
            print(f"  [ERROR red] {e}")
            return None
        if resp.status_code == 429:
            print(f"  [429] Rate limit — esperando {int(DELAY_429)}s...")
            await asyncio.sleep(DELAY_429)
            continue
        if resp.status_code != 200:
            return None
        return resp.json()


async def find_coin_id(client: httpx.AsyncClient, symbol: str) -> str | None:
    """Primer coin_id que coincida exactamente con el simbolo (case-insensitive)."""
    data = await cg_get(client, f"{COINGECKO_BASE}/search", {"query": symbol})
    await asyncio.sleep(DELAY)
    if not data:
        return None
    for coin in data.get("coins", []):
        if coin.get("symbol", "").upper() == symbol.upper():
            return coin["id"]
    return None


async def get_platforms(client: httpx.AsyncClient, coin_id: str) -> dict:
    """Dict de platforms de /coins/{coin_id}."""
    data = await cg_get(
        client,
        f"{COINGECKO_BASE}/coins/{coin_id}",
        {
            "localization": "false",
            "tickers": "false",
            "market_data": "false",
            "community_data": "false",
            "developer_data": "false",
        },
    )
    await asyncio.sleep(DELAY)
    return data.get("platforms", {}) if data else {}


async def main() -> None:
    # 1. Tokens activos sin contrato
    async with get_session() as session:
        rows = (
            await session.execute(
                select(TokenCandidate.id, TokenCandidate.symbol)
                .where(TokenCandidate.status == TokenStatus.active)
                .where(TokenCandidate.contract_address == None)  # noqa: E711
            )
        ).all()

    total = len(rows)
    print(f"Tokens a procesar: {total}\n")
    con_datos = sin_datos = 0

    async with httpx.AsyncClient() as client:
        for i, row in enumerate(rows, 1):
            # Paso A — buscar coin_id
            coin_id = await find_coin_id(client, row.symbol)
            if not coin_id:
                print(f"[{i}/{total}] {row.symbol}: sin coincidencia en CoinGecko")
                sin_datos += 1
                continue

            # Paso B — obtener plataformas
            platforms = await get_platforms(client, coin_id)

            # Paso C — elegir contrato por prioridad
            contract: str | None = None
            chain_value: str | None = None
            for platform in CHAIN_PRIORITY:
                addr = platforms.get(platform)
                if addr:
                    contract = addr
                    chain_value = CHAIN_MAP.get(platform, "unknown")
                    break

            # Plataforma fuera de la lista de prioridad — tomar cualquier contrato disponible
            if not contract:
                for platform, addr in platforms.items():
                    if addr:
                        contract = addr
                        chain_value = CHAIN_MAP.get(platform, "unknown")
                        break

            if not contract:
                print(f"[{i}/{total}] {row.symbol}: coin_id={coin_id} — sin contrato en ninguna red")
                sin_datos += 1
                continue

            # Paso D — actualizar DB
            async with get_session() as session:
                await session.execute(
                    update(TokenCandidate)
                    .where(TokenCandidate.id == row.id)
                    .values(contract_address=contract, chain=chain_value)
                )

            print(f"[{i}/{total}] {row.symbol}: chain={chain_value} contract={contract[:14]}...")
            con_datos += 1

    print(f"\nCompletado: {con_datos} tokens con contrato, {sin_datos} sin datos en CoinGecko")


if __name__ == "__main__":
    asyncio.run(main())
