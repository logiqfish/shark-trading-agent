"""ExecutionAdapter / LegacyAlpacaRestAdapter — HTTP mapping, fake-injected."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from execution_adapter import ExecutionAdapter, LegacyAlpacaRestAdapter


def _spy():
    """Return (adapter, calls). calls records (method, path, body)."""
    calls = []
    def http(base, key, sec, method, path, body=None):
        calls.append((method, path, body))
        return (200, {"ok": True, "path": path})
    return LegacyAlpacaRestAdapter("https://paper-api.alpaca.markets", "k", "s", http=http), calls


def test_submit_order_posts_to_v2_orders():
    a, calls = _spy()
    st, resp = a.submit_order({"symbol": "ABC", "qty": "1"})
    assert st == 200
    assert calls == [("POST", "/v2/orders", {"symbol": "ABC", "qty": "1"})]


def test_cancel_order_deletes_by_id():
    a, calls = _spy()
    a.cancel_order("ord-9")
    assert calls == [("DELETE", "/v2/orders/ord-9", None)]


def test_replace_order_patches_fields():
    a, calls = _spy()
    a.replace_order("ord-9", {"stop_price": "12.34"})
    assert calls == [("PATCH", "/v2/orders/ord-9", {"stop_price": "12.34"})]


def test_get_position_path():
    a, calls = _spy()
    a.get_position("ABC")
    assert calls == [("GET", "/v2/positions/ABC", None)]


def test_get_open_orders_for_symbol_uses_nested_legs():
    a, calls = _spy()
    a.get_open_orders("ABC")
    assert calls == [("GET", "/v2/orders?status=open&symbols=ABC&nested=true&limit=50", None)]


def test_get_open_orders_all_uses_nested_legs():
    a, calls = _spy()
    a.get_open_orders()
    assert calls == [("GET", "/v2/orders?status=open&nested=true&limit=50", None)]


def test_get_asset_and_clock_paths():
    a, calls = _spy()
    a.get_asset("ABC")
    a.get_clock()
    assert calls == [("GET", "/v2/assets/ABC", None), ("GET", "/v2/clock", None)]


def test_base_property_exposed_for_paper_guard():
    a, _ = _spy()
    assert "paper" in a.base


def test_interface_methods_raise_not_implemented():
    base = ExecutionAdapter()
    for fn in (lambda: base.submit_order({}), lambda: base.get_clock()):
        try:
            fn()
            assert False, "expected NotImplementedError"
        except NotImplementedError:
            pass
