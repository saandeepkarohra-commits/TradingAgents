"""The market=india preset: config values, bare NSE symbols, social search, FRED aliases."""

import importlib

import pytest

import tradingagents.default_config as default_config_module
from tradingagents.dataflows.symbols import (
    normalize_symbol,
    social_search_symbol,
    with_exchange_suffix,
)
from tradingagents.dataflows.vendors import fred, reddit
from tradingagents.default_config import MARKET_PRESETS, apply_market_preset


@pytest.mark.unit
def test_global_market_keeps_us_defaults():
    config = apply_market_preset({})
    assert config["market"] == "global"
    assert config.get("default_exchange_suffix") is None
    assert "reddit_subreddits" not in config  # nothing added for the global market


@pytest.mark.unit
def test_india_preset_fills_market_sensitive_keys():
    base = dict(default_config_module.DEFAULT_CONFIG, market="india")
    config = apply_market_preset(base)
    india = MARKET_PRESETS["india"]
    assert config["global_news_queries"] == india["global_news_queries"]
    assert config["reddit_subreddits"] == india["reddit_subreddits"]
    assert config["macro_indicator_hints"] == india["macro_indicator_hints"]
    assert config["default_exchange_suffix"] == ".NS"
    assert base["default_exchange_suffix"] is None  # the caller's dict is not mutated


@pytest.mark.unit
def test_india_preset_keeps_explicit_settings():
    config = apply_market_preset({"market": "India", "reddit_subreddits": ["mysub"]})
    assert config["market"] == "india"
    assert config["reddit_subreddits"] == ["mysub"]
    assert config["default_exchange_suffix"] == ".NS"


@pytest.mark.unit
def test_unknown_market_is_rejected():
    with pytest.raises(ValueError, match="Unknown market"):
        apply_market_preset({"market": "mars"})


@pytest.mark.unit
def test_market_env_var_applies_preset(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_MARKET", "india")
    try:
        dc = importlib.reload(default_config_module)
        assert dc.DEFAULT_CONFIG["market"] == "india"
        assert dc.DEFAULT_CONFIG["default_exchange_suffix"] == ".NS"
        assert "IndianStreetBets" in dc.DEFAULT_CONFIG["reddit_subreddits"]
    finally:
        monkeypatch.delenv("TRADINGAGENTS_MARKET", raising=False)
        importlib.reload(default_config_module)


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("RELIANCE", "RELIANCE.NS"),
        ("reliance", "RELIANCE.NS"),
        ("BAJAJ-AUTO", "BAJAJ-AUTO.NS"),
        ("TCS.BO", "TCS.BO"),          # an explicit exchange wins
        ("INFY.NS", "INFY.NS"),
        ("NIFTY", "^NSEI"),            # index aliases resolve, no suffix
        ("SENSEX", "^BSESN"),
        ("BANKNIFTY", "^NSEBANK"),
        ("BTCUSD", "BTC-USD"),         # crypto is not an NSE listing
        ("USDINR", "USDINR=X"),        # nor is forex
        ("XAUUSD", "GC=F"),
    ],
)
def test_bare_symbols_take_the_nse_suffix(raw, expected):
    assert with_exchange_suffix(raw, ".NS") == expected


@pytest.mark.unit
def test_no_suffix_leaves_ticker_as_given():
    assert with_exchange_suffix("nvda", None) == "nvda"
    assert with_exchange_suffix("BTCUSD", "") == "BTCUSD"


@pytest.mark.unit
def test_indian_index_aliases_in_normalize_symbol():
    assert normalize_symbol("nifty50") == "^NSEI"
    assert normalize_symbol("SENSEX") == "^BSESN"


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw, expected",
    [("RELIANCE.NS", "RELIANCE"), ("tcs.bo", "TCS"), ("BTC-USD", "BTC"), ("AAPL", "AAPL"),
     ("0700.HK", "0700.HK")],
)
def test_social_search_symbol(raw, expected):
    assert social_search_symbol(raw) == expected


@pytest.mark.unit
def test_reddit_searches_bare_indian_symbol(monkeypatch):
    seen = {}

    def fake_fetch(ticker, sub, limit, timeout, _retry=True):
        seen["ticker"], seen["sub"] = ticker, sub
        return []

    monkeypatch.setattr(reddit, "_fetch_subreddit_rss", fake_fetch)
    out = reddit.fetch_reddit_posts("RELIANCE.NS", MARKET_PRESETS["india"]["reddit_subreddits"])
    assert seen["ticker"] == "RELIANCE"
    assert seen["sub"] == "IndianStreetBets+IndiaInvestments+IndianStockMarket"
    assert "RELIANCE" in out


@pytest.mark.unit
def test_india_macro_hints_are_fred_aliases():
    for alias in MARKET_PRESETS["india"]["macro_indicator_hints"]:
        assert alias in fred.MACRO_SERIES, alias
    assert fred._resolve_series_id("india_cpi") == "INDCPIALLMINMEI"
    assert fred._resolve_series_id("usd_inr") == "DEXINUS"


@pytest.mark.unit
def test_global_macro_hints_are_fred_aliases():
    for alias in default_config_module._GLOBAL_MARKET["macro_indicator_hints"]:
        assert alias in fred.MACRO_SERIES, alias


@pytest.mark.unit
def test_backtest_resolves_bare_symbols_under_india(monkeypatch, tmp_path):
    import tradingagents.backtest as bt

    calls = []

    class _Graph:
        def __init__(self, selected_analysts=None, config=None, **kw):
            from tradingagents.decision_log import TradingMemoryLog
            self.memory_log = TradingMemoryLog(config)

        def propagate(self, ticker, trade_date, asset_type="stock", portfolio=None):
            calls.append(ticker)

        def settle_pending(self, ticker):
            calls.append(("settle", ticker))

    monkeypatch.setattr(bt, "TradingAgentsGraph", _Graph)
    config = {"market": "india", "results_dir": str(tmp_path / "r"),
              "memory_log_path": str(tmp_path / "m.md")}
    bt.run_backtest(["RELIANCE", "TCS.BO"], ["2026-01-05"], config)
    assert calls == ["RELIANCE.NS", "TCS.BO", ("settle", "RELIANCE.NS"), ("settle", "TCS.BO")]
