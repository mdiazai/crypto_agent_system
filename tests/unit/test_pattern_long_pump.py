import pytest
from datetime import datetime, timezone

from agents.monitor.schemas import TokenSnapshot
from agents.detector import pattern_long_pump
from agents.detector.schemas import ScoreWeights


def _snap(**kwargs) -> TokenSnapshot:
    base = dict(
        symbol="X", exchange="mexc",
        timestamp=datetime.now(timezone.utc),
        current_price=1.0,
    )
    base.update(kwargs)
    return TokenSnapshot(**base)


W = ScoreWeights()


def test_max_score_with_perfect_conditions():
    snap = _snap(
        inflow_4h_usd=5_000_000,   # 10x threshold
        holder_top10_pct=90.0,
        price_change_24h_pct=0.5,
        funding_rate=0.02,
    )
    bd = pattern_long_pump.score(snap, W)
    assert bd.score >= 80.0


def test_zero_inflow_reduces_score():
    snap = _snap(inflow_4h_usd=0.0, holder_top10_pct=70.0, price_change_24h_pct=1.0, funding_rate=0.01)
    bd = pattern_long_pump.score(snap, W)
    assert bd.inflow_signal == 0.0


def test_high_price_change_penalizes_stability():
    snap = _snap(price_change_24h_pct=40.0)
    bd = pattern_long_pump.score(snap, W)
    assert bd.price_stability_signal == 0.0


def test_negative_funding_reduces_long_pump_score():
    snap_pos = _snap(funding_rate=0.02)
    snap_neg = _snap(funding_rate=-0.1)
    bd_pos = pattern_long_pump.score(snap_pos, W)
    bd_neg = pattern_long_pump.score(snap_neg, W)
    assert bd_pos.funding_rate_signal > bd_neg.funding_rate_signal


def test_score_bounded():
    snap = _snap(
        inflow_4h_usd=100_000_000,
        holder_top10_pct=100.0,
        price_change_24h_pct=0.0,
        funding_rate=1.0,
    )
    bd = pattern_long_pump.score(snap, W)
    assert 0.0 <= bd.score <= 100.0
