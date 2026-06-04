"""
Cliente Telegram con retry exponencial y soporte para botones inline.
"""
import asyncio
from typing import Optional
import structlog
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.error import TelegramError, RetryAfter, TimedOut

from shared.config import settings
from shared.utils.retry import http_retry

log = structlog.get_logger(__name__)

_TRADINGVIEW_BASE = "https://www.tradingview.com/chart/?symbol="


def _chart_url(symbol: str, exchange: str) -> str:
    """Construye URL de TradingView para el par USDT en el exchange dado."""
    exchange_prefix = {"mexc": "MEXC", "bitget": "BITGET"}.get(exchange.lower(), exchange.upper())
    return f"{_TRADINGVIEW_BASE}{exchange_prefix}:{symbol}USDT"


def _build_keyboard(symbol: str, exchange: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📈 Ver Chart", url=_chart_url(symbol, exchange)),
            InlineKeyboardButton("⚡ Ejecutar", callback_data=f"execute:{symbol}:{exchange}"),
        ]
    ])


class TelegramClient:
    def __init__(self) -> None:
        self._bot = Bot(token=settings.telegram_bot_token.get_secret_value())
        self._chat_id = settings.telegram_chat_id

    async def send_alert(
        self,
        text: str,
        symbol: str,
        exchange: str,
        disable_notification: bool = False,
    ) -> Optional[int]:
        """
        Envía un mensaje de alerta al canal configurado.
        Retorna el message_id de Telegram, o None si falla.
        """
        keyboard = _build_keyboard(symbol, exchange)

        for attempt in range(3):
            try:
                msg: Message = await self._bot.send_message(
                    chat_id=self._chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_notification=disable_notification,
                )
                log.info(
                    "telegram_client.sent",
                    symbol=symbol,
                    message_id=msg.message_id,
                )
                return msg.message_id

            except RetryAfter as e:
                wait = e.retry_after + 1
                log.warning("telegram_client.rate_limit", wait_seconds=wait)
                await asyncio.sleep(wait)

            except TimedOut:
                log.warning("telegram_client.timeout", attempt=attempt + 1)
                await asyncio.sleep(2 ** attempt)

            except TelegramError as e:
                log.error("telegram_client.error", error=str(e))
                return None

        log.error("telegram_client.max_retries_exceeded", symbol=symbol)
        return None

    async def send_text(self, text: str) -> Optional[int]:
        """Envía mensaje de texto plano (para alertas del sistema)."""
        try:
            msg = await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode="HTML",
            )
            return msg.message_id
        except TelegramError as e:
            log.error("telegram_client.send_text_error", error=str(e))
            return None
