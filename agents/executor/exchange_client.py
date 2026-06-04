"""
Wrapper CCXT para MEXC y Bitget.
PAPER_TRADING=true → simula órdenes con el precio de mercado actual.
PAPER_TRADING=false → ejecuta órdenes reales (requiere API keys con permisos de trading).
"""
import asyncio
import structlog
import ccxt.async_support as ccxt_async

from shared.config import settings
from shared.utils.retry import exchange_retry
from .schemas import OrderResult

log = structlog.get_logger(__name__)

_EXCHANGE_CONFIGS = {
    "mexc": {
        "apiKey": lambda: settings.mexc_api_key.get_secret_value(),
        "secret": lambda: settings.mexc_secret.get_secret_value(),
        "enableRateLimit": True,
    },
    "bitget": {
        "apiKey": lambda: settings.bitget_api_key.get_secret_value(),
        "secret": lambda: settings.bitget_secret.get_secret_value(),
        "password": lambda: settings.bitget_passphrase.get_secret_value(),
        "enableRateLimit": True,
    },
}


class ExchangeClient:
    def __init__(self) -> None:
        self._exchanges: dict[str, ccxt_async.Exchange] = {}

    def _build_config(self, exchange_id: str) -> dict:
        cfg = _EXCHANGE_CONFIGS.get(exchange_id, {})
        return {k: (v() if callable(v) else v) for k, v in cfg.items()}

    async def _get(self, exchange_id: str) -> ccxt_async.Exchange:
        if exchange_id not in self._exchanges:
            cls = getattr(ccxt_async, exchange_id, None)
            if cls is None:
                raise ValueError(f"Exchange no soportado: {exchange_id}")
            self._exchanges[exchange_id] = cls(self._build_config(exchange_id))
        return self._exchanges[exchange_id]

    async def close(self) -> None:
        for ex in self._exchanges.values():
            try:
                await ex.close()
            except Exception:
                pass
        self._exchanges.clear()

    # ── Precio actual ─────────────────────────────────────────────────────────

    @exchange_retry
    async def get_price(self, symbol: str, exchange_id: str) -> float:
        ex = await self._get(exchange_id)
        ticker = await ex.fetch_ticker(f"{symbol}/USDT")
        return float(ticker["last"])

    # ── Compra ────────────────────────────────────────────────────────────────

    async def buy(self, symbol: str, capital_usd: float, exchange_id: str) -> OrderResult:
        if settings.paper_trading:
            return await self._paper_buy(symbol, capital_usd, exchange_id)
        return await self._real_buy(symbol, capital_usd, exchange_id)

    async def _paper_buy(self, symbol: str, capital_usd: float, exchange_id: str) -> OrderResult:
        try:
            price = await self.get_price(symbol, exchange_id)
            qty = capital_usd / price
            log.info(
                "executor.paper_buy",
                symbol=symbol, exchange=exchange_id,
                price=price, qty=qty, capital=capital_usd,
            )
            return OrderResult(
                success=True, price=price, quantity=qty,
                cost_usd=capital_usd, order_id=f"paper-buy-{symbol}", is_paper=True,
            )
        except Exception as e:
            log.error("executor.paper_buy_error", symbol=symbol, error=str(e))
            return OrderResult(success=False, error=str(e), is_paper=True)

    @exchange_retry
    async def _real_buy(self, symbol: str, capital_usd: float, exchange_id: str) -> OrderResult:
        try:
            ex = await self._get(exchange_id)
            pair = f"{symbol}/USDT"
            ticker = await ex.fetch_ticker(pair)
            price = float(ticker["last"])
            qty = capital_usd / price

            order = await ex.create_market_buy_order(pair, qty)
            filled_price = float(order.get("average") or order.get("price") or price)
            filled_qty = float(order.get("filled") or qty)

            log.info(
                "executor.real_buy",
                symbol=symbol, exchange=exchange_id,
                price=filled_price, qty=filled_qty,
                order_id=order.get("id"),
            )
            return OrderResult(
                success=True, price=filled_price, quantity=filled_qty,
                cost_usd=filled_price * filled_qty,
                order_id=str(order.get("id")), is_paper=False,
            )
        except Exception as e:
            log.error("executor.real_buy_error", symbol=symbol, error=str(e))
            return OrderResult(success=False, error=str(e), is_paper=False)

    # ── Venta ─────────────────────────────────────────────────────────────────

    async def sell(self, symbol: str, quantity: float, exchange_id: str) -> OrderResult:
        if settings.paper_trading:
            return await self._paper_sell(symbol, quantity, exchange_id)
        return await self._real_sell(symbol, quantity, exchange_id)

    async def _paper_sell(self, symbol: str, quantity: float, exchange_id: str) -> OrderResult:
        try:
            price = await self.get_price(symbol, exchange_id)
            log.info(
                "executor.paper_sell",
                symbol=symbol, exchange=exchange_id,
                price=price, qty=quantity,
            )
            return OrderResult(
                success=True, price=price, quantity=quantity,
                cost_usd=price * quantity, order_id=f"paper-sell-{symbol}", is_paper=True,
            )
        except Exception as e:
            log.error("executor.paper_sell_error", symbol=symbol, error=str(e))
            return OrderResult(success=False, error=str(e), is_paper=True)

    @exchange_retry
    async def _real_sell(self, symbol: str, quantity: float, exchange_id: str) -> OrderResult:
        try:
            ex = await self._get(exchange_id)
            pair = f"{symbol}/USDT"
            order = await ex.create_market_sell_order(pair, quantity)
            filled_price = float(order.get("average") or order.get("price") or 0)
            filled_qty = float(order.get("filled") or quantity)

            log.info(
                "executor.real_sell",
                symbol=symbol, exchange=exchange_id,
                price=filled_price, qty=filled_qty, order_id=order.get("id"),
            )
            return OrderResult(
                success=True, price=filled_price, quantity=filled_qty,
                cost_usd=filled_price * filled_qty,
                order_id=str(order.get("id")), is_paper=False,
            )
        except Exception as e:
            log.error("executor.real_sell_error", symbol=symbol, error=str(e))
            return OrderResult(success=False, error=str(e), is_paper=False)
