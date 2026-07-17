"""
Cliente técnico spot vía CCXT — RSI diario y ratio de volumen.
No existe un cálculo de RSI reutilizable en el resto del Crypto Agent
(los otros agentes usan funding rate / open interest de derivados, no RSI),
así que se implementa acá con velas diarias públicas de MEXC (sin API key).
"""
from dataclasses import dataclass
from typing import Optional

import ccxt.async_support as ccxt_async
import structlog

log = structlog.get_logger(__name__)

_PAIR_SUFFIX = "/USDT"
_RSI_PERIOD = 14
_OHLCV_LIMIT = 30  # días — suficiente para RSI-14 + ratio de volumen 7d


@dataclass
class TechnicalSnapshot:
    symbol: str
    rsi_1d: Optional[float] = None
    volume_ratio: Optional[float] = None
    price_usd: Optional[float] = None
    volume_24h_usd: Optional[float] = None


def _calc_rsi(closes: list[float], period: int = _RSI_PERIOD) -> Optional[float]:
    """RSI con suavizado de Wilder. None si no hay suficientes velas."""
    if len(closes) < period + 1:
        return None

    deltas = [closes[i + 1] - closes[i] for i in range(len(closes) - 1)]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


class TechnicalClient:
    def __init__(self) -> None:
        self._exchange = ccxt_async.mexc({"enableRateLimit": True})

    async def close(self) -> None:
        try:
            await self._exchange.close()
        except Exception:
            pass

    async def get_snapshot(self, symbol: str) -> TechnicalSnapshot:
        pair = f"{symbol}{_PAIR_SUFFIX}"
        try:
            candles = await self._exchange.fetch_ohlcv(pair, timeframe="1d", limit=_OHLCV_LIMIT)
        except Exception as e:
            log.warning("technical_client.ohlcv_error", symbol=symbol, error=str(e))
            return TechnicalSnapshot(symbol=symbol)

        if not candles or len(candles) < 2:
            return TechnicalSnapshot(symbol=symbol)

        closes = [c[4] for c in candles]
        volumes = [c[5] for c in candles]

        rsi = _calc_rsi(closes)

        volume_ratio = None
        if len(volumes) >= 8:
            prev_7d_avg = sum(volumes[-8:-1]) / 7
            if prev_7d_avg > 0:
                volume_ratio = volumes[-1] / prev_7d_avg

        return TechnicalSnapshot(
            symbol=symbol,
            rsi_1d=rsi,
            volume_ratio=volume_ratio,
            price_usd=closes[-1],
            volume_24h_usd=closes[-1] * volumes[-1] if closes and volumes else None,
        )
