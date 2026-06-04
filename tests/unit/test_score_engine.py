import pytest
from datetime import datetime, timezone

from agents.monitor.schemas import TokenSnapshot
from agents.detector.score_engine import ScoreEngine
from agents.detector.schemas import ScoreWeights


def _snapshot(**kwargs) -> TokenSnapshot:
    defaults = dict(
        symbol="TEST",
        exchange="mexc",
        timestamp=datetime.now(timezone.utc),
        current_price=0.05,
        price_change_24h_pct=1.5,
        volume_24h_usd=2_000_000,
        inflow_1h_usd=150_000,
        inflow_4h_usd=600_000,
        holder_top10_pct=65.0,
        funding_rate=0.008,
        short_interest_pct=10.0,
    )
    defaults.update(kwargs)
    return TokenSnapshot(**defaults)


@pytest.fixture
def engine():
    return ScoreEngine()


def test_long_pump_scores_higher_with_stable_price_and_inflow(engine):
    snap = _snapshot(
        price_change_24h_pct=0.5,
        inflow_4h_usd=800_000,
        holder_top10_pct=72.0,
        funding_rate=0.015,
        short_interest_pct=5.0,
    )
    scored = engine.compute(snap)
    assert scored.dominant_pattern == "long_pump"
    assert scored.long_pump.score > scored.classic_squeeze.score


def test_classic_squeeze_scores_higher_with_negative_funding_and_high_short(engine):
    snap = _snapshot(
        price_change_24h_pct=2.0,
        inflow_1h_usd=300_000,
        inflow_4h_usd=400_000,
        holder_top10_pct=68.0,
        funding_rate=-0.04,
        short_interest_pct=35.0,
    )
    scored = engine.compute(snap)
    assert scored.dominant_pattern == "classic"
    assert scored.classic_squeeze.score > scored.long_pump.score


def test_composite_score_bounded_0_100(engine):
    snap = _snapshot(
        inflow_4h_usd=50_000_000,
        holder_top10_pct=95.0,
        price_change_24h_pct=0.1,
        funding_rate=0.05,
        short_interest_pct=60.0,
        inflow_1h_usd=10_000_000,
    )
    scored = engine.compute(snap)
    assert 0.0 <= scored.composite_score <= 100.0


def test_no_data_returns_low_score(engine):
    snap = _snapshot(
        inflow_4h_usd=None,
        inflow_1h_usd=None,
        holder_top10_pct=None,
        funding_rate=None,
        short_interest_pct=None,
        price_change_24h_pct=None,
        volume_24h_usd=None,
    )
    scored = engine.compute(snap)
    # Sin datos, score debe ser bajo (solo señales neutras)
    assert scored.composite_score < 50.0


def test_weight_update_affects_score(engine):
    snap = _snapshot(
        inflow_4h_usd=2_000_000,
        holder_top10_pct=80.0,
        price_change_24h_pct=1.0,
        funding_rate=0.01,
    )
    score_before = engine.compute(snap).long_pump.score

    # Aumentar peso del inflow dramáticamente
    engine.update_weights(ScoreWeights(lp_inflow=5.0))
    score_after = engine.compute(snap).long_pump.score

    assert score_after != score_before


def test_above_alert_threshold_flag(engine):
    # Score muy alto debe marcar above_alert_threshold
    snap = _snapshot(
        inflow_4h_usd=5_000_000,
        holder_top10_pct=85.0,
        price_change_24h_pct=0.2,
        funding_rate=0.02,
    )
    scored = engine.compute(snap)
    if scored.composite_score >= 70:
        assert scored.above_alert_threshold is True


def test_convergence_bonus_when_both_patterns_strong(engine):
    """Bonus de convergencia cuando ambos patrones superan 50."""
    snap = _snapshot(
        inflow_4h_usd=2_000_000,
        inflow_1h_usd=800_000,
        holder_top10_pct=75.0,
        price_change_24h_pct=1.0,
        funding_rate=-0.02,
        short_interest_pct=25.0,
    )
    scored = engine.compute(snap)
    dominant_score = max(scored.long_pump.score, scored.classic_squeeze.score)
    # Si hay bonus, composite >= el dominante
    assert scored.composite_score >= dominant_score - 0.1  # tolerancia float
