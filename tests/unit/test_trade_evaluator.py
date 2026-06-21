import pytest
from unittest.mock import MagicMock
from agents.learner.trade_evaluator import TradeEvaluator
from agents.learner.schemas import QUALITY_SCORE


def _trade(pnl_pct=None, entry_quality=None, pattern="long_pump", is_paper=True):
    t = MagicMock()
    t.pnl_pct = pnl_pct
    t.entry_quality = entry_quality
    t.pattern_detected = pattern
    t.is_paper = is_paper
    t.score_at_entry = 75.0
    return t


@pytest.fixture
def evaluator():
    return TradeEvaluator()


class TestInferQuality:
    def test_perfect(self, evaluator):
        assert evaluator._infer_quality(25.0) == "perfect"

    def test_good(self, evaluator):
        assert evaluator._infer_quality(15.0) == "good"

    def test_early(self, evaluator):
        assert evaluator._infer_quality(5.0) == "early"

    def test_late(self, evaluator):
        assert evaluator._infer_quality(0.5) == "late"

    def test_bad(self, evaluator):
        assert evaluator._infer_quality(-5.0) == "bad"

    def test_none_returns_none(self, evaluator):
        assert evaluator._infer_quality(None) is None


class TestComputeMetrics:
    def test_empty_trades(self, evaluator):
        metrics = evaluator.compute_metrics([])
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0

    def test_win_rate_calculation(self, evaluator):
        trades = [
            _trade(pnl_pct=20.0, entry_quality="perfect"),
            _trade(pnl_pct=15.0, entry_quality="good"),
            _trade(pnl_pct=-5.0, entry_quality="bad"),
            _trade(pnl_pct=-8.0, entry_quality="bad"),
        ]
        metrics = evaluator.compute_metrics(trades)
        assert metrics.total_trades == 4
        assert metrics.win_rate == 0.5
        assert metrics.perfect_count == 1
        assert metrics.bad_count == 2

    def test_avg_pnl(self, evaluator):
        trades = [
            _trade(pnl_pct=20.0, entry_quality="perfect"),
            _trade(pnl_pct=-10.0, entry_quality="bad"),
        ]
        metrics = evaluator.compute_metrics(trades)
        assert abs(metrics.avg_pnl_pct - 5.0) < 0.01

    def test_quality_score_averaging(self, evaluator):
        trades = [
            _trade(pnl_pct=25.0, entry_quality="perfect"),   # score 4.0
            _trade(pnl_pct=12.0, entry_quality="good"),      # score 3.0
        ]
        metrics = evaluator.compute_metrics(trades)
        assert abs(metrics.avg_quality_score - 3.5) < 0.01

    def test_pattern_split(self, evaluator):
        trades = [
            _trade(pnl_pct=20.0, entry_quality="perfect", pattern="long_pump"),
            _trade(pnl_pct=15.0, entry_quality="good", pattern="long_pump"),
            _trade(pnl_pct=-5.0, entry_quality="bad", pattern="classic"),
        ]
        metrics = evaluator.compute_metrics(trades)
        assert metrics.long_pump.total_trades == 2
        assert metrics.long_pump.win_rate == 1.0
        assert metrics.classic.total_trades == 1
        assert metrics.classic.win_rate == 0.0


class TestQualityScores:
    def test_all_qualities_have_scores(self):
        for q in ("perfect", "good", "early", "late", "bad"):
            assert q in QUALITY_SCORE

    def test_perfect_highest(self):
        assert QUALITY_SCORE["perfect"] > QUALITY_SCORE["good"] > QUALITY_SCORE["early"]

    def test_bad_is_zero(self):
        assert QUALITY_SCORE["bad"] == 0.0
