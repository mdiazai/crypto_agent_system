import pytest
from datetime import datetime, timezone

from agents.monitor.schemas import TokenSnapshot
from agents.detector import pattern_classic_squeeze
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


def test_max_score_with_squeeze_conditions():
    snap = _snap(
        short_interest_pct=55.0,
        funding_rate=-0.06,
        inflow_1h_usd=400_000,
        holder_top10_pct=75.0,
    )
    bd = pattern_classic_squeeze.score(snap, W)
    assert bd.score >= 75.0


def test_no_short_interest_zeros_signal():
    snap = _snap(short_interest_pct=0.0)
    bd = pattern_classic_squeeze.score(snap, W)
    assert bd.short_interest_signal == 0.0


def test_positive_funding_rate_zeros_signal():
    snap = _snap(funding_rate=0.05)
    bd = pattern_classic_squeeze.score(snap, W)
    assert bd.funding_rate_signal == 0.0


def test_score_bounded():
    snap = _snap(
        short_interest_pct=100.0,
        funding_rate=-1.0,
        inflow_1h_usd=50_000_000,
        holder_top10_pct=100.0,
    )
    bd = pattern_classic_squeeze.score(snap, W)
    assert 0.0 <= bd.score <= 100.0


def test_missing_data_returns_zero_signals():
    snap = _snap(
        short_interest_pct=None,
        funding_rate=None,
        inflow_1h_usd=None,
        holder_top10_pct=None,
    )
    bd = pattern_classic_squeeze.score(snap, W)
    assert bd.score == 0.0
