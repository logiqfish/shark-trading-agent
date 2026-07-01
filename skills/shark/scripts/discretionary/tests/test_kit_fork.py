"""Kit-fork assertions: the real runners are adapted to the starter kit's
topology — no control service, regime via local-markov, no catalyst layer.

These complement the injected-runner tests (test_propose / test_execute), which
exercise the orchestration logic with fakes and pass unchanged.
"""
import discretionary as disc


def test_real_control_runner_passes_without_a_control_service(monkeypatch):
    # The kit ships no kill-switch/control service. The control runner must be an
    # always-pass no-op (exit 0) and must NOT shell out to anything.
    def boom(*args, **kwargs):
        raise AssertionError("control runner must not shell a control service")

    monkeypatch.setattr(disc, "_sh", boom)
    out = disc._real_runners()["control"]()
    assert out == {"exit": 0, "mode": "paper"}


def test_real_markov_runner_targets_local_markov(monkeypatch):
    # Regime must come from the kit's on-box local-markov veto.sh (same 0/10/20
    # exit contract), NOT a mesh regime service.
    captured = {}

    class _Proc:
        returncode = 10  # any code; we only assert which sibling was invoked

    def fake_sh(*args, stdin=None, env=None):
        captured["args"] = args
        return _Proc()

    monkeypatch.setattr(disc, "_sh", fake_sh)
    out = disc._real_runners()["markov"]()
    assert out == {"exit": 10}
    joined = "/".join(captured["args"])
    assert "local-markov" in joined
    assert any(a.endswith("veto.sh") for a in captured["args"])
    # the old mesh path ("markov" + "-regime") must be gone
    assert ("markov" + "-regime") not in joined


def test_real_catalyst_runner_is_empty_and_does_not_shell(monkeypatch):
    # No catalyst/news/fundamentals layer ships — the advisory is always "".
    def boom(*args, **kwargs):
        raise AssertionError("catalyst runner must not shell a catalyst service")

    monkeypatch.setattr(disc, "_sh", boom)
    assert disc._real_runners()["catalyst"]("TTWO") == ""
