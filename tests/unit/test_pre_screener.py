import pytest
from agents.discovery.pre_screener import PreScreener
from agents.discovery.schemas import TokenData


def _make_token(**kwargs) -> TokenData:
    defaults = dict(
        symbol="TEST",
        base="TEST",
        exchange="mexc",
        market_cap_usd=50_000_000,
        volume_24h_usd=5_000_000,
        volume_to_mcap_ratio=0.10,
        token_age_days=180,
        price_change_24h_pct=3.0,
    )
    defaults.update(kwargs)
    return TokenData(**defaults)


@pytest.fixture
def screener():
    return PreScreener()


def test_passes_valid_token(screener):
    token = _make_token()
    passing, rejected = screener.screen([token])
    assert len(passing) == 1
    assert len(rejected) == 0


def test_rejects_blacklisted(screener):
    screener.blacklist = {"TEST"}
    token = _make_token()
    passing, rejected = screener.screen([token])
    assert len(passing) == 0
    assert rejected["TEST"] == "blacklist"


def test_rejects_no_market_cap(screener):
    token = _make_token(market_cap_usd=None)
    _, rejected = screener.screen([token])
    assert rejected["TEST"] == "no_market_cap"


def test_rejects_mcap_too_low(screener):
    token = _make_token(market_cap_usd=1_000_000)
    _, rejected = screener.screen([token])
    assert "mcap_too_low" in rejected["TEST"]


def test_rejects_mcap_too_high(screener):
    token = _make_token(market_cap_usd=1_000_000_000)
    _, rejected = screener.screen([token])
    assert "mcap_too_high" in rejected["TEST"]


def test_rejects_low_volume_ratio(screener):
    token = _make_token(volume_to_mcap_ratio=0.001)
    _, rejected = screener.screen([token])
    assert "low_volume_ratio" in rejected["TEST"]


def test_rejects_token_too_old(screener):
    token = _make_token(token_age_days=1000)
    _, rejected = screener.screen([token])
    assert "too_old" in rejected["TEST"]


def test_rejects_already_pumping(screener):
    token = _make_token(price_change_24h_pct=75.0)
    _, rejected = screener.screen([token])
    assert "already_pumping" in rejected["TEST"]


def test_multiple_tokens_mixed(screener):
    tokens = [
        _make_token(symbol="GOOD"),
        _make_token(symbol="BAD_MCAP", market_cap_usd=100),
        _make_token(symbol="BAD_OLD", token_age_days=900),
    ]
    passing, rejected = screener.screen(tokens)
    assert len(passing) == 1
    assert passing[0].symbol == "GOOD"
    assert len(rejected) == 2
