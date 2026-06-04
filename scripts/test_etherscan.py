"""
Test de Moralis holder concentration + Etherscan count fallback.

Uso:
  docker exec -i crypto_agent_system-monitor-1 python - < /opt/crypto_agent_system/scripts/test_etherscan.py
"""
import asyncio
import os
import sys

import httpx

sys.path.insert(0, "/app")

MORALIS_BASE  = "https://deep-index.moralis.io/api/v2.2"
ETHERSCAN_V2  = "https://api.etherscan.io/v2/api"
USDC          = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


async def test() -> None:
    moralis_key   = os.getenv("MORALIS_API_KEY", "")
    etherscan_key = os.getenv("ETHERSCAN_API_KEY", "")
    print(f"MORALIS_API_KEY:   {moralis_key[:15]}...")
    print(f"ETHERSCAN_API_KEY: {etherscan_key[:10]}...")

    async with httpx.AsyncClient() as client:

        print(f"\n--- Moralis /erc20/{USDC[:10]}…/owners (chain=eth) ---")
        r = await client.get(
            f"{MORALIS_BASE}/erc20/{USDC}/owners",
            headers={"X-API-Key": moralis_key},
            params={"chain": "eth", "limit": 10, "order": "DESC"},
            timeout=15,
        )
        print(f"  HTTP {r.status_code}")
        if r.status_code == 200:
            holders = r.json().get("result", [])
            print(f"  holders returned: {len(holders)}")
            if holders:
                first = holders[0]
                pct_field = first.get("percentage_relative_to_total_supply")
                print(f"  percentage_relative_to_total_supply: {pct_field}")
                total_pct = sum(
                    float(h.get("percentage_relative_to_total_supply") or 0)
                    for h in holders[:10]
                )
                print(f"  sum top-10 pct: {round(total_pct, 2)}%  ← holder_concentration_pct")
        else:
            print(f"  error: {r.text[:120]}")

        print(f"\n--- Etherscan tokeninfo (holdersCount fallback) ---")
        r2 = await client.get(ETHERSCAN_V2, params={
            "chainid": 1, "module": "token", "action": "tokeninfo",
            "contractaddress": USDC, "apikey": etherscan_key,
        }, timeout=15)
        data2 = r2.json()
        print(f"  status:  {data2.get('status')}")
        print(f"  message: {data2.get('message')}")
        result2 = data2.get("result", [])
        if isinstance(result2, list) and result2:
            print(f"  holdersCount: {result2[0].get('holdersCount', 'N/A')}")
        else:
            print(f"  result: {str(result2)[:80]}")

    print(f"\n--- OnchainClient.get_holder_concentration (Moralis → Etherscan) ---")
    from agents.monitor.onchain_client import OnchainClient
    oc = OnchainClient()
    pct, source = await oc.get_holder_concentration(USDC, "evm")
    print(f"  resultado: ({pct}, '{source}')")
    print(f"  {'✓ OK' if pct is not None else '✗ FALLO — holder_concentration_pct = None'}")

    print(f"\n--- OnchainClient.get_holder_count (total holders) ---")
    count = await oc.get_holder_count(USDC)
    print(f"  holder_count: {count}")
    print(f"  {'✓ OK' if count is not None else '✗ FALLO — holder_count = None'}")


if __name__ == "__main__":
    asyncio.run(test())
