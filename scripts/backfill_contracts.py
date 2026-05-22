"""
Backfill de contract_address y chain para tokens activos sin contrato.
Corre UNA SOLA VEZ dentro del container discovery.

Uso:
  docker exec -i crypto_agent_system-discovery-1 python - < /opt/crypto_agent_system/scripts/backfill_contracts.py
"""
import asyncio
import os
import sys

import asyncpg
import httpx

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
            print(f"  [ERROR] {e}")
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
    # ── Conexión directa con asyncpg (autocommit por defecto) ─────────────────
    raw_url = os.getenv("DATABASE_URL", "")
    print(f"DATABASE_URL: {raw_url[:40]}...")

    db_url = raw_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(db_url)

    # Verificar conexión y contar tokens activos
    total_activos = await conn.fetchval(
        "SELECT COUNT(*) FROM token_candidates WHERE status = 'active'"
    )
    print(f"Tokens activos en DB: {total_activos}")

    # Tokens activos sin contrato
    rows = await conn.fetch(
        "SELECT id, symbol FROM token_candidates "
        "WHERE status = 'active' AND contract_address IS NULL"
    )
    total = len(rows)
    print(f"Tokens a procesar (sin contrato): {total}\n")

    con_datos = sin_datos = 0

    async with httpx.AsyncClient() as client:
        for i, row in enumerate(rows, 1):
            symbol = row["symbol"]
            token_id = row["id"]

            # Paso A — buscar coin_id
            coin_id = await find_coin_id(client, symbol)
            if not coin_id:
                print(f"[{i}/{total}] {symbol}: sin coincidencia en CoinGecko")
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

            if not contract:
                for platform, addr in platforms.items():
                    if addr:
                        contract = addr
                        chain_value = CHAIN_MAP.get(platform, "unknown")
                        break

            if not contract:
                print(f"[{i}/{total}] {symbol}: coin_id={coin_id} — sin contrato en ninguna red")
                sin_datos += 1
                continue

            # Paso D — UPDATE directo, asyncpg hace autocommit fuera de transacción explícita
            status = await conn.execute(
                "UPDATE token_candidates SET contract_address = $1, chain = $2 WHERE id = $3",
                contract, chain_value, token_id,
            )
            # status devuelve "UPDATE N" — verificar que N=1
            updated = int(status.split()[-1])
            if updated == 0:
                print(f"[{i}/{total}] {symbol}: ADVERTENCIA — UPDATE 0 filas (id={token_id})")
                sin_datos += 1
                continue

            print(f"[{i}/{total}] {symbol}: chain={chain_value} contract={contract[:14]}...")
            con_datos += 1

    # ── Verificación final ────────────────────────────────────────────────────
    final_count = await conn.fetchval(
        "SELECT COUNT(*) FROM token_candidates WHERE contract_address IS NOT NULL"
    )
    await conn.close()

    print(f"\nCompletado: {con_datos} guardados, {sin_datos} sin datos")
    print(f"VERIFICACION FINAL: {final_count} tokens con contract_address en DB")


if __name__ == "__main__":
    asyncio.run(main())
