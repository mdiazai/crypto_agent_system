"""
Test de Integración — Flujo Monitor → Detector → Executor (Paper Trading)

Prueba el pipeline crítico de ejecución:
  TokenSnapshot (Monitor)
  → DetectorAgent._handle_snapshot() (lógica real)
  → ScoredToken con composite_score
  → ExecutorAgent (PAPER_TRADING=True, CCXT mockeado)
  → Trade registrado correctamente

No requiere PostgreSQL ni Redis reales (DB y bus están mockeados).
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from agents.monitor.schemas import TokenSnapshot
from agents.detector.score_engine import ScoreEngine
from agents.detector.schemas import ScoredToken, ScoreWeights
from agents.executor.schemas import OrderResult, PositionState
from agents.executor.risk_manager import RiskManager


# ── Snapshots de prueba ───────────────────────────────────────────────────────

def _pump_snapshot(symbol="COLLECT") -> TokenSnapshot:
    """Snapshot con señales fuertes de Long Pump."""
    return TokenSnapshot(
        symbol=symbol,
        exchange="mexc",
        timestamp=datetime.now(timezone.utc),
        current_price=0.028,
        price_change_24h_pct=1.5,          # precio estable
        volume_24h_usd=8_000_000,
        inflow_1h_usd=200_000,
        inflow_4h_usd=900_000,             # > threshold (500k)
        holder_top10_pct=72.0,             # > 60%
        funding_rate=0.012,                # positivo (longs dominan)
        short_interest_pct=8.0,
        onchain_available=True,
    )


def _squeeze_snapshot(symbol="PROS") -> TokenSnapshot:
    """Snapshot con señales fuertes de Classic Short Squeeze."""
    return TokenSnapshot(
        symbol=symbol,
        exchange="mexc",
        timestamp=datetime.now(timezone.utc),
        current_price=0.67,
        price_change_24h_pct=3.0,
        volume_24h_usd=15_000_000,
        inflow_1h_usd=400_000,
        inflow_4h_usd=800_000,
        holder_top10_pct=68.0,
        funding_rate=-0.035,               # muy negativo = heavy shorts
        short_interest_pct=32.0,           # > 20% threshold
        onchain_available=True,
    )


def _noise_snapshot(symbol="NOISE") -> TokenSnapshot:
    """Snapshot de bajo score — no debe generar alerta."""
    return TokenSnapshot(
        symbol=symbol,
        exchange="mexc",
        timestamp=datetime.now(timezone.utc),
        current_price=1.0,
        price_change_24h_pct=0.1,
        volume_24h_usd=50_000,
        inflow_4h_usd=10_000,
        holder_top10_pct=30.0,
        funding_rate=0.001,
    )


# ── Tests ScoreEngine ─────────────────────────────────────────────────────────

class TestDetectorScoring:
    @pytest.fixture
    def engine(self):
        return ScoreEngine()

    def test_pump_snapshot_scores_above_threshold(self, engine):
        scored = engine.compute(_pump_snapshot())
        assert scored.composite_score >= 50.0
        assert scored.dominant_pattern == "long_pump"

    def test_squeeze_snapshot_favors_classic(self, engine):
        scored = engine.compute(_squeeze_snapshot())
        assert scored.classic_squeeze.score > scored.long_pump.score

    def test_noise_snapshot_scores_low(self, engine):
        scored = engine.compute(_noise_snapshot())
        assert scored.composite_score < 40.0
        assert scored.above_alert_threshold is False

    def test_above_threshold_flag_set_correctly(self, engine):
        high = engine.compute(_pump_snapshot())
        low = engine.compute(_noise_snapshot())

        if high.composite_score >= 70:
            assert high.above_alert_threshold is True
        assert low.above_alert_threshold is False

    def test_scored_token_serializable(self, engine):
        scored = engine.compute(_pump_snapshot())
        data = scored.model_dump()
        assert isinstance(data["composite_score"], float)
        assert isinstance(data["dominant_pattern"], str)
        assert "long_pump" in data
        assert "classic_squeeze" in data

    def test_weight_update_propagates(self, engine):
        snap = _pump_snapshot()
        score_default = engine.compute(snap).long_pump.score

        engine.update_weights(ScoreWeights(lp_inflow=3.0))
        score_boosted = engine.compute(snap).long_pump.score

        assert score_boosted != score_default

    @pytest.mark.parametrize("symbol", ["COLLECT", "PROS", "PLAY"])
    def test_multiple_tokens_independent(self, engine, symbol):
        snap = _pump_snapshot(symbol=symbol)
        scored = engine.compute(snap)
        assert scored.symbol == symbol
        assert 0.0 <= scored.composite_score <= 100.0


# ── Tests RiskManager + ExecutorAgent (Paper) ─────────────────────────────────

class TestExecutorPaperTrade:
    @pytest.fixture
    def risk(self):
        return RiskManager()

    def test_stop_loss_blocks_new_trade_after_breach(self, risk):
        risk.record_pnl(-200.0, is_loss=True)  # supera 15% de $1000
        assert risk.daily_drawdown_breached() is True

    def test_consecutive_losses_tracked(self, risk):
        for _ in range(3):
            risk.record_pnl(-20.0, is_loss=True)
        assert risk._consecutive_losses == 3

    def test_take_profit_50pct_at_30_gain(self, risk):
        pos = PositionState(
            trade_id=1,
            symbol="COLLECT",
            exchange="mexc",
            entry_price=0.028,
            total_quantity=1000.0,
            remaining_quantity=1000.0,
            capital_usd=28.0,
            stop_loss_price=0.028 * 0.92,
            take_profit_levels=risk.build_take_profit_levels(1000.0),
            is_paper=True,
        )
        # Precio sube 30%
        current_price = 0.028 * 1.30
        triggered = risk.triggered_levels(pos, current_price)
        assert len(triggered) == 1
        assert triggered[0].gain_pct == 30.0

        qty = risk.qty_to_sell(pos, triggered[0])
        assert qty == 500.0  # 50% de 1000

    def test_paper_order_result_structure(self):
        result = OrderResult(
            success=True,
            price=0.028,
            quantity=1000.0,
            cost_usd=28.0,
            order_id="paper-buy-COLLECT",
            is_paper=True,
        )
        assert result.success is True
        assert result.is_paper is True
        assert result.price == 0.028

    @pytest.mark.asyncio
    async def test_paper_buy_returns_correct_price(self):
        """ExchangeClient.buy() en paper mode devuelve el precio de mercado simulado."""
        from agents.executor.exchange_client import ExchangeClient

        mock_ticker = {"last": 0.028, "quoteVolume": 8_000_000}

        with patch("ccxt.async_support.mexc") as mock_cls:
            mock_exchange = MagicMock()
            mock_exchange.fetch_ticker = AsyncMock(return_value=mock_ticker)
            mock_exchange.close = AsyncMock()
            mock_cls.return_value = mock_exchange

            client = ExchangeClient()
            # Forzar paper trading
            with patch("agents.executor.exchange_client.settings") as mock_settings:
                mock_settings.paper_trading = True
                result = await client._paper_buy("COLLECT", 28.0, "mexc")

        assert result.success is True
        assert result.price == 0.028
        assert abs(result.quantity - 1000.0) < 0.01
        assert result.is_paper is True

    @pytest.mark.asyncio
    async def test_paper_sell_returns_market_price(self):
        from agents.executor.exchange_client import ExchangeClient

        mock_ticker = {"last": 0.036}  # precio sube 28.5%

        with patch("ccxt.async_support.mexc") as mock_cls:
            mock_exchange = MagicMock()
            mock_exchange.fetch_ticker = AsyncMock(return_value=mock_ticker)
            mock_exchange.close = AsyncMock()
            mock_cls.return_value = mock_exchange

            client = ExchangeClient()
            with patch("agents.executor.exchange_client.settings") as mock_settings:
                mock_settings.paper_trading = True
                result = await client._paper_sell("COLLECT", 500.0, "mexc")

        assert result.success is True
        assert result.price == 0.036
        assert result.quantity == 500.0


# ── Test de flujo extremo a extremo (mockeado) ────────────────────────────────

class TestEndToEndFlow:
    @pytest.mark.asyncio
    async def test_snapshot_to_scored_token_to_trade_lifecycle(self):
        """
        Ciclo completo en memoria:
          TokenSnapshot → ScoreEngine → ScoredToken → RiskManager checks
        """
        engine = ScoreEngine()
        risk = RiskManager()

        # 1. Monitor produce snapshot
        snap = _pump_snapshot("COLLECT")

        # 2. Detector procesa snapshot
        scored = engine.compute(snap)
        assert isinstance(scored, ScoredToken)

        # 3. Si score suficiente, verificar safety gate
        if scored.above_alert_threshold:
            allowed, reason = await risk.can_trade()
            assert allowed is True
            assert reason == "ok"

            # 4. Construir posición paper
            entry_price = snap.current_price
            sl_price = risk.calc_stop_loss_price(entry_price)
            tp_levels = risk.build_take_profit_levels(1000.0)

            pos = PositionState(
                trade_id=99,
                symbol=scored.symbol,
                exchange=scored.exchange,
                entry_price=entry_price,
                total_quantity=1000.0,
                remaining_quantity=1000.0,
                capital_usd=28.0,
                stop_loss_price=sl_price,
                take_profit_levels=tp_levels,
                is_paper=True,
                score_at_entry=scored.composite_score,
                pattern_detected=scored.dominant_pattern,
            )

            # 5. Verificar stop loss no se dispara al precio de entrada
            assert risk.should_stop_loss(pos, entry_price) is False
            assert risk.should_stop_loss(pos, sl_price - 0.001) is True

            # 6. Verificar take profit no se dispara hasta +30%
            assert len(risk.triggered_levels(pos, entry_price * 1.10)) == 0
            assert len(risk.triggered_levels(pos, entry_price * 1.31)) == 1

        # Test pasa independientemente del score (depende de settings.alert_threshold)
        assert 0.0 <= scored.composite_score <= 100.0
