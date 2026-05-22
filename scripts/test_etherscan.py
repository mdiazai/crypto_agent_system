"""
Test directo de Etherscan para verificar que la API key funciona
y que get_holder_concentration retorna datos para un ERC-20 conocido.

Uso:
  docker exec -i crypto_agent_system-monitor-1 python - < /opt/crypto_agent_system/scripts/test_etherscan.py
"""
import asyncio
import os
import sys

sys.path.insert(0, "/app")

from agents.monitor.onchain_client import OnchainClient

# USDC (Ethereum mainnet) — ERC-20 con holders conocidos
USDC_CONTRACT = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


async def test() -> None:
    print(f"ETHERSCAN_API_KEY: {os.getenv('ETHERSCAN_API_KEY', 'NO CONFIGURADA')[:10]}...")

    client = OnchainClient()

    print(f"\nTest 1 — _detect_chain('{USDC_CONTRACT[:10]}...')")
    from agents.monitor.onchain_client import _detect_chain
    chain = _detect_chain(USDC_CONTRACT)
    print(f"  chain detectada: {chain}  (esperado: 'evm')")

    print(f"\nTest 2 — get_holder_concentration con chain='evm' explícita")
    result = await client.get_holder_concentration(USDC_CONTRACT, "evm")
    print(f"  resultado: {result}  (esperado: (float, 'Etherscan'))")

    print(f"\nTest 3 — get_holder_concentration con chain=None (auto-detect)")
    result2 = await client.get_holder_concentration(USDC_CONTRACT, None)
    print(f"  resultado: {result2}  (esperado: igual al anterior)")


if __name__ == "__main__":
    asyncio.run(test())
