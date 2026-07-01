"""Phase 2 adapter hardening — fail-closed networking, symbol encoding, idempotency lookup."""
import os, sys, socket
import urllib.error, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import execution_adapter
from execution_adapter import ExecutionAdapter, LegacyAlpacaRestAdapter, _http


def _spy():
    calls = []
    def http(base, key, sec, method, path, body=None):
        calls.append((method, path, body))
        return (200, {"ok": True, "path": path})
    return LegacyAlpacaRestAdapter("https://paper-api.alpaca.markets", "k", "s", http=http), calls


# --- fail-closed networking: _http must never raise; status None signals "no answer" ---

def test_http_returns_none_status_on_urlerror(monkeypatch):
    def boom(*a, **k):
        raise urllib.error.URLError("Name or service not known")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    st, body = _http("https://paper-api.alpaca.markets", "k", "s", "GET", "/v2/clock")
    assert st is None
    assert "error" in body


def test_http_returns_none_status_on_socket_timeout(monkeypatch):
    def boom(*a, **k):
        raise socket.timeout("timed out")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    st, body = _http("https://paper-api.alpaca.markets", "k", "s", "POST", "/v2/orders", {"x": 1})
    assert st is None
    assert "error" in body


def test_http_returns_none_status_on_connection_refused(monkeypatch):
    def boom(*a, **k):
        raise ConnectionRefusedError("refused")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    st, body = _http("https://paper-api.alpaca.markets", "k", "s", "GET", "/v2/clock")
    assert st is None
    assert "error" in body


def test_http_still_surfaces_http_error_status(monkeypatch):
    """An HTTP 4xx/5xx is a real broker answer — keep its status, do NOT collapse to None."""
    class FakeHTTPError(urllib.error.HTTPError):
        def __init__(self):
            self.code = 422
        def read(self):
            return b'{"message": "rejected"}'
    def boom(*a, **k):
        raise FakeHTTPError()
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    st, body = _http("https://paper-api.alpaca.markets", "k", "s", "POST", "/v2/orders", {"x": 1})
    assert st == 422
    assert body == {"message": "rejected"}


# --- symbol URL-encoding (defends against odd tickers reaching the path/query) ---

def test_get_position_url_encodes_symbol():
    a, calls = _spy()
    a.get_position("BRK/B")
    assert calls == [("GET", "/v2/positions/BRK%2FB", None)]


def test_get_asset_url_encodes_symbol():
    a, calls = _spy()
    a.get_asset("BRK/B")
    assert calls == [("GET", "/v2/assets/BRK%2FB", None)]


def test_get_open_orders_url_encodes_symbol():
    a, calls = _spy()
    a.get_open_orders("BRK/B", status="all")
    assert calls == [("GET", "/v2/orders?status=all&symbols=BRK%2FB&nested=true&limit=50", None)]


def test_plain_symbol_is_unchanged():
    a, calls = _spy()
    a.get_position("AAPL")
    assert calls == [("GET", "/v2/positions/AAPL", None)]


# --- idempotency lookup: query an order by its client_order_id (reconciliation) ---

def test_get_order_by_client_id_path():
    a, calls = _spy()
    a.get_order_by_client_id("shark-enter-abc123")
    assert calls == [("GET", "/v2/orders:by_client_order_id?client_order_id=shark-enter-abc123", None)]


def test_get_order_by_client_id_url_encodes():
    a, calls = _spy()
    a.get_order_by_client_id("a b/c")
    assert calls == [("GET", "/v2/orders:by_client_order_id?client_order_id=a%20b%2Fc", None)]


def test_interface_declares_get_order_by_client_id():
    base = ExecutionAdapter()
    try:
        base.get_order_by_client_id("x")
        assert False, "expected NotImplementedError"
    except NotImplementedError:
        pass
