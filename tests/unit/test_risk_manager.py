import pytest
from datetime import datetime, timezone

from agents.executor.risk_manager import RiskManager
from agents.executor.schemas import PositionState, TakeProfitLevel


def _position(entry_price=1.0, qty=100.0, sl_price=0.92) -> PositionState:
    risk = RiskManager()
    tp_levels = risk.build_take_profit_levels(qty)
    return PositionState(
        trade_id=1,
        symbol="TEST",
        exchange="mexc",
        entry_price=entry_price,
        total_quantity=qty,
        remaining_quantity=qty,
        capital_usd=100.0,
        stop_loss_price=sl_price,
        take_profit_levels=tp_levels,
        is_paper=True,
    )


@pytest.fixture
def risk():
    return RiskManager()


class TestStopLoss:
    def test_triggers_at_stop_price(self, risk):
        pos = _position(entry_price=1.0, sl_price=0.92)
        assert risk.should_stop_loss(pos, 0.92) is True
        assert risk.should_stop_loss(pos, 0.91) is True

    def test_does_not_trigger_above(self, risk):
        pos = _position(entry_price=1.0, sl_price=0.92)
        assert risk.should_stop_loss(pos, 0.93) is False
        assert risk.should_stop_loss(pos, 1.20) is False

    def test_calc_stop_loss_price_8pct(self, risk):
        sl = risk.calc_stop_loss_price(1.0)
        assert abs(sl - 0.92) < 0.001  # 8% below (default)


class TestTakeProfitLevels:
    def test_three_levels_built(self, risk):
        levels = risk.build_take_profit_levels(100.0)
        assert len(levels) == 3

    def test_level_percentages(self, risk):
        levels = risk.build_take_profit_levels(100.0)
        sell_pcts = [l.sell_pct for l in levels]
        assert sell_pcts == [50.0, 30.0, 20.0]
        assert sum(sell_pcts) == 100.0

    def test_qty_to_sell_level1(self, risk):
        pos = _position(qty=100.0)
        level = pos.take_profit_levels[0]  # 50%
        qty = risk.qty_to_sell(pos, level)
        assert qty == 50.0

    def test_triggered_levels_at_30pct_gain(self, risk):
        pos = _position(entry_price=1.0)
        triggered = risk.triggered_levels(pos, 1.30)
        assert len(triggered) == 1
        assert triggered[0].gain_pct == 30.0

    def test_triggered_levels_at_60pct_gain(self, risk):
        pos = _position(entry_price=1.0)
        triggered = risk.triggered_levels(pos, 1.60)
        assert len(triggered) == 2  # nivel 30% y 60% ambos activos

    def test_already_triggered_not_returned(self, risk):
        pos = _position(entry_price=1.0)
        pos.take_profit_levels[0].triggered = True
        triggered = risk.triggered_levels(pos, 1.35)
        assert all(l.gain_pct != 30.0 for l in triggered)

    def test_no_levels_below_threshold(self, risk):
        pos = _position(entry_price=1.0)
        triggered = risk.triggered_levels(pos, 1.10)
        assert len(triggered) == 0


class TestDailyDrawdown:
    def test_no_breach_initially(self, risk):
        assert risk.daily_drawdown_breached() is False

    def test_breach_after_large_loss(self, risk):
        risk.record_pnl(-200.0, is_loss=True)  # capital default=1000, max=15%=$150
        assert risk.daily_drawdown_breached() is True

    def test_no_breach_within_limit(self, risk):
        risk.record_pnl(-50.0, is_loss=True)
        assert risk.daily_drawdown_breached() is False


class TestConsecutiveLosses:
    def test_increments_on_loss(self, risk):
        risk.record_pnl(-10.0, is_loss=True)
        risk.record_pnl(-10.0, is_loss=True)
        assert risk._consecutive_losses == 2

    def test_resets_on_win(self, risk):
        risk.record_pnl(-10.0, is_loss=True)
        risk.record_pnl(-10.0, is_loss=True)
        risk.record_pnl(20.0, is_loss=False)
        assert risk._consecutive_losses == 0
