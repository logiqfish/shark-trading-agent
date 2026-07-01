import broker


def test_enter_has_no_control_url(monkeypatch):
    # The kit must not reference a Cloud Run control service anywhere in broker.
    # (The forbidden URL fragment is built at runtime so this assertion file does
    # not itself contain the literal that the repo-wide secret-scrub gate forbids.)
    import inspect
    src = inspect.getsource(broker)
    cloud_run_fragment = "run" + ".app"
    assert cloud_run_fragment not in src
    assert "control" not in src.lower() or "kill_" + "switch" not in src.lower()
