"""The one Routing Rule (CONTEXT.md): a High-Severity Claim whose Report
Date is Recent, measured from the dataset anchor (ADR-0006) so the queue
is stable across regenerations."""

from __future__ import annotations

from databricks.sdk import WorkspaceClient

from ..config import CATALOG, SCHEMA
from ..warehouse import run_query

ROUTING_RULE_TEXT = "High-severity claim reported in the last 90 days."

ROUTING_SQL = f"""
SELECT c.claim_id, c.policy_id, c.coverage_line, CAST(c.loss_date AS STRING) AS loss_date,
       CAST(c.report_date AS STRING) AS report_date, c.settled_amount, c.severity_band,
       CAST(m.anchor_date AS STRING) AS anchor_date
FROM {CATALOG}.{SCHEMA}.claim_event c
CROSS JOIN (SELECT anchor_date FROM {CATALOG}.ptm_bronze.generation_manifest LIMIT 1) m
WHERE c.severity_band IN ('severe', 'catastrophic')
  AND c.report_date >= date_sub(m.anchor_date, 90)
ORDER BY c.report_date DESC
""".strip()


def route_claims(client: WorkspaceClient, store) -> int:
    rows = run_query(client, ROUTING_SQL)
    for row in rows:
        store.upsert_routed_claim(
            {"claim_id": row["claim_id"], "policy_id": row["policy_id"], "coverage_line": row["coverage_line"],
             "loss_date": row["loss_date"], "report_date": row["report_date"],
             "settled_amount": float(row["settled_amount"]), "severity_band": row["severity_band"]},
            routed_by="rule", routing_rule=ROUTING_RULE_TEXT,
        )
    return len(rows)
