"""Hand-crafted fixture data for the semantic-layer transformations.

Eleven policies, each planted to exercise one subtlety from spec 02 and the ADRs.
Fixtures are the ground truth for this suite: the generator (task P1) is owned by
another agent and may still be moving, so nothing here depends on its output.

Every date is ``anchor - offset``, mirroring ADR-0006's rule that no absolute date
literal appears anywhere, so the suite behaves identically whenever it runs.

    P-10001  coverage raised then claimed on the same line; three changes sharing
             one Linked Claim (many-to-one); a later unlinked coverage change;
             repeat-category offset; an SCD2 address transition
    P-10002  change inside the Loss-to-Report Gap; a change dated exactly on the
             report date; two claims whose loss order and report order disagree
    P-10003  changes, never claimed — all seven linkage columns NULL
    P-10004  categorical changes; a zero old value; a well-defined change_pct
    P-10005  rapid change cluster; utilisation above 100%; four patterns at once
    P-10006  deductible lowered before a claim
    P-10007  claim at 97% of a newly raised limit, moderate band (ADR-0008's
             signature two-axis conjunction)
    P-10008  vehicle and address within 60 days, no claims
    P-10009  a claim with no preceding change (control)
    P-10010  a change dated the same day as the loss
    P-10011  a zero limit — utilisation must be NULL, not a sentinel
"""

from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ANCHOR = _dt.date(2025, 6, 30)
FAR_FUTURE = _dt.date(9999, 12, 31)


def D(offset_days: int) -> _dt.date:
    """``anchor - offset_days``. No absolute date literals (ADR-0006)."""
    return ANCHOR - _dt.timedelta(days=offset_days)


# ---------------------------------------------------------------------------
# SCD Type 2 builders
# ---------------------------------------------------------------------------

def _scd2(base: dict, start: _dt.date, transitions: list[tuple[_dt.date, dict]]) -> list[dict]:
    points = [(start, {})] + sorted(transitions, key=lambda t: t[0])
    rows, state = [], dict(base)
    for index, (effective_from, delta) in enumerate(points, start=1):
        state = {**state, **delta}
        rows.append({**state, "version_no": index, "effective_from": effective_from})
    for index, row in enumerate(rows):
        row["effective_to"] = (
            rows[index + 1]["effective_from"] if index + 1 < len(rows) else FAR_FUTURE
        )
        row["is_current"] = index == len(rows) - 1
    return rows


def _policy_versions(policy_id, customer_id, start, transitions=(), **base) -> list[dict]:
    defaults = {
        "policy_id": policy_id,
        "customer_id": customer_id,
        "policy_status": "active",
        "agent_id": "AGT-0001",
        "garaging_city": "Austin",
        "garaging_state": "TX",
        "garaging_postal_code": "73301",
        "primary_vehicle_id": "VEH-000001",
        "term_start_date": start,
        "term_end_date": start + _dt.timedelta(days=365),
        "annual_premium": 1200.0,
        "endorsement_id": None,
    }
    defaults.update(base)
    return _scd2(defaults, start, list(transitions))


def _coverage_versions(policy_id, line, start, limit, deductible=None, transitions=()) -> list[dict]:
    base = {
        "policy_id": policy_id,
        "coverage_line": line,
        "limit_amount": limit,
        "deductible_amount": deductible,
        "endorsement_id": None,
    }
    return _scd2(base, start, list(transitions))


# ---------------------------------------------------------------------------
# The dataset
# ---------------------------------------------------------------------------

