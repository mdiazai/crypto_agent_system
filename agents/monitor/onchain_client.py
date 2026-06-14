import asyncio
import aiohttp
import os
from typing import Optional

ETHERSCAN_BASE = 'https://api.etherscan.io/v2/api'
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY', '')
HELIUS_API_KEY = os.getenv('HELIUS_API_KEY', '')
HELIUS_BASE = 'https://mainnet.helius-rpc.com'

class EtherscanClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def get_holder_concentration(self, token_address: str) -> Optional[dict]:
        params = {
            'chainid': 1,
            'module': 'token',
            'action': 'tokenholderlist',
            'contractaddress': token_address,
            'page': 1,
            'offset': 10,
            'apikey': ETHERSCAN_API_KEY,
        }
        try:
            async with self.session.get(ETHERSCAN_BASE, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get('status') == '1':
                    return {'chain': 'eth', 'holders': data.get('result', [])}
                return None
        except Exception:
            return None


class BscClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def get_holder_concentration(self, token_address: str) -> Optional[dict]:
        params = {
            'chainid': 56,
            'module': 'token',
            'action': 'tokenholderlist',
            'contractaddress': token_address,
            'page': 1,
            'offset': 10,
            'apikey': ETHERSCAN_API_KEY,
        }
        try:
            async with self.session.get(ETHERSCAN_BASE, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get('status') == '1':
                    return {'chain': 'bsc', 'holders': data.get('result', [])}
                return None
        except Exception:
            return None


class HeliusClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def get_holder_concentration(self, token_address: str) -> Optional[dict]:
        url = f"{HELIUS_BASE}/?api-key={HELIUS_API_KEY}"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenLargestAccounts",
            "params": [token_address],
        }
        try:
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                result = data.get('result', {}).get('value', [])
                if result:
                    return {'chain': 'solana', 'holders': result}
                return None
        except Exception:
            return None


class OnchainClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.eth_client = EtherscanClient(session)
        self.bsc_client = BscClient(session)
        self.helius_client = HeliusClient(session)

    async def get_holder_concentration(self, token_address: str, chain: str = 'evm') -> Optional[dict]:
        if chain == 'evm':
            result = await self.eth_client.get_holder_concentration(token_address)
            if result is not None:
                return result
            result = await self.bsc_client.get_holder_concentration(token_address)
            return result
        elif chain == 'solana':
            return await self.helius_client.get_holder_concentration(token_address)
        return None


async def main():
    async with aiohttp.ClientSession() as session:
        client = OnchainClient(session)
        result = await client.get_holder_concentration('0xTokenAddress', chain='evm')
        print(result)


if __name__ == '__main__':
    asyncio.run(main())
