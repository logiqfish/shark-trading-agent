"""Characterization: the bracket entry emits the exact HTTP it always did."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import broker, trade_manager as tm
from execution_adapter import LegacyAlpacaRestAdapter


def test_bracket_entry_http_is_byte_identical_to_plan_entry_payload():
    captured = {}
    def http(base, key, sec, method, path, body=None):
        captured["call"] = (method, path, body)
        return (200, {"id": "br-1"})
    a = LegacyAlpacaRestAdapter("https://paper-api.alpaca.markets", "k", "s", http=http)

    broker.enter("ABC", 10, 100.0, 95.0, phase=1, fractional=False, adapter=a,
                 coid="parity-coid")

    # Every STRATEGY field must equal exactly what plan_entry() produced — the adapter
    # is transparent. The one intentional Phase-2 addition is client_order_id (an
    # idempotency label; it does not change fills/pricing/bracket structure, so the
    # validation clock is undisturbed).
    expected_body = dict(tm.plan_entry("ABC", 100.0, 95.0, 10.0, 1, fractional=False)["orders"][0])
    expected_body["client_order_id"] = "parity-coid"
    assert captured["call"] == ("POST", "/v2/orders", expected_body)
