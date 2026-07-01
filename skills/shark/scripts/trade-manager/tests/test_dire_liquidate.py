"""dire-gate liquidation guard — is_protected() + dire_liquidate().

The trigger-2 liquidation path must NEVER sell a position that has a resting
protective stop leg (the 2026-06-22 false self-liquidation). The decision is made
in code (broker's leg walk), not by the LLM reading JSON.

CRITICAL real-world shape (ZETA, 2026-06-24): a bracket's protective stop leg can
rest in Alpaca status "held", and a `status=open` query does NOT return it (the
filled parent + held leg are both excluded). is_protected MUST query status=all
(nested) and walk legs, treating any non-terminal sell-stop as protection.

Tested with the injected fake-http adapter (real broker code), mirroring
test_manage_dispatch.py.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import broker
from execution_adapter import LegacyAlpacaRestAdapter

PAPER = "https://paper-api.alpaca.markets"
# is_protected queries status=all (so a "held" stop leg is visible):
ORDERS_PATH = "/v2/orders?status=all&symbols=ABBV&nested=true&limit=50"
POS_PATH = "/v2/positions/ABBV"


def _rec(responses=None):
    responses = responses or {}
    calls = []

    def req(base, key, sec, method, path, body=None):
        calls.append((method, path, body))
        return responses.get((method, path), (200, {"id": path.rsplit("/", 1)[-1]}))
    return req, calls


def _adapter(req, base=PAPER):
    return LegacyAlpacaRestAdapter(base, "k", "s", http=req)


def _pos(qty="100"):
    return (200, {"symbol": "ABBV", "qty": qty, "avg_entry_price": "100.00",
                  "current_price": "101.00"})


# bracket parent (filled) carrying both exit legs — the real ZETA shape
def _filled_bracket(stop_status="held"):
    return {"id": "p1", "side": "buy", "type": "market", "status": "filled", "legs": [
        {"id": "t1", "side": "sell", "type": "limit", "status": "new", "limit_price": "120"},
        {"id": "s1", "side": "sell", "type": "stop", "status": stop_status,
         "stop_price": "95", "qty": "100"}]}


# ---------- is_protected ----------

def test_is_protected_true_when_held_stop_leg_under_filled_bracket():
    # THE ZETA case: stop leg rests in status "held" under a filled bracket parent.
    resp = {("GET", ORDERS_PATH): (200, [_filled_bracket("held")]), ("GET", POS_PATH): _pos()}
    req, _ = _rec(resp)
    out = broker.is_protected("ABBV", _adapter(req))
    assert out["protected"] is True
    assert out["stop_id"] == "s1" and out["stop_price"] == 95.0


def test_is_protected_true_when_toplevel_held_stop():
    resp = {("GET", ORDERS_PATH): (200, [
                {"id": "s1", "side": "sell", "type": "stop", "status": "held",
                 "stop_price": "95", "qty": "100"}]),
            ("GET", POS_PATH): _pos()}
    req, _ = _rec(resp)
    assert broker.is_protected("ABBV", _adapter(req))["protected"] is True


def test_is_protected_false_when_only_take_profit_limit():
    resp = {("GET", ORDERS_PATH): (200, [
                {"id": "p1", "side": "buy", "type": "market", "status": "filled",
                 "legs": [{"id": "t1", "side": "sell", "type": "limit",
                           "status": "new", "limit_price": "120"}]}]),
            ("GET", POS_PATH): _pos()}
    req, _ = _rec(resp)
    assert broker.is_protected("ABBV", _adapter(req))["protected"] is False


def test_is_protected_false_when_stop_is_canceled():
    # a dead (canceled) stop leg does NOT protect — status=all returns it, must be ignored.
    resp = {("GET", ORDERS_PATH): (200, [_filled_bracket("canceled")]), ("GET", POS_PATH): _pos()}
    req, _ = _rec(resp)
    assert broker.is_protected("ABBV", _adapter(req))["protected"] is False


def test_is_protected_false_when_no_orders():
    resp = {("GET", ORDERS_PATH): (200, []), ("GET", POS_PATH): _pos()}
    req, _ = _rec(resp)
    assert broker.is_protected("ABBV", _adapter(req))["protected"] is False


def test_is_protected_failsafe_true_when_orders_read_errors():
    # transient API error must read as PROTECTED, never as naked.
    resp = {("GET", ORDERS_PATH): (500, {"message": "boom"}), ("GET", POS_PATH): _pos()}
    req, _ = _rec(resp)
    out = broker.is_protected("ABBV", _adapter(req))
    assert out["protected"] is True and out["reason"] == "orders_read_failed"


# ---------- dire_liquidate ----------

def test_dire_liquidate_refuses_and_places_no_order_when_held_stop_exists():
    # THE ZETA case end-to-end: must NOT sell a position whose stop rests in "held".
    resp = {("GET", ORDERS_PATH): (200, [_filled_bracket("held")]), ("GET", POS_PATH): _pos()}
    req, calls = _rec(resp)
    out = broker.dire_liquidate("ABBV", qty=100, adapter=_adapter(req))
    assert out["ok"] is False and out["stage"] == "blocked_protected"
    assert out["holding"] is True and out["alert"] is True and out["stop_price"] == 95.0
    assert not any(m == "POST" for (m, p, b) in calls), "must place NO order when protected"


def test_dire_liquidate_sells_live_held_qty_when_naked():
    # passed qty is wrong (5); the live position holds 100 -> must sell 100.
    resp = {("GET", ORDERS_PATH): (200, []), ("GET", POS_PATH): _pos("100")}
    req, calls = _rec(resp)
    out = broker.dire_liquidate("ABBV", qty=5, adapter=_adapter(req))
    sells = [b for (m, p, b) in calls if m == "POST" and p == "/v2/orders"]
    assert len(sells) == 1
    assert sells[0]["side"] == "sell" and sells[0]["type"] == "market"
    assert sells[0]["qty"] == "100"
    assert out["ok"] is True and out["stage"] == "liquidated" and out["sold_qty"] == 100


def test_dire_liquidate_respects_paper_guard():
    req, calls = _rec()
    out = broker.dire_liquidate("ABBV", qty=100, adapter=_adapter(req, base="https://api.alpaca.markets"))
    assert out["ok"] is False and out["stage"] == "guard"
    assert not any(m == "POST" for (m, p, b) in calls)


def test_dire_liquidate_noop_when_already_flat():
    resp = {("GET", ORDERS_PATH): (200, []), ("GET", POS_PATH): (404, {"message": "position not found"})}
    req, calls = _rec(resp)
    out = broker.dire_liquidate("ABBV", qty=100, adapter=_adapter(req))
    assert out["ok"] is True and out["stage"] == "already_flat" and out["sold_qty"] == 0
    assert not any(m == "POST" for (m, p, b) in calls)
