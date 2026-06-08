"""
Test de CCXTDerivativesClient contra tokens reales en DB.

Uso (dentro del container monitor):
  docker exec -i crypto_agent_system-monitor-1 python - < /opt/crypto_agent_system/scripts/test_derivatives.py

Exit code 0 si al menos un token devuelve dato de derivados.
Exit code 1 si TODOS retornan None en funding rate Y open interest.
"""
import asyncio
import os
import sys

import asyncpg


async def main() -> int:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL no configurada")
        return 1

    # asyncpg no acepta el prefijo +asyncpg de SQLAlchemy
    pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(pg_url)
    rows = await conn.fetch(
        """
        SELECT symbol, volume_24h_usd
        FROM token_candidates
        WHERE status = 'active' AND volume_24h_usd > 500000
        ORDER BY volume_24h_usd DESC
        LIMIT 3
        """
    )
    await conn.close()

    if not rows:
        print("No hay tokens con volume > $500k activos en DB.")
        return 1

    # importar después de confirmar que hay tokens (evita init de exchanges si falla la DB)
    sys.path.insert(0, "/app")
    from agents.monitor.onchain_client import CCXTDerivativesClient

    client = CCXTDerivativesClient()

    any_data = False
    try:
        for row in rows:
            symbol = row["symbol"]
            vol = row["volume_24h_usd"]
            print(f"\n── {symbol} (vol 24h: ${vol:,.0f}) ──")

            funding = await client.get_funding_rate(symbol)
            oi      = await client.get_open_interest(symbol)

            print(f"  funding_rate    : {funding}")
            print(f"  open_interest   : {oi}")

            if funding is not None or oi is not None:
                any_data = True
    finally:
        await client.close()

    print()
    if any_data:
        print("OK — al menos un token devolvió datos de derivados.")
        return 0
    else:
        print("WARN — todos los tokens retornaron None. Sin contratos perpetuos en MEXC/Bitget.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
