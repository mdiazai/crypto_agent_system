"""
DataFetcher: obtiene precio, orderbook, futuros y on-chain en paralelo para un token.
"""
import asyncio
from typing import Optional
import structlog
import ccxt.async_support as ccxt_async

from .schemas import TokenSnapshot
from .onchain_client import OnchainClient

log = structlog.get_logger(__name__)

# Límite de concurrencia para no saturar APIs de exchange
_SEMAPHORE = asyncio.Semaphore(8)


class DataFetcher:
    def __init__(self) -> None:
        self._onchain = OnchainClient()
        self._exchanges: dict[str, ccxt_async.Exchange] = {}

    async def _get_exchange(self, exchange_id: str) -> ccxt_async.Exchange:
        if exchange_id not in self._exchanges:
            cls = getattr(ccxt_async, exchange_id, None)
            if cls is None:
                raise ValueError(f"Unknown exchange: {exchange_id}")
            self._exchanges[exchange_id] = cls({"enableRateLimit": True})
        return self._exchanges[exchange_id]

    async def close(self) -> None:
        for ex in self._exchanges.values():
            try:
                await ex.close()
            except Exception:
                pass
        self._exchanges.clear()

    # ── Sub-fetchers ──────────────────────────────────────────────────────────

    async def _fetch_ticker(
        self, exchange: ccxt_async.Exchange, pair: str
    ) -> Optional[dict]:
        try:
            return await exchange.fetch_ticker(pair)
        except Exception as e:
            log.warning("data_fetcher.ticker_error", pair=pair, error=str(e))
            return None

    async def _fetch_orderbook(
        self, exchange: ccxt_async.Exchange, pair: str
    ) -> Optional[dict]:
        try:
            return await exchange.fetch_order_book(pair, limit=5)
        except Exception as e:
            log.warning("data_fetcher.orderbook_error", pair=pair, error=str(e))
            return None

    async def _fetch_funding_rate(
        self, exchange: ccxt_async.Exchange, pair: str
    ) -> Optional[dict]:
        try:
            if exchange.has.get("fetchFundingRate"):
                return await exchange.fetch_funding_rate(pair)
        except Exception:
            pass
        return None

    async def _fetch_open_interest(
        self, exchange: ccxt_async.Exchange, pair: str
    ) -> Optional[dict]:
        try:
            if exchange.has.get("fetchOpenInterest"):
                return await exchange.fetch_open_interest(pair)
        except Exception:
            pass
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _calc_spread_pct(orderbook: Optional[dict]) -> Optional[float]:
        if not orderbook:
            return None
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        if not bids or not asks:
            return None
        best_bid = bids[0][0]
        best_ask = asks[0][0]
        if best_bid <= 0:
            return None
        mid = (best_bid + best_ask) / 2
        return ((best_ask - best_bid) / mid) * 100

    @staticmethod
    def _safe(value, default=None):
        return value if value is not None else default

    # ── Main entry ────────────────────────────────────────────────────────────

    _FALLBACK = {"mexc": "bitget", "bitget": "mexc"}

    async def fetch_all(self, symbol: str, exchange_id: str, contract_address: Optional[str] = None) -> Optional[TokenSnapshot]:
        pair = f"{symbol}/USDT"
        errors: list[str] = []

        # ── Onchain calls (independientes del exchange) ───────────────────────
        (
            cq_inflow,
            ls_ratio,
            cg_oi,
            holder_count,
        ) = await asyncio.gather(
            self._onchain.get_exchange_inflow(symbol),
            self._onchain.get_long_short_ratio(symbol),
            self._onchain.get_open_interest(symbol),
            self._onchain.get_holder_count(contract_address),
            return_exceptions=False,
        )

        # ── Exchange calls con fallback ───────────────────────────────────────
        ticker = orderbook = funding = open_interest = None
        for attempt_exchange in [exchange_id, self._FALLBACK.get(exchange_id, "")]:
            if not attempt_exchange:
                break
            async with _SEMAPHORE:
                try:
                    exchange = await self._get_exchange(attempt_exchange)
                except ValueError as e:
                    log.error("data_fetcher.unknown_exchange", error=str(e))
                    continue

                (
                    ticker,
                    orderbook,
                    funding,
                    open_interest,
                ) = await asyncio.gather(
                    self._fetch_ticker(exchange, pair),
                    self._fetch_orderbook(exchange, pair),
                    self._fetch_funding_rate(exchange, pair),
                    self._fetch_open_interest(exchange, pair),
                    return_exceptions=False,
                )

            if ticker is not None:
                if attempt_exchange != exchange_id:
                    log.info("data_fetcher.fallback_exchange_used", symbol=symbol, fallback=attempt_exchange)
                exchange_id = attempt_exchange
                break

        if ticker is None:
            log.warning("data_fetcher.no_ticker", symbol=symbol, exchange=exchange_id)
            return None

        current_price = self._safe(ticker.get("last"), 0.0)
        if not current_price:
            return None

        volume_usd = self._safe(ticker.get("quoteVolume"))

        # Inflow: CryptoQuant si disponible, si no proxy vol×15%
        inflow_4h = cq_inflow
        if inflow_4h is None and volume_usd:
            inflow_4h = volume_usd * 0.15

        # OI: Coinglass tiene prioridad; fallback a CCXT
        oi_usd = cg_oi or (open_interest.get("openInterestValue") if open_interest else None)

        onchain_available = ls_ratio is not None or cg_oi is not None or cq_inflow is not None

        snapshot = TokenSnapshot(
            symbol=symbol,
            exchange=exchange_id,
            current_price=current_price,
            price_change_1h_pct=None,
            price_change_24h_pct=self._safe(ticker.get("percentage")),
            volume_24h_usd=volume_usd,
            bid_ask_spread_pct=self._calc_spread_pct(orderbook),
            inflow_1h_usd=None,
            inflow_4h_usd=inflow_4h,
            inflow_24h_usd=volume_usd,
            holder_top10_pct=None,
            total_holders=holder_count,
            funding_rate=funding.get("fundingRate") if funding else None,
            open_interest_usd=oi_usd,
            long_short_ratio=ls_ratio,
            onchain_available=onchain_available,
            fetch_errors=errors,
        )

        log.debug(
            "data_fetcher.snapshot_ready",
            symbol=symbol,
            price=current_price,
            onchain=onchain_available,
        )
        return snapshot