def _policy_history() -> list[dict]:
    rows: list[dict] = []
    rows += _policy_versions(
        "P-10001", "C-000001", D(900),
        transitions=[(D(55), {"garaging_city": "Dallas", "garaging_state": "CA",
                              "endorsement_id": "END-00000003"})],
    )
    rows += _policy_versions("P-10002", "C-000002", D(800))
    rows += _policy_versions("P-10003", "C-000003", D(700))
    rows += _policy_versions("P-10004", "C-000004", D(600))
    rows += _policy_versions(
        "P-10005", "C-000005", D(500),
        # A renewal: a new term starting, never emitted as a Policy Change.
        transitions=[(D(135), {"term_start_date": D(135),
                               "term_end_date": D(135) + _dt.timedelta(days=365)})],
    )
    rows += _policy_versions("P-10006", "C-000006", D(450))
    rows += _policy_versions("P-10007", "C-000007", D(400))
    rows += _policy_versions("P-10008", "C-000008", D(350))
    rows += _policy_versions("P-10009", "C-000009", D(300))
    rows += _policy_versions("P-10010", "C-000010", D(250))
    rows += _policy_versions("P-10011", "C-000011", D(200))
    return rows


def _policy_coverage_history() -> list[dict]:
    rows: list[dict] = []
    rows += _coverage_versions("P-10001", "COLL", D(900), 25000.0, 500.0,
                               transitions=[(D(41), {"limit_amount": 50000.0}),
                                            (D(10), {"limit_amount": 60000.0})])
    rows += _coverage_versions("P-10001", "BI", D(900), 100000.0)
    rows += _coverage_versions("P-10002", "COLL", D(800), 25000.0, 500.0)
    rows += _coverage_versions("P-10003", "COLL", D(700), 25000.0, 500.0,
                               transitions=[(D(200), {"limit_amount": 30000.0})])
    rows += _coverage_versions("P-10004", "COMP", D(600), 20000.0, 0.0,
                               transitions=[(D(200), {"deductible_amount": 500.0})])
    rows += _coverage_versions("P-10004", "COLL", D(600), 1000.0, 500.0,
                               transitions=[(D(150), {"limit_amount": 1500.0})])
    rows += _coverage_versions("P-10005", "COLL", D(500), 25000.0, 500.0,
                               transitions=[(D(82), {"limit_amount": 40000.0})])
    rows += _coverage_versions("P-10006", "COMP", D(450), 20000.0, 1000.0,
                               transitions=[(D(52), {"deductible_amount": 500.0})])
    rows += _coverage_versions("P-10007", "COLL", D(400), 6000.0, 500.0,
                               transitions=[(D(66), {"limit_amount": 10000.0})])
    rows += _coverage_versions("P-10008", "COLL", D(350), 25000.0, 500.0)
    rows += _coverage_versions("P-10009", "BI", D(300), 100000.0)
    rows += _coverage_versions("P-10010", "COLL", D(250), 12000.0, 500.0,
                               transitions=[(D(45), {"limit_amount": 15000.0})])
    # A zero limit: utilisation must be NULL rather than a sentinel or a divide
    # by zero (E10).
    rows += _coverage_versions("P-10011", "UMUIM", D(200), 0.0)
    return rows


def _change(cid, policy_id, offset, category, *, line=None, old=None, new=None,
            old_num=None, new_num=None, endorsement=None) -> dict:
    return {
        "change_event_id": cid,
        "policy_id": policy_id,
        "endorsement_id": endorsement or f"END-{cid[-8:]}",
        "change_date": D(offset),
        "change_category": category,
        "coverage_line": line,
        "old_value": old,
        "new_value": new,
        "old_value_num": old_num,
        "new_value_num": new_num,
    }


