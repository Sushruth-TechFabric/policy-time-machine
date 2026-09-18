import datetime as dt

import pandas as pd

from generator.behaviour import FLAGS, claim_flags

DAY0 = dt.date(2025, 1, 1)


def d(offset: int) -> pd.Timestamp:
    return pd.Timestamp(DAY0 + dt.timedelta(days=offset))


def frames(claims, history, vehicles):
    return {
        "claim": pd.DataFrame(claims, columns=["claim_id", "policy_id", "loss_date"]),
        "policy_history": pd.DataFrame(
            history, columns=["policy_id", "version_no", "effective_from", "policy_status"]),
        "vehicle": pd.DataFrame(vehicles, columns=["policy_id", "added_date"]),
    }


def test_flags_are_the_declared_three():
    assert FLAGS == ("early_tenure", "recent_reinstatement", "new_vehicle")


def test_early_tenure_is_inclusive_at_ninety_days():
    f = frames(
        [("A", "P1", d(90)), ("B", "P1", d(91))],
        [("P1", 1, d(0), "active")],
        [("P1", d(0))],
    )
    out = claim_flags(f).set_index("claim_id")
    assert out.loc["A", "policy_age_at_loss_days"] == 90
    assert bool(out.loc["A", "early_tenure"]) and not bool(out.loc["B", "early_tenure"])


def test_reinstatement_counts_entry_into_the_status_within_thirty_days():
    history = [
        ("P1", 1, d(0), "active"), ("P1", 2, d(200), "lapsed"),
        ("P1", 3, d(220), "reinstated"), ("P1", 4, d(230), "reinstated"),
    ]
    f = frames([("A", "P1", d(250)), ("B", "P1", d(251)), ("C", "P1", d(219))],
               history, [("P1", d(0))])
    out = claim_flags(f).set_index("claim_id")["recent_reinstatement"]
    # Entry into the status is d(220); a later version still 'reinstated' is not a new entry.
    assert bool(out["A"]) and not bool(out["B"]) and not bool(out["C"])


def test_new_vehicle_ignores_the_vehicle_the_policy_started_with():
    f = frames([("A", "P1", d(20)), ("B", "P2", d(130))],
               [("P1", 1, d(0), "active"), ("P2", 1, d(0), "active")],
               [("P1", d(0)), ("P2", d(0)), ("P2", d(100))])
    out = claim_flags(f).set_index("claim_id")["new_vehicle"]
    assert not bool(out["A"]) and bool(out["B"])


def test_rows_follow_the_claim_frame_order():
    f = frames([("B", "P1", d(10)), ("A", "P1", d(20))], [("P1", 1, d(0), "active")], [])
    assert list(claim_flags(f)["claim_id"]) == ["B", "A"]
