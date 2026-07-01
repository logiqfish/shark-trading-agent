#!/usr/bin/env python3
"""
Broker-neutral execution adapter (Phase 1 seam). Part of the Shark Starter Kit.

ExecutionAdapter is the broker-neutral interface the trade-manager broker speaks.
LegacyAlpacaRestAdapter is the default implementation: Alpaca paper REST (it wraps a
plain urllib request fn). Other adapters can implement the same interface so the
execution rail can swap WITHOUT touching the risk kernel, trade_manager.py, or
HEARTBEAT.

Methods return (status:int, body:dict|list) — the same shape broker.py's _req returned.
Subclasses MUST surface OCO/bracket child legs in get_open_orders(): the dire-gate's
naked-position audit depends on seeing the protective stop leg.

Stdlib only (urllib/json/ssl). Python 3.9 floor (matches the CR routine runtime).
"""
from __future__ import annotations
import json, ssl, urllib.error, urllib.parse, urllib.request


def _http(base, key, sec, method, path, body=None):
    """The single real HTTP touch.

    Returns (status:int, body) on any real broker answer — including a 4xx/5xx,
    whose code is preserved so callers can read the rejection.

    FAIL-CLOSED (Phase 2): a transport failure with NO broker answer (DNS,
    connection refused, read/connect timeout, TLS error) returns (None, {"error": ...}).
    Status None is falsy in every caller's `st and 200 <= st < 300` guard, so an
    unreachable broker reads as "order/read did NOT happen" — never as success, and
    never raises into the heartbeat. The idempotency key (see broker.client_order_id)
    is what makes recovering from an *ambiguous* write safe."""
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, data=data, method=method)
    r.add_header("APCA-API-KEY-ID", key)
    r.add_header("APCA-API-SECRET-KEY", sec)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, context=ssl.create_default_context(), timeout=20) as resp:
            txt = resp.read().decode()
            return resp.status, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as e:
        # A real broker answer with an error status — preserve the code + body.
        txt = e.read().decode()
        try:
            return e.code, json.loads(txt)
        except Exception:
            return e.code, {"raw": txt}
    except (urllib.error.URLError, OSError) as e:
        # No answer reached us (DNS / refused / timeout / TLS). Fail closed.
        # OSError covers socket.timeout (read timeout) and ConnectionError; URLError
        # covers connect-time failures. HTTPError is handled above (caught first).
        return None, {"error": str(getattr(e, "reason", e))}


class ExecutionAdapter:
    """Broker-neutral execution interface. Methods return (status:int, body)."""
    def submit_order(self, order): raise NotImplementedError
    def cancel_order(self, order_id): raise NotImplementedError
    def replace_order(self, order_id, fields): raise NotImplementedError
    def get_position(self, symbol): raise NotImplementedError
    def get_open_orders(self, symbol=None, status="open"): raise NotImplementedError
    def get_order_by_client_id(self, client_order_id): raise NotImplementedError
    def get_asset(self, symbol): raise NotImplementedError
    def get_clock(self): raise NotImplementedError

    @property
    def base(self):
        """Broker base identifier — MUST be a non-None str.

        broker.py's paper guard does `"paper" not in adapter.base`; a None base would
        raise TypeError there (still fail-closed, but obscurely). Every adapter returns
        a string."""
        raise NotImplementedError


class LegacyAlpacaRestAdapter(ExecutionAdapter):
    """Default rail: Alpaca paper REST. Byte-identical to pre-adapter broker.py."""

    def __init__(self, base, key, sec, http=_http):
        self._base, self._key, self._sec, self._http = base, key, sec, http

    @property
    def base(self):
        return self._base

    def submit_order(self, order):
        return self._http(self._base, self._key, self._sec, "POST", "/v2/orders", order)

    def cancel_order(self, order_id):
        return self._http(self._base, self._key, self._sec, "DELETE", f"/v2/orders/{order_id}")

    def replace_order(self, order_id, fields):
        return self._http(self._base, self._key, self._sec, "PATCH", f"/v2/orders/{order_id}", fields)

    def get_position(self, symbol):
        return self._http(self._base, self._key, self._sec, "GET",
                          f"/v2/positions/{urllib.parse.quote(symbol, safe='')}")

    def get_open_orders(self, symbol=None, status="open"):
        # status="all" surfaces bracket legs that rest in Alpaca status "held"
        # (a "status=open" query excludes both the filled parent and the held leg)
        # — the dire-gate naked check relies on seeing a "held" protective stop.
        if symbol:
            sym = urllib.parse.quote(symbol, safe="")
            path = f"/v2/orders?status={status}&symbols={sym}&nested=true&limit=50"
        else:
            path = f"/v2/orders?status={status}&nested=true&limit=50"
        return self._http(self._base, self._key, self._sec, "GET", path)

    def get_order_by_client_id(self, client_order_id):
        # Reconciliation lookup: learn the true broker state of a write after an
        # ambiguous/timed-out response, so callers never blind-retry into a duplicate.
        coid = urllib.parse.quote(client_order_id, safe="")
        return self._http(self._base, self._key, self._sec, "GET",
                          f"/v2/orders:by_client_order_id?client_order_id={coid}")

    def get_asset(self, symbol):
        return self._http(self._base, self._key, self._sec, "GET",
                          f"/v2/assets/{urllib.parse.quote(symbol, safe='')}")

    def get_clock(self):
        return self._http(self._base, self._key, self._sec, "GET", "/v2/clock")
