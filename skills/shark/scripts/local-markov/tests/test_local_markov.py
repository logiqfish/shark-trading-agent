import local_markov as lm


def _series(start, step, n):
    return [start + step * i for i in range(n)]


def test_uptrend_is_bull():
    closes = _series(100.0, 0.5, 120)          # steady rise → fast SMA > slow SMA, price on top
    assert lm.classify(closes) == "Bull"


def test_downtrend_is_bear():
    closes = _series(160.0, -0.5, 120)         # steady fall
    assert lm.classify(closes) == "Bear"


def test_flat_is_sideways():
    closes = [100.0 + (1 if i % 2 else -1) for i in range(120)]  # oscillate, no trend
    assert lm.classify(closes) == "Sideways"


def test_drawdown_spike_overrides_to_bear():
    closes = _series(100.0, 0.5, 110) + [160, 150, 138, 126, 118, 110, 104, 99, 95, 92]  # sharp reversal
    assert lm.classify(closes) == "Bear"


def test_too_few_bars_returns_none():
    assert lm.classify([1.0, 2.0, 3.0]) is None   # insufficient history → fail-soft


def test_current_regime_shape():
    closes = _series(100.0, 0.5, 120)
    out = lm.current_regime_from_closes(closes)
    assert out == {"current_regime": "Bull"}
