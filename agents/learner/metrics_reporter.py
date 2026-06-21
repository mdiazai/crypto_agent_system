"""
MetricsReporter: genera y envía el reporte semanal de rendimiento vía Telegram.
"""
import structlog
from telegram import Bot
from telegram.error import TelegramError

from shared.config import settings
from .schemas import TradeMetrics, LearnerRun

log = structlog.get_logger(__name__)


def _bar(ratio: float, length: int = 10) -> str:
    """Barra de progreso ASCII: ████░░░░░░"""
    filled = round(ratio * length)
    return "█" * filled + "░" * (length - filled)


def _quality_emoji(score: float) -> str:
    if score >= 3.5:
        return "🟢"
    if score >= 2.5:
        return "🟡"
    if score >= 1.5:
        return "🟠"
    return "🔴"


class MetricsReporter:
    def __init__(self) -> None:
        self._bot = Bot(token=settings.telegram_bot_token.get_secret_value())
        self._chat_id = settings.telegram_chat_id

    async def send_weekly_report(self, run: LearnerRun) -> None:
        text = self._format_report(run)
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode="HTML",
            )
            log.info("metrics_reporter.weekly_report_sent")
        except TelegramError as e:
            log.error("metrics_reporter.send_error", error=str(e))

    def _format_report(self, run: LearnerRun) -> str:
        m = run.metrics
        lp = m.long_pump
        cl = m.classic

        win_bar = _bar(m.win_rate)
        quality_emoji = _quality_emoji(m.avg_quality_score)

        lines = [
            "📈 <b>REPORTE SEMANAL — Crypto Agent System</b>",
            f"📅 Período: últimos {m.period_days} días",
            "━━━━━━━━━━━━━━━━━",
            "",
            "📊 <b>RENDIMIENTO GLOBAL</b>",
            f"  Trades cerrados: <b>{m.total_trades}</b>",
            f"  Win Rate: <b>{m.win_rate:.1%}</b> {win_bar}",
            f"  P&L promedio: <b>{m.avg_pnl_pct:+.2f}%</b>",
            f"  Calidad entrada: {quality_emoji} <b>{m.avg_quality_score:.2f}/4.0</b>",
            "",
            "🎯 <b>DISTRIBUCIÓN DE CALIDAD</b>",
            f"  🟢 Perfect : {m.perfect_count} trades",
            f"  🔵 Good    : {m.good_count} trades",
            f"  🟡 Early   : {m.early_count} trades",
            f"  🟠 Late    : {m.late_count} trades",
            f"  🔴 Bad     : {m.bad_count} trades",
            "",
        ]

        if lp.total_trades > 0:
            lines += [
                "🚀 <b>LONG PUMP</b>",
                f"  Trades: {lp.total_trades} | WR: {lp.win_rate:.1%}",
                f"  P&L avg: {lp.avg_pnl_pct:+.2f}%",
            ]
        if cl.total_trades > 0:
            lines += [
                "🔀 <b>CLASSIC SQUEEZE</b>",
                f"  Trades: {cl.total_trades} | WR: {cl.win_rate:.1%}",
                f"  P&L avg: {cl.avg_pnl_pct:+.2f}%",
            ]

        lines += [
            "",
            "⚙️ <b>AJUSTE DE PESOS</b>",
            f"  {run.adjustment_reason}",
            "",
        ]

        # Mostrar cambios de pesos relevantes
        deltas = {k: v for k, v in run.weight_delta.items() if abs(v) > 0.05}
        if deltas:
            lines.append("  Cambios significativos:")
            for key, delta in sorted(deltas.items(), key=lambda x: abs(x[1]), reverse=True)[:4]:
                arrow = "↑" if delta > 0 else "↓"
                lines.append(f"    {arrow} {key}: {delta:+.3f}")
        else:
            lines.append("  Sin cambios significativos esta semana.")

        lines += [
            "━━━━━━━━━━━━━━━━━",
            "🤖 <i>Crypto Agent System v1.0</i>",
        ]

        return "\n".join(lines)
