"""
Test directo de Etherscan V2 — verifica que la API key funciona con V2.

Uso:
  docker exec -i crypto_agent_system-monitor-1 python - < /opt/crypto_agent_system/scripts/test_etherscan.py
"""
import asyncio
import os
import sys

import httpx

sys.path.insert(0, "/app")

ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


async def test() -> None:
    api_key = os.getenv("ETHERSCAN_API_KEY", "")
    print(f"ETHERSCAN_API_KEY: {api_key[:10]}...")

    async with httpx.AsyncClient() as client:

        print("\n--- tokenholderlist Ethereum chainid=1 ---")
        r = await client.get(ETHERSCAN_V2, params={
            "chainid": 1,
            "module": "token", "action": "tokenholderlist",
            "contractaddress": USDC, "page": 1, "offset": 10,
            "apikey": api_key,
        }, timeout=15)
        data = r.json()
        print(f"  status:  {data.get('status')}")
        print(f"  message: {data.get('message')}")
        result = data.get("result")
        if isinstance(result, str):
            print(f"  result:  {result[:80]}")
        elif isinstance(result, list):
            print(f"  result:  [{len(result)} holders]  ← OK")

        print("\n--- tokensupply Ethereum chainid=1 ---")
        r2 = await client.get(ETHERSCAN_V2, params={
            "chainid": 1,
            "module": "stats", "action": "tokensupply",
            "contractaddress": USDC,
            "apikey": api_key,
        }, timeout=15)
        data2 = r2.json()
        print(f"  status:  {data2.get('status')}")
        print(f"  message: {data2.get('message')}")
        print(f"  result:  {str(data2.get('result', ''))[:30]}")

        print("\n--- tokeninfo Ethereum chainid=1 ---")
        r3 = await client.get(ETHERSCAN_V2, params={
            "chainid": 1,
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

    print("\n--- OnchainClient.get_holder_concentration (via V2) ---")
    from agents.monitor.onchain_client import OnchainClient
    oc = OnchainClient()
    pct, source = await oc.get_holder_concentration(USDC, "evm")
    print(f"  resultado: ({pct}, '{source}')  (esperado: (float, 'Etherscan'))")


if __name__ == "__main__":
    asyncio.run(test())
