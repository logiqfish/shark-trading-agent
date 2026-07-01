import thesis as t


def test_fetch_regime_uses_local_markov(monkeypatch):
    # The kit fork must read regime from on-box local-markov, NOT a mesh URL.
    monkeypatch.setattr(t, "_local_regime_label", lambda ticker: "Bull")
    # long position + Bull regime -> favorable
    assert t.fetch_regime("AAPL", "long") == "favorable"


def test_catalyst_and_fundamentals_checks_removed():
    assert "catalyst_live" not in t.CHECKS
    assert "fundamentals_stable" not in t.CHECKS
