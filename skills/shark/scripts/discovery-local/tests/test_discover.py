import discover as d


def test_watchlist_mode_returns_configured_tickers(monkeypatch):
    monkeypatch.setenv("DISCOVERY_MODE", "watchlist")
    monkeypatch.setenv("WATCHLIST", "AAPL, msft ,NVDA")
    assert d.candidates(fetch_movers=lambda: []) == ["AAPL", "MSFT", "NVDA"]


def test_movers_mode_filters_by_price_and_volume(monkeypatch):
    monkeypatch.setenv("DISCOVERY_MODE", "alpaca_movers")
    monkeypatch.setenv("MOVERS_MIN_PRICE", "5")
    monkeypatch.setenv("MOVERS_MIN_VOLUME", "1000000")
    monkeypatch.setenv("MOVERS_TOP_N", "2")
    movers = [
        {"symbol": "GOOD", "price": 50.0, "volume": 5_000_000},
        {"symbol": "CHEAP", "price": 2.0, "volume": 9_000_000},   # price filtered
        {"symbol": "THIN", "price": 80.0, "volume": 100_000},     # volume filtered
        {"symbol": "ALSO", "price": 20.0, "volume": 3_000_000},
    ]
    assert d.candidates(fetch_movers=lambda: movers) == ["GOOD", "ALSO"]
