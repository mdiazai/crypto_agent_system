"""
Formatea mensajes ricos para Telegram a partir de un ScoredToken.
Usa HTML parse_mode — soportado nativamente por Telegram Bot API.
"""
from typing import Optional
from agents.detector.schemas import ScoredToken


def format_alert(scored: ScoredToken) -> str:
    score_emoji = _score_emoji(scored.composite_score)
    pattern_label = _pattern_label(scored.dominant_pattern)
    inflow_str = _fmt_money(scored.inflow_4h_usd)
    if scored.holder_top10_pct:
        src = f" ({scored.holder_source})" if scored.holder_source else ""
        holder_str = f"{scored.holder_top10_pct:.1f}%{src}"
    else:
        holder_str = "N/D"
    price_str = _fmt_price(scored.current_price)
    volume_str = _fmt_money(scored.volume_24h_usd)

    lines = [
        "⚡ <b>CRIMINAL PUMPS</b>",
        "🚨 <b>PUMP SIGNAL DETECTADO</b>",
        "━━━━━━━━━━━━━━━━━",
        f"🪙 Token: <b>${scored.symbol}</b>",
        f"📊 Score: <b>{scored.composite_score:.0f}/100</b> {score_emoji}",
        f"🎯 Patrón: <b>{pattern_label}</b>",
        f"💰 Precio: <code>{price_str}</code>",
        f"📥 Inflow 4h: <b>{inflow_str}</b>",
        f"📊 Vol 24h: {volume_str}",
        f"👥 Holders TOP10: <b>{holder_str}</b>",
    ]

    if scored.funding_rate is not None:
        funding_emoji = "🐂" if scored.funding_rate >= 0 else "🐻"
        lines.append(f"📉 Funding rate: {scored.funding_rate:.4f}% {funding_emoji}")

    lines.append("━━━━━━━━━━━━━━━━━")

    if scored.llm_validated and scored.llm_analysis:
        lines.append(f"🤖 <i>Análisis IA: {scored.llm_analysis}</i>")

    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc).strftime("%H:%M UTC")
    lines.append(f"⏰ Detectado: {now_utc}")
    lines.append(f"🏦 Exchange: {scored.exchange.upper()}")

    return "\n".join(lines)


def format_dedup_skip(symbol: str, last_sent_minutes_ago: int) -> str:
    return (
        f"⏭ {symbol} ya alertado hace {last_sent_minutes_ago} min — omitiendo duplicado."
    )


def format_system_alert(title: str, body: str) -> str:
    return f"⚡ <b>CRIMINAL PUMPS</b>\n⚠️ <b>{title}</b>\n{body}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_emoji(score: float) -> str:
    if score >= 90:
        return "🔴"
    if score >= 80:
        return "🟠"
    if score >= 70:
        return "🟡"
    return "⚪"


def _pattern_label(pattern: str) -> str:
    return {
        "long_pump": "Long Pump 🚀",
        "classic": "Classic Squeeze 🔀",
        "unknown": "Desconocido",
    }.get(pattern, pattern)


def _fmt_money(value: Optional[float]) -> str:
    if value is None:
        return "N/D"
    if value >= 1_000_000:
        return f"+${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"+${value / 1_000:.1f}K"
    return f"+${value:.0f}"


def _fmt_price(price: float) -> str:
    if price >= 1:
        return f"${price:.4f}"
    if price >= 0.01:
        return f"${price:.6f}"
    return f"${price:.8f}"
