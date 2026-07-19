import hashlib
import json
import re

import httpx
import redis.asyncio as aioredis
import structlog

from shared.config import settings

log = structlog.get_logger(__name__)

REDIS_PENDING_KEY = "smartdevops:pending_command"
REDIS_TTL = 3600  # 1 hora

REDIS_COOLDOWN_PREFIX = "smartdevops:alert_cooldown:"
ALERT_COOLDOWN_SECONDS = 3600  # no reenviar la misma alerta más de 1 vez por hora

_SEVERITY_EMOJI = {"ok": "✅", "warn": "⚠️", "critical": "🚨"}

_MD_SPECIAL = re.compile(r'([_*\[\]()~`>#+=|{}.!\-\\])')


def _esc(text: str) -> str:
    """Escape all MarkdownV2 special characters in plain text."""
    return _MD_SPECIAL.sub(r'\\\1', text)


def _esc_code(text: str) -> str:
    """Escape only backtick and backslash inside a code span."""
    return text.replace('\\', '\\\\').replace('`', '\\`')


class TelegramNotifier:
    def __init__(self) -> None:
        self._base_url = (
            f"https://api.telegram.org/bot"
            f"{settings.smartdevops_bot_token.get_secret_value()}"
        )
        self._chat_id = settings.telegram_chat_id

    async def has_pending_command(self) -> bool:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            val = await client.get(REDIS_PENDING_KEY)
            return val is not None
        finally:
            await client.aclose()

    async def store_pending_command(self, command: str) -> None:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            await client.setex(REDIS_PENDING_KEY, REDIS_TTL, command)
            log.info("telegram_notifier.command_stored", ttl=REDIS_TTL)
        finally:
            await client.aclose()

    async def send_ok_heartbeat(self, diagnosis: str, run_count: int) -> None:
        """Send a brief OK ping every N cycles (avoid silent running)."""
        text = f"🤖 *SmartDevops* ✅\n\n_Ciclo \\#{run_count}: sistema nominal_\n_{_esc(diagnosis[:200])}_"
        await self._send_message(text)

    @staticmethod
    def _alert_hash(severity: str, diagnosis: str, fix_command: str | None) -> str:
        # fix_command es más estable entre ciclos que diagnosis (que Claude
        # redacta de nuevo cada vez) — es la mejor señal de "mismo problema".
        identity = fix_command or diagnosis
        raw = f"{severity}:{identity}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    async def _is_in_cooldown(self, alert_hash: str) -> bool:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            return await client.exists(REDIS_COOLDOWN_PREFIX + alert_hash) == 1
        finally:
            await client.aclose()

    async def _mark_alert_sent(self, alert_hash: str) -> None:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            await client.setex(
                REDIS_COOLDOWN_PREFIX + alert_hash, ALERT_COOLDOWN_SECONDS, "1"
            )
        finally:
            await client.aclose()

    async def send_proposal(
        self, severity: str, diagnosis: str, fix_command: str | None
    ) -> None:
        alert_hash = self._alert_hash(severity, diagnosis, fix_command)
        if await self._is_in_cooldown(alert_hash):
            log.info(
                "telegram_notifier.alert_suppressed_cooldown",
                severity=severity,
                alert_hash=alert_hash,
            )
            return

        emoji = _SEVERITY_EMOJI.get(severity, "⚠️")
        lines = [
            f"🤖 *SmartDevops Diagnosis* {emoji}",
            "",
            f"*Severidad:* {_esc(severity.upper())}",
            f"*Diagnóstico:* {_esc(diagnosis)}",
        ]

        if fix_command:
            lines += [
                "",
                "*Comando propuesto:*",
                f"`{_esc_code(fix_command[:400])}`",
                "",
                "¿Ejecutar?",
            ]
            reply_markup = json.dumps({
                "inline_keyboard": [[
                    {"text": "✅ Aprobar", "callback_data": "sd_approve"},
                    {"text": "❌ Ignorar", "callback_data": "sd_ignore"},
                ]]
            })
            await self.store_pending_command(fix_command)
        else:
            lines += ["", "_No hay fix automático disponible para este problema\\._"]
            reply_markup = None

        await self._send_message("\n".join(lines), reply_markup=reply_markup)
        await self._mark_alert_sent(alert_hash)

    async def _send_message(
        self, text: str, reply_markup: str | None = None
    ) -> None:
        payload: dict = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{self._base_url}/sendMessage", json=payload)
            if not r.is_success:
                log.warning(
                    "telegram_notifier.send_failed",
                    status=r.status_code,
                    body=r.text[:200],
                )
            else:
                log.info("telegram_notifier.sent", severity_snippet=text[:60])
