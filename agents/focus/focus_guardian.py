from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

ENV_PATH = Path("/opt/11mkeys_lab/.env")
load_dotenv(ENV_PATH)

FOCUS_BOT_TOKEN = os.environ["FOCUS_BOT_TOKEN"]
DATABASE_URL    = os.environ["DATABASE_URL"]
MARCE_CHAT_ID   = int(os.environ.get("FOCUS_CHAT_ID", "6517856768"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("focus_guardian")
logging.getLogger("httpx").setLevel(logging.WARNING)


# ── DB ───────────────────────────────────────────────────────────────────────

async def init_db_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=3)


async def insert_checkin(
    pool: asyncpg.Pool,
    fecha: date,
    tipo: str,
    proyecto: str | None,
    resultado: str,
    detalle: str | None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO focus_checkins
                (fecha, tipo, proyecto_declarado, resultado, detalle)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (fecha, tipo) DO UPDATE
                SET proyecto_declarado = EXCLUDED.proyecto_declarado,
                    resultado          = EXCLUDED.resultado,
                    detalle            = EXCLUDED.detalle,
                    created_at         = now()
            """,
            fecha, tipo, proyecto, resultado, detalle,
        )


async def fetch_recent(pool: asyncpg.Pool, limit: int = 7) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT fecha, tipo, proyecto_declarado, resultado, detalle
            FROM focus_checkins
            ORDER BY fecha DESC, tipo DESC
            LIMIT $1
            """,
            limit,
        )


# ── Scheduled jobs ───────────────────────────────────────────────────────────

async def send_morning_checkin(application: Application) -> None:
    logger.info("Check-in mañana — enviando pregunta")
    application.bot_data["morning_pending"] = True
    application.bot_data["morning_date"]    = date.today()
    await application.bot.send_message(
        chat_id=MARCE_CHAT_ID,
        text=(
            "🌅 *Check-in mañana*\n\n"
            "¿En qué proyecto trabajás hoy?\n"
            "Respondé con el nombre."
        ),
        parse_mode="Markdown",
    )


async def check_morning_timeout(application: Application) -> None:
    """14:00 UTC — 2 h después del check-in. Sin respuesta → sin_respuesta."""
    if not application.bot_data.get("morning_pending"):
        return
    if application.bot_data.get("morning_date") != date.today():
        return
    logger.info("Timeout check-in mañana — registrando sin_respuesta")
    await insert_checkin(
        application.bot_data["pool"],
        date.today(), "manana", None, "sin_respuesta", "timeout 2h",
    )
    application.bot_data["morning_pending"] = False
    await application.bot.send_message(
        chat_id=MARCE_CHAT_ID,
        text="⏰ No recibí check-in de mañana. Registré *sin_respuesta*.",
        parse_mode="Markdown",
    )


async def send_evening_checkin(application: Application) -> None:
    logger.info("Check-in noche — enviando pregunta")
    application.bot_data["evening_pending"] = True
    application.bot_data["evening_date"]    = date.today()
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Avancé",    callback_data="fg_avance"),
        InlineKeyboardButton("❌ Me desvié", callback_data="fg_desvio"),
    ]])
    await application.bot.send_message(
        chat_id=MARCE_CHAT_ID,
        text="🌙 *Check-in noche*\n\n¿Cómo fue el día?",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ── Handlers ─────────────────────────────────────────────────────────────────

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != MARCE_CHAT_ID:
        return
    text = (update.message.text or "").strip()

    # Detalle post-botón noche
    if context.bot_data.get("evening_wait_detail"):
        resultado = context.bot_data.pop("evening_resultado", "avance")
        fecha     = context.bot_data.pop("evening_date", date.today())
        proyecto  = context.bot_data.get("morning_proyecto")
        detalle   = None if text.lower() == "/skip" else text
        context.bot_data["evening_wait_detail"] = False
        context.bot_data["evening_pending"]     = False
        await insert_checkin(
            context.bot_data["pool"], fecha, "noche", proyecto, resultado, detalle,
        )
        await update.message.reply_text("✅ Check-in noche guardado.")
        return

    # Respuesta al check-in de mañana
    if context.bot_data.get("morning_pending"):
        if context.bot_data.get("morning_date") == date.today():
            await insert_checkin(
                context.bot_data["pool"],
                date.today(), "manana", text, "avance", None,
            )
            context.bot_data["morning_pending"]  = False
            context.bot_data["morning_proyecto"] = text
            await update.message.reply_text(
                f"✅ Check-in mañana guardado.\nProyecto: *{text}*",
                parse_mode="Markdown",
            )
            return

    await update.message.reply_text(
        "Sin check-in pendiente. Usá /historial para ver registros."
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not query.data.startswith("fg_") or update.effective_chat.id != MARCE_CHAT_ID:
        return
    resultado = "avance" if query.data == "fg_avance" else "desvio"
    context.bot_data["evening_resultado"]   = resultado
    context.bot_data["evening_wait_detail"] = True
    emoji = "✅" if resultado == "avance" else "❌"
    await query.edit_message_text(
        f"{emoji} Registré: *{resultado}*\n\n"
        "¿Querés agregar un detalle? (escribí el texto o /skip)",
        parse_mode="Markdown",
    )


async def cmd_historial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != MARCE_CHAT_ID:
        return
    rows = await fetch_recent(context.bot_data["pool"])
    if not rows:
        await update.message.reply_text("Sin check-ins registrados todavía.")
        return
    lines = ["📅 *Últimos check-ins*", ""]
    for r in rows:
        emoji    = "🌅" if r["tipo"] == "manana" else "🌙"
        proyecto = r["proyecto_declarado"] or "—"
        detalle  = f" — {r['detalle']}" if r["detalle"] else ""
        lines.append(f"{emoji} {r['fecha']} | {r['resultado']} | {proyecto}{detalle}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Lifecycle ────────────────────────────────────────────────────────────────

async def _post_init(application: Application) -> None:
    application.bot_data["pool"]               = await init_db_pool()
    application.bot_data["morning_pending"]     = False
    application.bot_data["evening_pending"]     = False
    application.bot_data["evening_wait_detail"] = False

    scheduler = AsyncIOScheduler(timezone="UTC")
    # 09:00 Uruguay = 12:00 UTC
    scheduler.add_job(send_morning_checkin,  "cron", hour=12, minute=0, args=[application], id="morning")
    # timeout 2h = 14:00 UTC
    scheduler.add_job(check_morning_timeout, "cron", hour=14, minute=0, args=[application], id="timeout")
    # 21:00 Uruguay = 00:00 UTC día siguiente
    scheduler.add_job(send_evening_checkin,  "cron", hour=0,  minute=0, args=[application], id="evening")
    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    logger.info("Scheduler: mañana 12:00 UTC | timeout 14:00 UTC | noche 00:00 UTC")


async def _post_shutdown(application: Application) -> None:
    s = application.bot_data.get("scheduler")
    if s:
        s.shutdown(wait=False)
    p = application.bot_data.get("pool")
    if p:
        await p.close()


def main() -> None:
    app = (
        Application.builder()
        .token(FOCUS_BOT_TOKEN)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("historial", cmd_historial))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    logger.info("Focus Guardian arrancando…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
