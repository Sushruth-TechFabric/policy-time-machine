"""claim_context: behaviour facts and the first-notice note, one row per claim."""

import datetime as _dt

import transformations as T

ANCHOR = _dt.date(2025, 6, 30)


def D(offset):
    return ANCHOR - _dt.timedelta(days=offset)


def version(policy_id, n, start, status="active"):
    return {"policy_id": policy_id, "version_no": n, "effective_from": start,
            "effective_to": _dt.date(9999, 12, 31), "is_current": False,
            "policy_status": status, "customer_id": "CUS-1"}


def claim(claim_id, policy_id, loss, report):
    return {"claim_id": claim_id, "policy_id": policy_id, "coverage_line": "COLL",
            "loss_date": loss, "report_date": report, "settled_amount": 1000.0,
            "claim_status": "settled"}


def by_id(frame):
    return {row["claim_id"]: row for row in T.records(frame)}


def test_schema_and_one_row_per_claim():
    out = T.build_claim_context(
        [claim("CLM-1", "P-10001", D(10), D(5))], [version("P-10001", 1, D(400))],
        [], [{"claim_id": "CLM-1", "note_text": "Caller reports a collision."}])
    assert list(out.columns) == [name for name, _ in T.CLAIM_CONTEXT_SCHEMA]
    row = by_id(out)["CLM-1"]
    assert row["policy_age_at_loss_days"] == 390
    assert row["prior_claims_count"] == 0 and row["days_since_prior_claim"] is None
    assert row["note_text"] == "Caller reports a collision."


def test_prior_claims_are_counted_on_report_date_not_loss_date():
    # CLM-B lost earlier but reported later, so CLM-A is its prior claim.
    claims = [claim("CLM-A", "P-10002", D(34), D(19)), claim("CLM-B", "P-10002", D(60), D(5))]
    rows = by_id(T.build_claim_context(claims, [version("P-10002", 1, D(500))], [], []))
    assert rows["CLM-A"]["prior_claims_count"] == 0
    assert rows["CLM-B"]["prior_claims_count"] == 1
    assert rows["CLM-B"]["days_since_prior_claim"] == 14


def test_reinstatement_window_is_inclusive_at_thirty_days_and_uses_entry_into_the_status():
    history = [version("P-10003", 1, D(500)), version("P-10003", 2, D(100), "lapsed"),
               version("P-10003", 3, D(80), "reinstated"), version("P-10003", 4, D(70), "reinstated")]
    claims = [claim("CLM-30", "P-10003", D(50), D(45)), claim("CLM-31", "P-10003", D(49), D(44)),
              claim("CLM-PRE", "P-10003", D(81), D(79))]
    rows = by_id(T.build_claim_context(claims, history, [], []))
    assert rows["CLM-30"]["reinstated_within_30d_before_loss"] is True     # exactly 30 days
    assert rows["CLM-31"]["reinstated_within_30d_before_loss"] is False    # 31 days
    assert rows["CLM-PRE"]["reinstated_within_30d_before_loss"] is False   # loss before it


def test_the_vehicle_a_policy_started_with_is_not_a_new_vehicle():
    history = [version("P-10004", 1, D(40))]
    vehicles = [{"vehicle_id": "VEH-1", "policy_id": "P-10004", "added_date": D(40)}]
    rows = by_id(T.build_claim_context([claim("CLM-1", "P-10004", D(20), D(15))], history, vehicles, []))
    assert rows["CLM-1"]["vehicle_added_within_30d_before_loss"] is False
    vehicles.append({"vehicle_id": "VEH-2", "policy_id": "P-10004", "added_date": D(20)})
    rows = by_id(T.build_claim_context([claim("CLM-1", "P-10004", D(20), D(15))], history, vehicles, []))
    assert rows["CLM-1"]["vehicle_added_within_30d_before_loss"] is True   # added on the loss date


def test_it_is_a_gold_table_keyed_on_the_claim():
    assert "claim_context" in T.SCHEMAS
    keys = T.GOLD_KEYS["claim_context"]
    assert keys.primary_key == ("claim_id",)
    assert [(fk.columns, fk.references_table) for fk in keys.foreign_keys] == [
        (("claim_id",), "claim_event"), (("policy_id",), "policy_profile")]


def test_build_all_returns_it(curated, claim_event):
    assert set(curated["claim_context"]["claim_id"]) == set(claim_event["claim_id"])
    assert curated["claim_context"]["note_text"].notna().all()
