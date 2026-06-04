import asyncio
from typing import Optional
import httpx
import ccxt.async_support as ccxt
import structlog

from shared.config import settings
from shared.utils.retry import http_retry
from .schemas import TokenData

log = structlog.get_logger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
COINGECKO_PRO_BASE = "https://pro-api.coingecko.com/api/v3"
STABLECOIN_BLACKLIST = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDP", "USDD"}

# Excluidos al cargar markets — evita llamadas a CoinGecko para tokens de gran cap
LARGE_CAP_SKIP: set[str] = {
    "BTC", "ETH", "BNB", "XRP", "SOL", "ADA", "DOGE", "AVAX",
    "DOT", "MATIC", "LINK", "UNI", "LTC", "BCH", "ATOM", "XLM",
    "ALGO", "VET", "FIL", "THETA", "ETC", "XMR", "HBAR", "NEAR",
    "FTM", "SAND", "MANA", "AXS", "GALA", "ENJ",
    "XAUT", "PAXG", "WBTC", "STETH", "WETH", "CBBTC",
}


class ExchangeScanner:
    def __init__(self) -> None:
        cg_key = settings.coingecko_api_key.get_secret_value()
        self._cg_base = COINGECKO_PRO_BASE if cg_key else COINGECKO_BASE
        self._cg_headers = {"x-cg-pro-api-key": cg_key} if cg_key else {}

    async def get_exchange_symbols(self, exchange_id: str) -> set[str]:
        """Returns set of base symbols available as USDT pairs on the given exchange."""
        exchange_cls = getattr(ccxt, exchange_id, None)
        if not exchange_cls:
            log.error("exchange_scanner.unknown_exchange", exchange_id=exchange_id)
            return set()

        exchange = exchange_cls({"enableRateLimit": True})
        try:
            markets = await exchange.load_markets()
            symbols = {
                m["base"]
                for m in markets.values()
                if m.get("quote") == "USDT"
                and m.get("active", True)
                and m.get("base") not in STABLECOIN_BLACKLIST
                and m.get("base") not in LARGE_CAP_SKIP
            }
            log.info("exchange_scanner.symbols_loaded", exchange=exchange_id, count=len(symbols))
            return symbols
        except Exception:
            log.exception("exchange_scanner.load_markets_failed", exchange=exchange_id)
            return set()
        finally:
            await exchange.close()

    @http_retry
    async def _fetch_cg_page(
        self,
        client: httpx.AsyncClient,
        page: int,
        per_page: int = 250,
    ) -> list[dict]:
        params = {
            "vs_currency": "usd",
            "order": "volume_desc",
            "per_page": per_page,
            "page": page,
            "sparkline": "false",
            "locale": "en",
        }
        resp = await client.get(
            f"{self._cg_base}/coins/markets",
            params=params,
            headers=self._cg_headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_market_data(self, symbols: set[str]) -> dict[str, dict]:
        """
        Fetches market data for up to 2000 tokens from CoinGecko and returns
        a dict keyed by uppercase symbol.
        """
        results: dict[str, dict] = {}
        async with httpx.AsyncClient() as client:
            for page in range(1, 9):  # 8 pages × 250 = 2000 tokens
                try:
                    data = await self._fetch_cg_page(client, page)
                except Exception:
                    log.exception("exchange_scanner.cg_page_failed", page=page)
                    break

                if not data:
                    break

                for coin in data:
                    sym = coin.get("symbol", "").upper()
                    if sym in symbols:
                        results[sym] = coin

                await asyncio.sleep(0.4)  # ~2.5 req/s, well within 30/min free limit

                if len(results) >= len(symbols):
                    break

        log.info("exchange_scanner.market_data_fetched", matched=len(results), queried=len(symbols))
        return results

    async def get_exchange_tickers(self, exchange_id: str, api_key: str = "", secret: str = "", passphrase: str = "") -> dict[str, dict]:
        """Fetches live tickers from exchange via CCXT — used as fallback when CoinGecko is unavailable."""
        exchange_cls = getattr(ccxt, exchange_id, None)
        if not exchange_cls:
            return {}

        cfg: dict = {"enableRateLimit": True}
        if api_key:
            cfg["apiKey"] = api_key
            cfg["secret"] = secret
            if passphrase:
                cfg["password"] = passphrase

        exchange = exchange_cls(cfg)
        try:
            tickers = await exchange.fetch_tickers()
            result: dict[str, dict] = {}
            for market_symbol, ticker in tickers.items():
                if not market_symbol.endswith("/USDT"):
                    continue
                base = market_symbol.split("/")[0]
                quote_vol = ticker.get("quoteVolume") or 0.0
                result[base] = {
                    "volume_24h_usd": float(quote_vol),
                    "price_change_24h_pct": ticker.get("percentage"),
                    "current_price": ticker.get("last"),
                }
            log.info("exchange_scanner.tickers_loaded", exchange=exchange_id, count=len(result))
            return result
        except Exception:
            log.exception("exchange_scanner.tickers_failed", exchange=exchange_id)
            return {}
        finally:
            await exchange.close()

    async def scan(self) -> list[TokenData]:
        """
        Full scan: carga markets de MEXC + Bitget, luego en paralelo:
        CoinGecko (puede ser parcial) + tickers de ambos exchanges como suplemento.
        """
        # Paso 1: cargar listas de símbolos de cada exchange
        mexc_symbols, bitget_symbols = await asyncio.gather(
            self.get_exchange_symbols("mexc"),
            self.get_exchange_symbols("bitget"),
        )
        all_symbols = mexc_symbols | bitget_symbols
        log.info("exchange_scanner.combined_symbols", total=len(all_symbols))

        # Paso 2: CoinGecko + tickers de exchange EN PARALELO
        cg_data, mexc_tickers, bitget_tickers = await asyncio.gather(
            self.get_market_data(all_symbols),
            self.get_exchange_tickers(
                "mexc",
                api_key=settings.mexc_api_key.get_secret_value(),
                secret=settings.mexc_secret.get_secret_value(),
            ),
            self.get_exchange_tickers(
                "bitget",
                api_key=settings.bitget_api_key.get_secret_value(),
                secret=settings.bitget_secret.get_secret_value(),
                passphrase=settings.bitget_passphrase.get_secret_value(),
            ),
        )

        # Tickers de exchange: MEXC tiene prioridad, Bitget como suplemento
        ticker_data = {**bitget_tickers, **mexc_tickers}
        log.info(
            "exchange_scanner.tickers_combined",
            mexc=len(mexc_tickers),
            bitget=len(bitget_tickers),
            cg_matched=len(cg_data),
        )

        tokens: list[TokenData] = []
        for sym in all_symbols:
            # Asignar exchange: Bitget solo si no está en MEXC
            exchange = "mexc" if sym in mexc_symbols else "bitget"

            cg = cg_data.get(sym, {})
            tk = ticker_data.get(sym, {})

            # Combinar: CoinGecko primero, ticker de exchange como suplemento
            mcap = cg.get("market_cap")
            cg_vol = cg.get("total_volume")
            tk_vol = tk.get("volume_24h_usd")
            vol = cg_vol or tk_vol          # CG preferido, ticker como fallback
            ratio = (vol / mcap) if mcap and vol and mcap > 0 else None
            price = cg.get("current_price") or tk.get("current_price")
            change = cg.get("price_change_percentage_24h") or tk.get("price_change_24h_pct")

            # Si el ticker del exchange dice que el símbolo está en Bitget pero no en MEXC,
            # corregir el exchange aunque ambos aparezcan en markets
            if sym not in mexc_tickers and sym in bitget_tickers:
                exchange = "bitget"

            tokens.append(TokenData(
                symbol=sym, base=sym, exchange=exchange,
                coingecko_id=cg.get("id"),
                market_cap_usd=mcap,
                volume_24h_usd=vol,
                volume_to_mcap_ratio=ratio,
                token_age_days=_calc_age_days(cg.get("atl_date")),
                current_price=price,
                price_change_24h_pct=change,
            ))

        return tokens

    async def get_eth_contracts(self, tokens: list) -> dict[str, tuple[str, str]]:
        """Llama /coins/{id} para cada token con coingecko_id y extrae contrato + chain.

        Returns dict[symbol, (contract_address, chain)] where chain is "evm" or "solana".
        """
        result: dict[str, tuple[str, str]] = {}
        tokens_with_id = [t for t in tokens if t.coingecko_id]
        if not tokens_with_id:
            return result

        log.info("exchange_scanner.fetching_contracts", count=len(tokens_with_id))
        async with httpx.AsyncClient() as client:
            for token in tokens_with_id:
                try:
                    resp = await client.get(
                        f"{self._cg_base}/coins/{token.coingecko_id}",
                        params={
                            "localization": "false",
                            "tickers": "false",
                            "market_data": "false",
                            "community_data": "false",
                            "developer_data": "false",
                        },
                        headers=self._cg_headers,
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        platforms = data.get("platforms", {})
                        addr = platforms.get("ethereum") or platforms.get("binance-smart-chain")
                        if addr:
                            result[token.symbol] = (addr, "evm")
                            log.debug("exchange_scanner.contract_found", symbol=token.symbol, chain="evm", addr=addr[:10] + "...")
                        elif platforms.get("solana"):
                            sol_addr = platforms["solana"]
                            result[token.symbol] = (sol_addr, "solana")
                            log.debug("exchange_scanner.contract_found", symbol=token.symbol, chain="solana", addr=sol_addr[:10] + "...")
                    await asyncio.sleep(2.0)  # CoinGecko free tier: ~30 req/min
                except Exception:
                    log.debug("exchange_scanner.contract_fetch_failed", symbol=token.symbol)

        log.info("exchange_scanner.contracts_fetched", found=len(result), queried=len(tokens_with_id))
        return result


def _calc_age_days(atl_date_str: Optional[str]) -> Optional[int]:
    if not atl_date_str:
        return None
    try:
        from datetime import datetime, timezone
        atl_dt = datetime.fromisoformat(atl_date_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - atl_dt
        return delta.days
    except Exception:
        return None