def _changes() -> list[dict]:
    return [
        # --- P-10001 -------------------------------------------------------
        _change("CHG-00000103", "P-10001", 55, "address",
                old="Austin, TX", new="Dallas, CA", endorsement="END-00000003"),
        # One endorsement, two deltas: the coverage decision and its premium echo.
        _change("CHG-00000101", "P-10001", 41, "coverage", line="COLL",
                old="25000", new="50000", old_num=25000.0, new_num=50000.0,
                endorsement="END-00000001"),
        _change("CHG-00000102", "P-10001", 41, "premium",
                old="1200", new="1310", old_num=1200.0, new_num=1310.0,
                endorsement="END-00000001"),
        # After the claim was reported: no later claim, so unlinked.
        _change("CHG-00000104", "P-10001", 10, "coverage", line="COLL",
                old="50000", new="60000", old_num=50000.0, new_num=60000.0),

        # --- P-10002 -------------------------------------------------------
        _change("CHG-00000203", "P-10002", 70, "coverage", line="COLL",
                old="25000", new="25500", old_num=25000.0, new_num=25500.0),
        # Inside the Loss-to-Report Gap of CLM-000201.
        _change("CHG-00000201", "P-10002", 28, "address",
                old="Austin, TX", new="Houston, TX"),
        # Dated exactly on CLM-000201's report date.
        _change("CHG-00000202", "P-10002", 19, "status", old="active", new="lapsed"),

        # --- P-10003: changes, never claimed --------------------------------
        _change("CHG-00000301", "P-10003", 200, "coverage", line="COLL",
                old="25000", new="30000", old_num=25000.0, new_num=30000.0),
        _change("CHG-00000302", "P-10003", 150, "vehicle",
                old="VEH-000001", new="VEH-000002"),
        _change("CHG-00000303", "P-10003", 100, "address",
                old="Austin, TX", new="Waco, TX"),

        # --- P-10004: categoricals, a zero old value, a real percentage -----
        _change("CHG-00000401", "P-10004", 300, "vehicle",
                old="VEH-000001", new="VEH-000002"),
        _change("CHG-00000402", "P-10004", 250, "status", old="active", new="lapsed"),
        _change("CHG-00000403", "P-10004", 200, "deductible", line="COMP",
                old="0", new="500", old_num=0.0, new_num=500.0),
        _change("CHG-00000404", "P-10004", 180, "agent",
                old="AGT-0001", new="AGT-0002"),
        _change("CHG-00000405", "P-10004", 150, "coverage", line="COLL",
                old="1000", new="1500", old_num=1000.0, new_num=1500.0),

        # --- P-10005: four material changes across 22 days ------------------
        _change("CHG-00000501", "P-10005", 82, "coverage", line="COLL",
                old="25000", new="40000", old_num=25000.0, new_num=40000.0),
        _change("CHG-00000502", "P-10005", 75, "vehicle",
                old="VEH-000001", new="VEH-000003"),
        _change("CHG-00000503", "P-10005", 68, "address",
                old="Austin, TX", new="Plano, TX"),
        _change("CHG-00000504", "P-10005", 60, "status", old="active", new="reinstated"),

        # --- P-10006: deductible lowered before a claim ---------------------
        _change("CHG-00000601", "P-10006", 52, "deductible", line="COMP",
                old="1000", new="500", old_num=1000.0, new_num=500.0),

        # --- P-10007: limit raised, then a near-limit moderate claim --------
        _change("CHG-00000701", "P-10007", 66, "coverage", line="COLL",
                old="6000", new="10000", old_num=6000.0, new_num=10000.0),

        # --- P-10008: vehicle and address, no claims ------------------------
        _change("CHG-00000801", "P-10008", 73, "vehicle",
                old="VEH-000001", new="VEH-000004"),
        _change("CHG-00000802", "P-10008", 48, "address",
                old="Austin, TX", new="Frisco, TX"),

        # --- P-10010: a change dated the same day as the loss ---------------
        _change("CHG-00001001", "P-10010", 45, "coverage", line="COLL",
                old="12000", new="15000", old_num=12000.0, new_num=15000.0),
    ]


