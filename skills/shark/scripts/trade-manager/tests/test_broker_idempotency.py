"""Phase 2 idempotency + reconciliation: every write carries a client_order_id; an
ambiguous (no-answer) entry reconciles by that id instead of blind-retrying into a dup."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import broker
from execution_adapter import LegacyAlpacaRestAdapter


def _adapter(handler):
    def http(base, key, sec, method, path, body=None):
        return handler(method, path, body)
    return LegacyAlpacaRestAdapter("https://paper-api.alpaca.markets", "k", "s", http=http)


def _post_capture(extra=None):
    """Handler that records every POSTed order body and 200s. `extra` handles GETs."""
    posts = []
    def handler(method, path, body):
        if method == "POST" and path == "/v2/orders":
            posts.append(body)
            return (200, {"id": "ord-%d" % len(posts)})
        if extra:
            return extra(method, path, body)
        return (200, {})
    return handler, posts


# --- every order-creating write carries a client_order_id ---

def test_whole_bracket_carries_client_order_id():
    h, posts = _post_capture()
    broker.enter("ABC", 10, 100.0, 95.0, phase=1, fractional=False, adapter=_adapter(h))
    assert len(posts) == 1
    assert posts[0].get("client_order_id")


def test_enter_uses_explicit_coid_when_given():
    h, posts = _post_capture()
    broker.enter("ABC", 10, 100.0, 95.0, phase=1, fractional=False,
                 adapter=_adapter(h), coid="fixed-base-1")
    assert posts[0]["client_order_id"] == "fixed-base-1"


def test_fractional_buy_and_stop_get_distinct_client_order_ids():
    def extra(method, path, body):
        if path == "/v2/assets/META":
            return (200, {"fractionable": True})
        if path == "/v2/clock":
            return (200, {"is_open": True})
        return (200, {})
    h, posts = _post_capture(extra)
    broker.enter("META", 0.24, 625.0, 593.75, phase=1, fractional=True,
                 adapter=_adapter(h), coid="frac-base")
    assert len(posts) == 2
    coids = [p.get("client_order_id") for p in posts]
    assert all(coids) and coids[0] != coids[1]


def test_place_stop_carries_client_order_id():
    h, posts = _post_capture()
    broker.place_stop("ABC", 10, 95.0, adapter=_adapter(h))
    assert posts[0].get("client_order_id")


def test_scale_out_sell_and_oco_get_distinct_client_order_ids():
    h, posts = _post_capture()
    broker.scale_out("ABC", 5, 5, 100.0, 110.0, ["c1"], adapter=_adapter(h))
    assert len(posts) == 2
    coids = [p.get("client_order_id") for p in posts]
    assert all(coids) and coids[0] != coids[1]


def test_dire_liquidate_sell_carries_client_order_id():
    def handler(method, path, body):
        if path.startswith("/v2/orders?"):           # is_protected read -> no stop
            return (200, [])
        if path == "/v2/positions/ABC":
            return (200, {"qty": "10"})
        if method == "POST" and path == "/v2/orders":
            handler.posted.append(body)
            return (200, {"id": "sell-1"})
        return (200, {})
    handler.posted = []
    broker.dire_liquidate("ABC", adapter=_adapter(handler))
    assert handler.posted and handler.posted[0].get("client_order_id")


# --- the ENTRY key must be STABLE across fires (cross-fire broker-level dedup) ---

def test_entry_coid_is_deterministic_per_ticker_and_day():
    """Two separate enter() calls for the same ticker on the same day must send the
    SAME bracket client_order_id, so a heartbeat-to-heartbeat retry is rejected by
    Alpaca as a duplicate instead of opening a second position."""
    h1, posts1 = _post_capture()
    h2, posts2 = _post_capture()
    broker.enter("ABC", 10, 100.0, 95.0, phase=1, fractional=False, adapter=_adapter(h1))
    broker.enter("ABC", 10, 100.0, 95.0, phase=1, fractional=False, adapter=_adapter(h2))
    assert posts1[0]["client_order_id"] == posts2[0]["client_order_id"]
    assert "ABC" in posts1[0]["client_order_id"]


# --- a duplicate-coid REJECT means "this entry already landed" — not a fresh reject ---

def test_duplicate_coid_reject_is_treated_as_already_placed():
    """A 422 'client_order_id must be unique' means a prior fire's bracket is live.
    Must reconcile and report it placed — NOT fall back to a market buy (would double)."""
    posts = []
    def handler(method, path, body):
        if method == "POST" and path == "/v2/orders":
            posts.append(body)
            return (422, {"code": 40010001, "message": "client_order_id must be unique"})
        if path.startswith("/v2/orders:by_client_order_id"):
            return (200, {"id": "br-prior", "status": "new"})
        return (200, {})
    r = broker.enter("ABC", 10, 100.0, 95.0, phase=1, fractional=False,
                     adapter=_adapter(handler), coid="dup-1")
    assert r["ok"] is True
    assert r.get("order_id") == "br-prior"
    assert len(posts) == 1                          # only the bracket — NO fallback buy


def test_duplicate_coid_reject_but_unfetchable_does_not_blind_fallback():
    """Broker says the coid exists but we can't fetch the order — place NOTHING
    (a fallback market buy would double the already-existing position)."""
    posts = []
    def handler(method, path, body):
        if method == "POST" and path == "/v2/orders":
            posts.append(body)
            return (422, {"code": 40010001, "message": "client_order_id must be unique"})
        if path.startswith("/v2/orders:by_client_order_id"):
            return (404, {"message": "not found"})
        return (200, {})
    r = broker.enter("ABC", 10, 100.0, 95.0, phase=1, fractional=False,
                     adapter=_adapter(handler), coid="dup-2")
    assert r["ok"] is False
    assert r["stage"] == "duplicate_unresolved"
    assert len(posts) == 1                          # NO fallback buy


def test_genuine_bracket_reject_still_falls_back():
    """A NON-duplicate reject (e.g. bracket not allowed) must still fall back to
    market+stop — the duplicate-coid handling must not swallow real rejects."""
    seen = []
    def handler(method, path, body):
        if method == "POST" and path == "/v2/orders":
            seen.append(body)
            if body.get("order_class") == "bracket":
                return (422, {"message": "bracket orders not allowed for this account"})
            return (200, {"id": "ok-%d" % len(seen)})
        return (200, {})
    r = broker.enter("ABC", 10, 100.0, 95.0, phase=1, fractional=False,
                     adapter=_adapter(handler), coid="rej-1")
    assert r["stage"] == "fallback"
    assert any(b.get("type") == "market" for b in seen)


# --- coid generator ---

def test_new_coid_is_unique_and_prefixed():
    a = broker._new_coid("enter")
    b = broker._new_coid("enter")
    assert a != b
    assert a.startswith("shark-enter-")


# --- reconciliation lookup ---

def test_reconcile_returns_order_when_found():
    a = _adapter(lambda m, p, b: (200, {"id": "br-9", "status": "new"}))
    assert broker.reconcile("some-coid", a) == {"id": "br-9", "status": "new"}


def test_reconcile_returns_none_when_not_found():
    a = _adapter(lambda m, p, b: (404, {"message": "order not found"}))
    assert broker.reconcile("some-coid", a) is None


def test_reconcile_returns_none_on_read_failure():
    a = _adapter(lambda m, p, b: (None, {"error": "timeout"}))
    assert broker.reconcile("some-coid", a) is None


# --- ambiguous-entry reconciliation: never blind-retry into a duplicate position ---

def test_entry_ambiguous_but_order_actually_placed_is_treated_as_placed():
    """Bracket POST returns no answer (None); reconcile finds the order -> it WAS placed.
    Must NOT also fire a fallback market buy (that would double the position)."""
    posts = []
    def handler(method, path, body):
        if method == "POST" and path == "/v2/orders":
            posts.append(body)
            return (None, {"error": "read timeout"})          # ambiguous
        if path.startswith("/v2/orders:by_client_order_id"):
            return (200, {"id": "br-real", "status": "new"})   # it did land
        return (200, {})
    r = broker.enter("ABC", 10, 100.0, 95.0, phase=1, fractional=False,
                     adapter=_adapter(handler), coid="amb-1")
    assert r["ok"] is True
    assert r.get("order_id") == "br-real"
    assert r.get("reconciled") is True
    assert len(posts) == 1                          # only the bracket — NO fallback buy
    assert posts[0].get("order_class") == "bracket" # the single attempt was the bracket


def test_entry_ambiguous_and_not_placed_does_not_blind_retry():
    """Bracket POST returns no answer; reconcile finds nothing -> stay fail-closed,
    place NOTHING further (no fallback buy). Operator/next fire decides."""
    posts = []
    def handler(method, path, body):
        if method == "POST" and path == "/v2/orders":
            posts.append(body)
            return (None, {"error": "dns failure"})
        if path.startswith("/v2/orders:by_client_order_id"):
            return (404, {"message": "not found"})
        return (200, {})
    r = broker.enter("ABC", 10, 100.0, 95.0, phase=1, fractional=False,
                     adapter=_adapter(handler), coid="amb-2")
    assert r["ok"] is False
    assert r["stage"] == "ambiguous"
    assert len(posts) == 1            # only the bracket attempt — NO blind fallback
