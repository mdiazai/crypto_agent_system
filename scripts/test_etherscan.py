"""
Test directo de Etherscan — muestra respuesta raw de cada endpoint.

Uso:
  docker exec -i crypto_agent_system-monitor-1 python - < /opt/crypto_agent_system/scripts/test_etherscan.py
"""
import asyncio
import os
import sys

import httpx

sys.path.insert(0, "/app")

ETHERSCAN_BASE = "https://api.etherscan.io/api"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


async def test() -> None:
    api_key = os.getenv("ETHERSCAN_API_KEY", "")
    print(f"ETHERSCAN_API_KEY: {api_key[:10]}...")

    async with httpx.AsyncClient() as client:

        print("\n--- tokenholderlist (usado en get_holder_concentration) ---")
        r = await client.get(ETHERSCAN_BASE, params={
            "module": "token", "action": "tokenholderlist",
            "contractaddress": USDC, "page": 1, "offset": 10,
            "apikey": api_key,
        }, timeout=15)
        data = r.json()
        print(f"  status:  {data.get('status')}")
        print(f"  message: {data.get('message')}")
        result = data.get("result")
        if isinstance(result, str):
            print(f"  result:  {result}")
        elif isinstance(result, list):
            print(f"  result:  [{len(result)} holders]")

        print("\n--- tokensupply (usado en get_holder_concentration) ---")
        r2 = await client.get(ETHERSCAN_BASE, params={
            "module": "stats", "action": "tokensupply",
            "contractaddress": USDC,
            "apikey": api_key,
        }, timeout=15)
        data2 = r2.json()
        print(f"  status:  {data2.get('status')}")
        print(f"  message: {data2.get('message')}")
        print(f"  result:  {str(data2.get('result', ''))[:30]}")

        print("\n--- tokeninfo (usado en get_holder_count) ---")
        r3 = await client.get(ETHERSCAN_BASE, params={
            "module": "token", "action": "tokeninfo",
            "contractaddress": USDC,
            "apikey": api_key,
        }, timeout=15)
        data3 = r3.json()
        print(f"  status:  {data3.get('status')}")
        print(f"  message: {data3.get('message')}")
        result3 = data3.get("result", [])
        if isinstance(result3, list) and result3:
            print(f"  holdersCount: {result3[0].get('holdersCount', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(test())
