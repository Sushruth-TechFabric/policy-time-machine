"""Ground truth for the fifteen query contracts (spec 05), computed once
per run directly from the curated tables and `scenario_assignment` via
warehouse SQL — never from Genie's own SQL (ADR-0015).

One `load()` call does every warehouse round-trip up front so the three
repeated runs per contract don't re-derive the same facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from databricks.sdk import WorkspaceClient

from . import config
from .genie_client import run_warehouse_query

# Declared effect-size ordering, ADR-0014 / spec 01 §8. Ranking contracts
# assert this ordering, never the magnitudes.
DECLARED_CATEGORY_ORDER = ["coverage", "deductible", "vehicle", "status", "address"]

# Approved vocabulary boundary, spec 03 §7 / ADR-0014. QC-13's negative
# assertion checks Genie's prose against this banned list.
BANNED_VOCABULARY = [
    "fraud",
    "fraudulent",
    "suspicious",
    "scheme",
    "deceptive",
    "guilty",
    "risk score",
    "predicts",
    "causes",
    "leads to",
    "increases the risk of",
]

VALID_PATTERN_CODES = {
    "change_in_loss_report_gap",
    "claim_near_new_limit",
    "coverage_raised_then_claimed_same_line",
    "deductible_lowered_before_claim",
    "rapid_change_cluster",
    "vehicle_and_address_within_60d",
}
VALID_PATTERN_NAMES = {
    "Change during the loss-to-report gap",
    "Claim near a newly raised limit",
    "Coverage raised, then a claim on the same line",
    "Deductible lowered before a claim",
    "Rapid change cluster",
    "Vehicle and address changed within 60 days",
}


def _q(client: WorkspaceClient, sql: str) -> list[dict[str, Any]]:
    return run_warehouse_query(
        client, config.WAREHOUSE_ID, config.CATALOG, config.SCHEMA, sql
    )


def _ids(rows: list[dict[str, Any]], col: str = "policy_id") -> set[str]:
    return {r[col] for r in rows}


@dataclass
class GroundTruth:
    anchor_date: str
    demo_policy_id: str

    # QC-01
    qc01_window_start: str
    qc01_must_include: list[dict[str, Any]]
    qc01_must_exclude_before: str

    # QC-02
    qc02_loss_date: str
    qc02_must_include: list[dict[str, Any]]

    # QC-03
    qc03_s1_ids: set[str]
    qc03_exclude_ids: set[str]
    qc03_trap_ids: set[str]

    # QC-04
    qc04_s4_ids: set[str]
    qc04_exclude_ids: set[str]

    # QC-07
    qc07_s2_ids: set[str]
    qc07_exclude_ids: set[str]
    qc07_trap_ids: set[str]

    # QC-08
    qc08_s5_ids: set[str]

    # QC-09
    qc09_top10: list[dict[str, Any]]

    # QC-10
    qc10_n_recent: int
    qc10_n_not_recent: int

    # QC-11
    qc11_neighbours: list[dict[str, Any]]

    # QC-12
    qc12_top_claims: list[dict[str, Any]]
    qc12_c1_top_claim_ids: set[str]

    # QC-14
    qc14_pattern_counts: dict[str, int]

    # QC-15
    qc15_s6_ids: set[str]

    raw: dict[str, Any] = field(default_factory=dict)


def load(client: WorkspaceClient) -> GroundTruth:
    manifest = _q(client, "SELECT anchor_date, demo_policy_id FROM generation_manifest")[0]
    anchor_date = str(manifest["anchor_date"])
    demo_policy_id = manifest["demo_policy_id"] or config.DEMO_POLICY_ID

    # --- scenario populations -------------------------------------------------
    def scenario_ids(scenario_id: str) -> set[str]:
        rows = _q(
            client,
            f"SELECT policy_id FROM scenario_assignment WHERE scenario_id = '{scenario_id}'",
        )
        return _ids(rows)

    s1 = scenario_ids("S1")
    s2 = scenario_ids("S2")
    s4 = scenario_ids("S4")
    s5 = scenario_ids("S5")
    s6 = scenario_ids("S6")
    c1 = scenario_ids("C1")
    c2 = scenario_ids("C2")

    # --- QC-01 / QC-02: demo policy timeline -----------------------------------
    timeline = _q(
        client,
        f"""
        SELECT event_date, event_type, event_category, display_label,
               old_value, new_value, amount
        FROM policy_timeline_event
        WHERE policy_id = '{demo_policy_id}'
        ORDER BY event_date
        """,
    )
    window_row = _q(
        client, f"SELECT DATE('{anchor_date}') - INTERVAL 365 DAYS AS cutoff"
    )[0]
    cutoff = str(window_row["cutoff"])
    qc01_must_include = [
        r for r in timeline
        if str(r["event_date"]) >= cutoff
        and (
            (r["event_category"] == "address" and r["event_type"] == "policy_change")
            or (r["event_category"] == "coverage" and r["event_type"] == "policy_change")
            or (r["event_category"] == "vehicle" and r["event_type"] == "policy_change")
            or (r["event_type"] == "claim_filed")
        )
    ]

    claim = _q(
        client,
        f"""
        SELECT claim_id, loss_date, report_date, severity_band
        FROM claim_event WHERE policy_id = '{demo_policy_id}'
        ORDER BY loss_date DESC LIMIT 1
        """,
    )[0]
    loss_date = str(claim["loss_date"])
    material_changes = _q(
        client,
        f"""
        SELECT change_date, change_category, old_value, new_value
        FROM policy_change_event
        WHERE policy_id = '{demo_policy_id}'
          AND next_claim_id = '{claim["claim_id"]}'
          AND is_material = true
          AND change_timing = 'before_loss'
        ORDER BY change_date
        """,
    )

    # --- QC-03: coverage increase within 30d before claim ----------------------
    qc03_trap = _q(
        client,
        """
        SELECT DISTINCT policy_id FROM policy_change_event
        WHERE change_category = 'coverage' AND change_direction = 'increase'
          AND next_claim_id IS NOT NULL
          AND days_to_next_claim_loss <= 30
          AND NOT (change_timing = 'before_loss' AND days_to_next_claim_loss <= 30)
        """,
    )

    # --- QC-07: deductible decreased before claim, trap -------------------------
    qc07_trap = _q(
        client,
        """
        SELECT DISTINCT policy_id FROM policy_change_event
        WHERE change_category = 'deductible' AND change_direction = 'decrease'
          AND next_claim_id IS NOT NULL
          AND NOT (change_timing = 'before_loss')
        """,
    )

    # --- QC-09: table-routed, top 10 customers by material_change_count --------
    qc09_top10 = _q(
        client,
        """
        SELECT customer_id, SUM(material_change_count) AS material_change_count
        FROM policy_profile
        GROUP BY customer_id
        ORDER BY material_change_count DESC, customer_id ASC
        LIMIT 10
        """,
    )

    # --- QC-10: comparison group sizes (90-day default, query-time) ------------
    groups = _q(
        client,
        """
        SELECT CASE WHEN last_material_change_date >= CURRENT_DATE - INTERVAL 90 DAY
                    THEN 'recent' ELSE 'not_recent' END AS grp,
               COUNT(*) AS n
        FROM policy_profile GROUP BY 1
        """,
    )
    n_recent = next(r["n"] for r in groups if r["grp"] == "recent")
    n_not_recent = next(r["n"] for r in groups if r["grp"] == "not_recent")

    # --- QC-11: table-routed similarity neighbours ------------------------------
    qc11_neighbours = _q(
        client,
        f"""
        SELECT rank, similar_policy_id, similarity_score
        FROM policy_similarity WHERE policy_id = '{demo_policy_id}'
        ORDER BY rank
        """,
    )

    # --- QC-12: largest claims, must include >=1 C1 (no preceding change) ------
    qc12_top_claims = _q(
        client,
        """
        SELECT cl.claim_id, cl.policy_id, cl.settled_amount, sa.scenario_id
        FROM claim_event cl
        LEFT JOIN scenario_assignment sa ON sa.policy_id = cl.policy_id
        ORDER BY cl.settled_amount DESC
        LIMIT 20
        """,
    )
    qc12_c1_top_claim_ids = {
        r["policy_id"] for r in qc12_top_claims if r["scenario_id"] == "C1"
    }

    # --- QC-14: table-routed pattern counts -------------------------------------
    qc14_rows = _q(
        client,
        "SELECT pattern_name, COUNT(DISTINCT policy_id) AS n FROM policy_pattern_match GROUP BY pattern_name",
    )
    qc14_counts = {r["pattern_name"]: int(r["n"]) for r in qc14_rows}

    return GroundTruth(
        anchor_date=anchor_date,
        demo_policy_id=demo_policy_id,
        qc01_window_start=cutoff,
        qc01_must_include=qc01_must_include,
        qc01_must_exclude_before=cutoff,
        qc02_loss_date=loss_date,
        qc02_must_include=material_changes,
        qc03_s1_ids=s1,
        qc03_exclude_ids=c1 | c2,
        qc03_trap_ids=_ids(qc03_trap),
        qc04_s4_ids=s4,
        qc04_exclude_ids=c1 | c2,
        qc07_s2_ids=s2,
        qc07_exclude_ids=c1,
        qc07_trap_ids=_ids(qc07_trap),
        qc08_s5_ids=s5,
        qc09_top10=qc09_top10,
        qc10_n_recent=int(n_recent),
        qc10_n_not_recent=int(n_not_recent),
        qc11_neighbours=qc11_neighbours,
        qc12_top_claims=qc12_top_claims,
        qc12_c1_top_claim_ids=qc12_c1_top_claim_ids,
        qc14_pattern_counts=qc14_counts,
        qc15_s6_ids=s6,
        raw={"timeline": timeline, "claim": claim, "material_changes": material_changes},
    )
