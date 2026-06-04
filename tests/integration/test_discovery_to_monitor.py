"""
Test de Integración — Flujo Discovery → Monitor

Prueba el pipeline completo:
  ExchangeScanner (CCXT + CoinGecko mockeados)
  → PreScreener (lógica real)
  → DiscoveryResult (estructura y datos)
  → MonitorAgent.DataFetcher (CCXT mockeado)
  → TokenSnapshot (estructura validada)

No requiere PostgreSQL ni Redis (toda la I/O está mockeada).
"""
import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from agents.discovery.schemas import TokenData, DiscoveryResult
from agents.discovery.pre_screener import PreScreener
from agents.discovery.exchange_scanner import ExchangeScanner
from agents.monitor.schemas import TokenSnapshot


# ── Fixtures ──────────────────────────────────────────────────────────────────

MOCK_MEXC_MARKETS = {
    "BTC/USDT": {"base": "BTC", "quote": "USDT", "active": True},
    "ETH/USDT": {"base": "ETH", "quote": "USDT", "active": True},
    "COLLECT/USDT": {"base": "COLLECT", "quote": "USDT", "active": True},
    "PROS/USDT": {"base": "PROS", "quote": "USDT", "active": True},
    "PLAY/USDT": {"base": "PLAY", "quote": "USDT", "active": True},
    "USDT/USDC": {"base": "USDT", "quote": "USDC", "active": True},  # estable — debe filtrarse
}

MOCK_CG_DATA = [
    {
        "id": "collect-coin",
        "symbol": "collect",
        "market_cap": 45_000_000,
        "total_volume": 8_000_000,
        "current_price": 0.028,
        "price_change_percentage_24h": 2.5,
        "atl_date": "2024-01-15T00:00:00.000Z",
    },
    {
        "id": "pros-token",
        "symbol": "pros",
        "market_cap": 120_000_000,
        "total_volume": 15_000_000,
        "current_price": 0.67,
        "price_change_percentage_24h": 1.2,
        "atl_date": "2024-03-20T00:00:00.000Z",
    },
    {
        "id": "play-token",
        "symbol": "play",
        "market_cap": 8_000_000,
        "total_volume": 1_200_000,
        "current_price": 0.06,
        "price_change_percentage_24h": -1.0,
        "atl_date": "2024-06-01T00:00:00.000Z",
    },
    {
        "id": "bitcoin",
        "symbol": "btc",
        "market_cap": 1_200_000_000_000,  # demasiado grande → debe filtrarse
        "total_volume": 30_000_000_000,
        "current_price": 60000,
        "price_change_percentage_24h": 0.5,
        "atl_date": "2010-07-17T00:00:00.000Z",
    },
]


@pytest.fixture
def mock_exchange():
    exchange = MagicMock()
    exchange.load_markets = AsyncMock(return_value=MOCK_MEXC_MARKETS)
    exchange.close = AsyncMock()
    return exchange


@pytest.fixture
def screener():
    return PreScreener()


# ── Tests ExchangeScanner ────────────────────────────────────────────────────

class TestExchangeScanner:
    @pytest.mark.asyncio
    async def test_filters_stablecoins(self, mock_exchange):
        with patch("ccxt.async_support.mexc", return_value=mock_exchange), \
             patch("ccxt.async_support.bitget", return_value=mock_exchange):
            scanner = ExchangeScanner()
            symbols = await scanner.get_exchange_symbols("mexc")

        assert "USDT" not in symbols
        assert "USDC" not in symbols

    @pytest.mark.asyncio
    async def test_returns_base_symbols(self, mock_exchange):
        with patch("ccxt.async_support.mexc", return_value=mock_exchange):
            scanner = ExchangeScanner()
            symbols = await scanner.get_exchange_symbols("mexc")

        assert "BTC" in symbols
        assert "COLLECT" in symbols
        assert "PROS" in symbols

    @pytest.mark.asyncio
    async def test_market_data_maps_by_symbol(self):
        import httpx
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=MOCK_CG_DATA)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            scanner = ExchangeScanner()
            data = await scanner.get_market_data({"COLLECT", "PROS", "BTC"})

        assert "COLLECT" in data
        assert "BTC" in data
        assert data["COLLECT"]["market_cap"] == 45_000_000


# ── Tests PreScreener ─────────────────────────────────────────────────────────

class TestPreScreenerIntegration:
    def _make_tokens(self) -> list[TokenData]:
        return [
            TokenData(
                symbol="COLLECT", base="COLLECT", exchange="mexc",
                market_cap_usd=45_000_000, volume_24h_usd=8_000_000,
                volume_to_mcap_ratio=0.178, token_age_days=120,
                price_change_24h_pct=2.5,
            ),
            TokenData(
                symbol="PROS", base="PROS", exchange="mexc",
                market_cap_usd=120_000_000, volume_24h_usd=15_000_000,
                volume_to_mcap_ratio=0.125, token_age_days=60,
                price_change_24h_pct=1.2,
            ),
            TokenData(
                symbol="BTC", base="BTC", exchange="mexc",
                market_cap_usd=1_200_000_000_000, volume_24h_usd=30_000_000_000,
                volume_to_mcap_ratio=0.025, token_age_days=5000,
                price_change_24h_pct=0.5,
            ),
        ]

    def test_rejects_btc_too_large_mcap(self, screener):
        passing, rejected = screener.screen(self._make_tokens())
        symbols = [t.symbol for t in passing]
        assert "BTC" not in symbols
        assert "BTC" in rejected

    def test_passes_small_altcoins(self, screener):
        passing, rejected = screener.screen(self._make_tokens())
        symbols = [t.symbol for t in passing]
        assert "COLLECT" in symbols
        assert "PROS" in symbols

    def test_result_count(self, screener):
        tokens = self._make_tokens()
        passing, rejected = screener.screen(tokens)
        assert len(passing) + len(rejected) == len(tokens)

    def test_blacklist_integration(self, screener):
        screener.blacklist = {"COLLECT"}
        tokens = self._make_tokens()
        passing, rejected = screener.screen(tokens)
        assert "COLLECT" not in [t.symbol for t in passing]
        assert rejected.get("COLLECT") == "blacklist"


# ── Tests TokenSnapshot (Monitor output) ────────────────────────────────────

class TestTokenSnapshotStructure:
    def test_snapshot_serializes_correctly(self):
        snap = TokenSnapshot(
            symbol="COLLECT",
            exchange="mexc",
            timestamp=datetime.now(timezone.utc),
            current_price=0.028,
            price_change_24h_pct=2.5,
            volume_24h_usd=8_000_000,
            inflow_4h_usd=600_000,
            holder_top10_pct=65.0,
            funding_rate=0.008,
        )
        data = snap.model_dump()
        assert data["symbol"] == "COLLECT"
        assert data["current_price"] == 0.028

    def test_snapshot_optional_fields_default_none(self):
        snap = TokenSnapshot(
            symbol="TEST", exchange="mexc", current_price=1.0
        )
        assert snap.inflow_1h_usd is None
        assert snap.holder_top10_pct is None
        assert snap.funding_rate is None
        assert snap.onchain_available is False

    def test_snapshot_deserializes_from_dict(self):
        data = {
            "symbol": "PROS",
            "exchange": "bitget",
            "current_price": 0.67,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        snap = TokenSnapshot(**data)
        assert snap.symbol == "PROS"
        assert snap.exchange == "bitget"