def _claims() -> list[dict]:
    return [
        {"claim_id": "CLM-000101", "policy_id": "P-10001", "coverage_line": "COLL",
         "loss_date": D(17), "report_date": D(12), "settled_amount": 30000.0,
         "claim_status": "settled"},
        # Loss order and report order disagree: CLM-000202's loss is earlier but
        # its report is later, so report-date anchoring must pick CLM-000201.
        {"claim_id": "CLM-000201", "policy_id": "P-10002", "coverage_line": "COLL",
         "loss_date": D(34), "report_date": D(19), "settled_amount": 4000.0,
         "claim_status": "settled"},
        {"claim_id": "CLM-000202", "policy_id": "P-10002", "coverage_line": "COLL",
         "loss_date": D(60), "report_date": D(5), "settled_amount": 2000.0,
         "claim_status": "settled"},
        {"claim_id": "CLM-000501", "policy_id": "P-10005", "coverage_line": "COLL",
         "loss_date": D(31), "report_date": D(25), "settled_amount": 60000.0,
         "claim_status": "settled"},
        {"claim_id": "CLM-000601", "policy_id": "P-10006", "coverage_line": "COMP",
         "loss_date": D(20), "report_date": D(14), "settled_amount": 3000.0,
         "claim_status": "settled"},
        {"claim_id": "CLM-000701", "policy_id": "P-10007", "coverage_line": "COLL",
         "loss_date": D(30), "report_date": D(26), "settled_amount": 9700.0,
         "claim_status": "settled"},
        {"claim_id": "CLM-000901", "policy_id": "P-10009", "coverage_line": "BI",
         "loss_date": D(40), "report_date": D(30), "settled_amount": 15000.0,
         "claim_status": "settled"},
        {"claim_id": "CLM-001001", "policy_id": "P-10010", "coverage_line": "COLL",
         "loss_date": D(45), "report_date": D(40), "settled_amount": 1000.0,
         "claim_status": "settled"},
        {"claim_id": "CLM-001101", "policy_id": "P-10011", "coverage_line": "UMUIM",
         "loss_date": D(60), "report_date": D(55), "settled_amount": 5000.0,
         "claim_status": "settled"},
    ]


def _claim_payments() -> list[dict]:
    return [
        {"payment_id": "PAY-000001", "claim_id": "CLM-000101",
         "payment_date": D(8), "amount": 30000.0},
        {"payment_id": "PAY-000002", "claim_id": "CLM-000501",
         "payment_date": D(20), "amount": 60000.0},
    ]


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def anchor_date() -> _dt.date:
    return ANCHOR


@pytest.fixture(scope="session")
def sources() -> dict:
    import pandas as pd

    return {
        "policy_history": pd.DataFrame(_policy_history()),
        "policy_coverage_history": pd.DataFrame(_policy_coverage_history()),
        "changes": pd.DataFrame(_changes()),
        "claims": pd.DataFrame(_claims()),
        "claim_payment": pd.DataFrame(_claim_payments()),
    }


@pytest.fixture(scope="session")
def curated(sources, anchor_date) -> dict:
    import transformations as T

    return T.build_all(
        changes=sources["changes"],
        claims=sources["claims"],
        policy_history=sources["policy_history"],
        policy_coverage_history=sources["policy_coverage_history"],
        claim_payment=sources["claim_payment"],
        anchor_date=anchor_date,
        k=5,  # eleven policies in the fixture; K=20 is asserted separately
    )


@pytest.fixture(scope="session")
def change_event(curated):
    return curated["policy_change_event"]


@pytest.fixture(scope="session")
def claim_event(curated):
    return curated["claim_event"]


@pytest.fixture(scope="session")
def policy_profile(curated):
    return curated["policy_profile"]


@pytest.fixture(scope="session")
def timeline_event(curated):
    return curated["policy_timeline_event"]


@pytest.fixture(scope="session")
def pattern_match(curated):
    return curated["policy_pattern_match"]


@pytest.fixture(scope="session")
def similarity(curated):
    return curated["policy_similarity"]


# ---------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------

def row_by(frame, **filters):
    """The single row matching ``filters``; fails loudly if not exactly one."""
    subset = frame
    for column, value in filters.items():
        subset = subset[subset[column] == value]
    assert len(subset) == 1, f"expected exactly one row for {filters}, got {len(subset)}"
    return subset.iloc[0]


def rows_by(frame, **filters):
    subset = frame
    for column, value in filters.items():
        subset = subset[subset[column] == value]
    return subset
