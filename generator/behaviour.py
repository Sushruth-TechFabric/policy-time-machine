"""Behaviour facts of a claim, derived from the emitted source tables alone.

Nothing here reads generator internals: the same facts are derived again by the
pipeline (``transformations.build_claim_context``) from the same tables, and a
test holds the two derivations together.
"""

from __future__ import annotations

import pandas as pd

FLAGS: tuple[str, ...] = ("early_tenure", "recent_reinstatement", "new_vehicle")
EARLY_TENURE_DAYS = 90
RECENT_DAYS = 30


def _within(claim: pd.DataFrame, events: pd.DataFrame, column: str) -> pd.Series:
    """True where the policy has an event 0..RECENT_DAYS days before the loss."""
    if events.empty:
        return pd.Series(False, index=claim.index)
    joined = claim[["claim_id", "policy_id", "loss_date"]].merge(events, on="policy_id")
    days = (joined["loss_date"] - joined[column]).dt.days
    hits = set(joined.loc[(days >= 0) & (days <= RECENT_DAYS), "claim_id"])
    return claim["claim_id"].isin(hits)


def claim_flags(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    claim = frames["claim"][["claim_id", "policy_id", "loss_date"]].copy()
    claim["loss_date"] = pd.to_datetime(claim["loss_date"])

    history = frames["policy_history"].sort_values(["policy_id", "version_no"], kind="stable").copy()
    history["effective_from"] = pd.to_datetime(history["effective_from"])
    inception = history.groupby("policy_id")["effective_from"].min()

    claim["policy_age_at_loss_days"] = (
        claim["loss_date"] - claim["policy_id"].map(inception)
    ).dt.days.astype("int64")
    claim["early_tenure"] = claim["policy_age_at_loss_days"] <= EARLY_TENURE_DAYS

    previous = history.groupby("policy_id")["policy_status"].shift(1)
    entered = history.loc[
        (history["policy_status"] == "reinstated") & (previous != "reinstated"),
        ["policy_id", "effective_from"],
    ]
    claim["recent_reinstatement"] = _within(claim, entered, "effective_from")

    vehicle = frames["vehicle"][["policy_id", "added_date"]].copy()
    vehicle["added_date"] = pd.to_datetime(vehicle["added_date"])
    vehicle = vehicle[vehicle["added_date"] > vehicle["policy_id"].map(inception)]
    claim["new_vehicle"] = _within(claim, vehicle, "added_date")

    return claim[["claim_id", "policy_age_at_loss_days", *FLAGS]].reset_index(drop=True)
