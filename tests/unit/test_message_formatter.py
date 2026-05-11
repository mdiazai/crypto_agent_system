import pytest
from datetime import datetime, timezone

from agents.detector.schemas import ScoredToken, PatternBreakdown
from agents.scorer.message_formatter import (
    format_alert,
    _score_emoji,
    _fmt_money,
    _fmt_price,
)


def _scored(**kwargs) -> ScoredToken:
    lp = PatternBreakdown(score=75.0)
    cl = PatternBreakdown(score=40.0)
    defaults = dict(
        symbol="COLLECT",
        exchange="mexc",
        timestamp=datetime.now(timezone.utc),
        long_pump=lp,
        classic_squeeze=cl,
        composite_score=75.0,
        dominant_pattern="long_pump",
        current_price=0.028,
        inflow_4h_usd=2_400_000,
        holder_top10_pct=71.0,
        volume_24h_usd=15_000_000,
        funding_rate=0.008,
        above_alert_threshold=True,
    )
    defaults.update(kwargs)
    return ScoredToken(**defaults)


class TestScoreEmoji:
    def test_red_above_90(self):
        assert _score_emoji(90) == "🔴"
        assert _score_emoji(95) == "🔴"

    def test_orange_80_to_89(self):
        assert _score_emoji(80) == "🟠"
        assert _score_emoji(89) == "🟠"

    def test_yellow_70_to_79(self):
        assert _score_emoji(70) == "🟡"
        assert _score_emoji(79) == "🟡"

    def test_white_below_70(self):
        assert _score_emoji(69) == "⚪"


class TestFmtMoney:
    def test_millions(self):
        assert "M" in _fmt_money(2_400_000)
        assert "2.40" in _fmt_money(2_400_000)

    def test_thousands(self):
        assert "K" in _fmt_money(500_000)

    def test_none(self):
        assert _fmt_money(None) == "N/D"

    def test_small(self):
        assert "$" in _fmt_money(999)


class TestFmtPrice:
    def test_large_price(self):
        assert "$1.2345" in _fmt_price(1.2345)

    def test_small_price(self):
        result = _fmt_price(0.00001234)
        assert "0.00001234" in result

    def test_medium_price(self):
        result = _fmt_price(0.0284)
        assert "0.028400" in result


class TestFormatAlert:
    def test_contains_symbol(self):
        msg = format_alert(_scored())
        assert "COLLECT" in msg

    def test_contains_score(self):
        msg = format_alert(_scored(composite_score=87.0))
        assert "87" in msg

    def test_contains_pattern(self):
        msg = format_alert(_scored(dominant_pattern="long_pump"))
        assert "Long Pump" in msg

    def test_contains_llm_analysis_when_present(self):
        msg = format_alert(_scored(
            llm_validated=True,
            llm_analysis="Alta concentración y flujo masivo detectado.",
        ))
        assert "Análisis IA" in msg
        assert "concentración" in msg

    def test_no_llm_section_when_absent(self):
        msg = format_alert(_scored(llm_validated=False, llm_analysis=None))
        assert "Análisis IA" not in msg

    def test_html_tags_present(self):
        msg = format_alert(_scored())
        assert "<b>" in msg
        assert "</b>" in msg

    def test_classic_pattern_label(self):
        msg = format_alert(_scored(dominant_pattern="classic"))
        assert "Squeeze" in msg
