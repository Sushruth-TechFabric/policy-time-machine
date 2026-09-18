from unittest.mock import MagicMock

import backend.review.routing as routing
from backend.review.store import InMemoryReviewStore


def test_routing_sql_encodes_the_rule():
    assert "severity_band IN ('severe', 'catastrophic')" in routing.ROUTING_SQL
    assert "date_sub(m.anchor_date, 90)" in routing.ROUTING_SQL
    assert "generation_manifest" in routing.ROUTING_SQL


def test_route_claims_upserts_each_row_as_rule_routed(monkeypatch):
    rows = [{"claim_id": "C-1", "policy_id": "P-1", "coverage_line": "COLL", "loss_date": "2026-08-01",
             "report_date": "2026-08-05", "settled_amount": "24700", "severity_band": "severe", "anchor_date": "2026-09-17"}]
    monkeypatch.setattr(routing, "run_query", lambda client, sql, params=None: rows)
    store = InMemoryReviewStore()
    assert routing.route_claims(MagicMock(), store) == 1
    row = store.list_queue()[0]
    assert row["routed_by"] == "rule" and row["routing_rule"] == routing.ROUTING_RULE_TEXT
    assert row["settled_amount"] == 24700.0
