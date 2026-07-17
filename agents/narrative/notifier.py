"""
Notificador Telegram del Narrative Swing Module, con glosario educativo.
Usa la librería python-telegram-bot (clase Bot), igual que
agents/scorer/telegram_client.py — no httpx crudo.
"""
from typing import Optional

import structlog
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.error import TelegramError, RetryAfter, TimedOut
import asyncio

from shared.config import settings
from .scorer import NarrativeScore

log = structlog.get_logger(__name__)


def _build_message(symbol: str, score: NarrativeScore, mode: str) -> str:
    emoji = "🎯" if mode == "auto" else "❓"
    action = "Entrada automática ejecutada" if mode == "auto" else "¿Aprobar entrada?"

    lines = [
        "🌊 <b>NARRATIVE SWING</b>",
        f"{emoji} <b>SEÑAL DETECTADA — {symbol}</b>",
        f"Score: {score.combined:.0f}/100",
        "",
        f"📊 Señales: {score.narrative_desc}",
        "",
        f"Narrativa: {score.narrative_score:.0f}/35 pts",
        f"Onchain:   {score.onchain_score:.0f}/40 pts",
        f"Técnico:   {score.technical_score:.0f}/25 pts",
        "",
        "🎓 <b>Glosario de esta señal:</b>",
    ]
    for term, explanation in score.educational_glossary.items():
        lines.append(f"• <b>{term}</b>: {explanation}")

    lines.append("")
    lines.append(action)
    return "\n".join(lines)


class NarrativeNotifier:
    def __init__(self) -> None:
        self._bot = Bot(token=settings.telegram_bot_token.get_secret_value())
        self._chat_id = settings.telegram_chat_id

    async def send_high_confidence(self, symbol: str, score: NarrativeScore) -> Optional[int]:
        """Score >= NARRATIVE_ALERT_THRESHOLD: entrada automática + notificación informativa."""
        text = _build_message(symbol, score, mode="auto")
        return await self._send(text)

    async def send_consult_marce(self, symbol: str, score: NarrativeScore) -> Optional[int]:
        """Score entre NARRATIVE_CONSULT_THRESHOLD y ALERT_THRESHOLD: consulta con botones."""
        text = _build_message(symbol, score, mode="consult")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Aprobar entrada", callback_data=f"nsm_approve_{symbol}"),
            InlineKeyboardButton("❌ Rechazar", callback_data=f"nsm_reject_{symbol}"),
        ]])
        return await self._send(text, reply_markup=keyboard)

    async def _send(self, text: str, reply_markup=None) -> Optional[int]:
        for attempt in range(3):
            try:
                msg: Message = await self._bot.send_message(
                    chat_id=self._chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                log.info("narrative_notifier.sent", message_id=msg.message_id)
                return msg.message_id
            except RetryAfter as e:
                wait = e.retry_after + 1
                log.warning("narrative_notifier.rate_limit", wait_seconds=wait)
                await asyncio.sleep(wait)
            except TimedOut:
                log.warning("narrative_notifier.timeout", attempt=attempt + 1)
                await asyncio.sleep(2 ** attempt)
            except TelegramError as e:
                log.error("narrative_notifier.error", error=str(e))
                return None

        log.error("narrative_notifier.max_retries_exceeded")
        return None
