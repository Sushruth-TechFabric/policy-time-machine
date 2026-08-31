"""Post-generation validation (spec 08 section 2).

Runs in CI and in the regeneration Workflow, after generation and before the
pipeline. It answers one question: **is the signal the one we declared?**

Everything below is re-derived from the emitted parquet files rather than from
the generator's internal state. Material changes are reconstructed by diffing
adjacent SCD Type 2 versions, exactly as the declarative pipeline will, so a
generator that computed the right effect internally but emitted history that
does not express it still fails here.

    python -m generator.validate --out data/raw

Exit status is non-zero on any failure.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import constants as K
from .ids import assert_lexical_reservation
from .emit import DATE_COLUMNS, POLICY_COLUMNS, TABLE_ORDER

DAYS_PER_YEAR = 365.0
TERMINAL_STATUSES = ("cancelled", "non_renewed")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


class Report:
    def __init__(self) -> None:
        self.checks: list[Check] = []

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(Check(name, bool(passed), detail))

    @property
    def ok(self) -> bool:
        return all(check.passed for check in self.checks)

    def render(self) -> str:
        width = max(len(c.name) for c in self.checks)
        lines = []
        for check in self.checks:
            mark = "PASS" if check.passed else "FAIL"
            lines.append(f"  [{mark}] {check.name:<{width}}  {check.detail}")
        failed = sum(1 for c in self.checks if not c.passed)
        lines.append("")
        lines.append(
            f"  {len(self.checks) - failed}/{len(self.checks)} checks passed"
            + ("" if failed == 0 else f" - {failed} FAILED")
        )
        return "\n".join(lines)


# ---------------------------------------------------------------- loading
def load(out_dir: Path) -> dict[str, pd.DataFrame]:
    frames = {}
    for table in TABLE_ORDER:
        path = out_dir / f"{table}.parquet"
        if not path.exists():
            raise SystemExit(f"missing expected table: {path}")
        frame = pd.read_parquet(path)
        # Parquet date32 reads back as python dates; make them datetimelike so
        # date arithmetic below is ordinary pandas rather than object juggling.
        for column in DATE_COLUMNS[table]:
            frame[column] = pd.to_datetime(frame[column], errors="coerce").astype("datetime64[s]")
        frames[table] = frame
    return frames


def anchor_of(frames: dict[str, pd.DataFrame]) -> pd.Timestamp:
    return pd.Timestamp(frames["generation_manifest"]["anchor_date"].iloc[0])


# ------------------------------------------------- material change derivation
def derive_material_changes(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Reconstruct material changes by diffing adjacent SCD2 versions.

    The five material categories of spec 01 section 6. Premium and agent moves
    are visible in the same history and deliberately not reconstructed here:
    they are derived changes and never material (ADR-0003).
    """
    history = frames["policy_history"].sort_values(["policy_id", "version_no"], kind="stable")
    group = history.groupby("policy_id", sort=False)
    records = []

    address_moved = (
        history["garaging_postal_code"].ne(group["garaging_postal_code"].shift(1))
        | history["garaging_city"].ne(group["garaging_city"].shift(1))
    ) & group["garaging_city"].shift(1).notna()
    vehicle_moved = history["primary_vehicle_id"].ne(group["primary_vehicle_id"].shift(1)) & group[
        "primary_vehicle_id"
    ].shift(1).notna()
    status_moved = history["policy_status"].ne(group["policy_status"].shift(1)) & group[
        "policy_status"
    ].shift(1).notna()

    for category, mask in (
        ("address", address_moved),
        ("vehicle", vehicle_moved),
        ("status", status_moved),
    ):
        subset = history.loc[mask, ["policy_id", "effective_from"]].copy()
        subset["change_category"] = category
        subset["coverage_line"] = None
        subset["direction"] = "switch"
        records.append(subset)

    coverage = frames["policy_coverage_history"].sort_values(
        ["policy_id", "coverage_line", "version_no"], kind="stable"
    )
    cgroup = coverage.groupby(["policy_id", "coverage_line"], sort=False)
    previous_limit = cgroup["limit_amount"].shift(1)
    previous_deductible = cgroup["deductible_amount"].shift(1)

    limit_moved = coverage["limit_amount"].ne(previous_limit) & previous_limit.notna()
    subset = coverage.loc[limit_moved, ["policy_id", "coverage_line", "effective_from"]].copy()
    subset["change_category"] = "coverage"
    subset["direction"] = np.where(
        coverage.loc[limit_moved, "limit_amount"].to_numpy()
        > previous_limit[limit_moved].to_numpy(),
        "increase",
        "decrease",
    )
    records.append(subset)

    deductible_moved = (
        coverage["deductible_amount"].ne(previous_deductible) & previous_deductible.notna()
    )
    subset = coverage.loc[deductible_moved, ["policy_id", "coverage_line", "effective_from"]].copy()
    subset["change_category"] = "deductible"
    subset["direction"] = np.where(
        coverage.loc[deductible_moved, "deductible_amount"].to_numpy()
        > previous_deductible[deductible_moved].to_numpy(),
        "increase",
        "decrease",
    )
    records.append(subset)

    changes = pd.concat(records, ignore_index=True)
    changes = changes.rename(columns={"effective_from": "change_date"})
    return changes


def policy_exposure(frames: dict[str, pd.DataFrame], anchor: pd.Timestamp) -> pd.DataFrame:
    """Start and end of each policy's time on the books.

    A policy that ends the window `cancelled` or `non_renewed` stops accruing
    exposure on the day it leaves; everything else runs to the anchor.
    """
    history = frames["policy_history"]
    start = history.groupby("policy_id")["effective_from"].min()
    current = history.loc[history["is_current"], ["policy_id", "policy_status", "effective_from"]]
    current = current.set_index("policy_id")
    end = pd.Series(anchor, index=start.index)
    terminal = current["policy_status"].isin(TERMINAL_STATUSES)
    end.loc[current.index[terminal]] = current.loc[terminal, "effective_from"]
    return pd.DataFrame({"start": start, "end": end.reindex(start.index)})


# ------------------------------------------------------------- exposure maths
class ExposureGrid:
    """Flat policy-day grid, the denominator for every rate in this module."""

    def __init__(self, exposure: pd.DataFrame, anchor: pd.Timestamp):
        self.policy_ids = exposure.index.to_numpy()
        self.index = {pid: i for i, pid in enumerate(self.policy_ids)}
        epoch = anchor.to_numpy().astype("datetime64[D]").astype(np.int64)
        self.anchor_day = int(epoch)
        self.start = exposure["start"].to_numpy().astype("datetime64[D]").astype(np.int64)
        self.end = exposure["end"].to_numpy().astype("datetime64[D]").astype(np.int64)
        lengths = self.end - self.start + 1
        self.lengths = lengths
        self.offset = np.concatenate(([0], np.cumsum(lengths)[:-1]))
        self.total = int(lengths.sum())

    def locate(self, policy_ids: pd.Series, dates: pd.Series) -> np.ndarray:
        p = np.array([self.index.get(pid, -1) for pid in policy_ids], dtype=np.int64)
        d = dates.to_numpy().astype("datetime64[D]").astype(np.int64)
        valid = (p >= 0) & (d >= self.start[p]) & (d <= self.end[p])
        flat = np.full(p.shape, -1, dtype=np.int64)
        flat[valid] = self.offset[p[valid]] + (d[valid] - self.start[p[valid]])
        return flat

    def window(self, policy_ids: pd.Series, dates: pd.Series, days: int) -> np.ndarray:
        """Boolean per policy-day: is this day within `days` after such an event?"""
        p = np.array([self.index.get(pid, -1) for pid in policy_ids], dtype=np.int64)
        d = dates.to_numpy().astype("datetime64[D]").astype(np.int64)
        keep = (p >= 0) & (d >= self.start[p]) & (d <= self.end[p])
        p, d = p[keep], d[keep]
        diff = np.zeros(self.total + 1, dtype=np.int32)
        if p.size:
            a = self.offset[p] + (d - self.start[p])
            b = self.offset[p] + (np.minimum(d + days - 1, self.end[p]) - self.start[p]) + 1
            np.add.at(diff, a, 1)
            np.add.at(diff, b, -1)
        return np.cumsum(diff[:-1]) > 0


def rate(claim_flags: np.ndarray, mask: np.ndarray) -> tuple[float, int, float]:
    claims = int(claim_flags[mask].sum())
    years = float(mask.sum()) / DAYS_PER_YEAR
    return (claims / years if years else float("nan")), claims, years


# --------------------------------------------------------------------- checks
def run(out_dir: Path) -> tuple[Report, dict]:
    frames = load(out_dir)
    anchor = anchor_of(frames)
    report = Report()
    measurements: dict = {}

    # --- lexical reservation -------------------------------------------------
    try:
        assert_lexical_reservation(frames, POLICY_COLUMNS)
        report.add("identifier lexical reservation", True, r"no non-policy id matches \bP-\d{5}\b")
    except AssertionError as error:
        report.add("identifier lexical reservation", False, str(error).replace("\n", " | "))

    changes = derive_material_changes(frames)
    exposure = policy_exposure(frames, anchor)
    grid = ExposureGrid(exposure, anchor)
    claim = frames["claim"]

    claim_flat = grid.locate(claim["policy_id"], claim["loss_date"])
    claim_counts = np.zeros(grid.total, dtype=np.int32)
    inside = claim_flat >= 0
    np.add.at(claim_counts, claim_flat[inside], 1)
    measurements["claims_outside_exposure"] = int((~inside).sum())
    report.add(
        "every claim falls inside its policy's exposure",
        int((~inside).sum()) == 0,
        f"{int((~inside).sum())} outside",
    )

    material = changes[changes["change_category"].isin(K.MATERIAL_CATEGORIES)].copy()
    material["exposure_key"] = [
        K.exposure_key(category, direction)
        for category, direction in zip(material["change_category"], material["direction"])
    ]
    recent90 = grid.window(material["policy_id"], material["change_date"], K.HEADLINE_WINDOW_DAYS)
    within60 = {
        category: grid.window(
            material.loc[material["change_category"] == category, "policy_id"],
            material.loc[material["change_category"] == category, "change_date"],
            K.CATEGORY_WINDOW_DAYS,
        )
        for category in K.MATERIAL_CATEGORIES
    }
    within60_key = {
        key: grid.window(
            material.loc[material["exposure_key"] == key, "policy_id"],
            material.loc[material["exposure_key"] == key, "change_date"],
            K.CATEGORY_WINDOW_DAYS,
        )
        for key in K.EXPOSURE_KEYS
    }

    # --- headline comparison (spec 01 section 8) -----------------------------
    exposed_rate, exposed_n, exposed_years = rate(claim_counts, recent90)
    baseline_rate, baseline_n, baseline_years = rate(claim_counts, ~recent90)
    measurements["headline"] = {
        "recent_material_change": {"rate": exposed_rate, "claims": exposed_n, "policy_years": exposed_years},
        "no_recent_material_change": {"rate": baseline_rate, "claims": baseline_n, "policy_years": baseline_years},
    }
    for label, measured, declared in (
        ("recent material change", exposed_rate, K.RATE_RECENT_MATERIAL_CHANGE),
        ("no recent material change", baseline_rate, K.RATE_NO_RECENT_MATERIAL_CHANGE),
    ):
        relative = measured / declared - 1.0
        report.add(
            f"annual claim frequency, {label}",
            abs(relative) <= K.EFFECT_TOLERANCE,
            f"measured {measured:.4%} vs declared {declared:.2%} ({relative:+.1%} relative)",
        )

    overall_rate, overall_n, overall_years = rate(claim_counts, np.ones(grid.total, dtype=bool))
    measurements["baseline_annual_claim_frequency"] = overall_rate
    relative = overall_rate / K.BASELINE_ANNUAL_CLAIM_FREQUENCY - 1.0
    report.add(
        "portfolio annual claim frequency",
        abs(relative) <= K.EFFECT_TOLERANCE,
        f"measured {overall_rate:.4%} vs declared {K.BASELINE_ANNUAL_CLAIM_FREQUENCY:.2%} "
        f"({relative:+.1%} relative), {overall_n:,} claims over {overall_years:,.0f} policy-years",
    )

    # --- category lifts and the ranking --------------------------------------
    reference_mask = ~np.any(list(within60.values()), axis=0)
    reference_rate, reference_n, reference_years = rate(claim_counts, reference_mask)
    measurements["category_reference"] = {
        "rate": reference_rate,
        "claims": reference_n,
        "policy_years": reference_years,
    }
    lifts: dict[str, float] = {}
    for category in K.MATERIAL_CATEGORIES:
        category_rate, n, years = rate(claim_counts, within60[category])
        lift = category_rate / reference_rate
        lifts[category] = lift
        declared = K.CATEGORY_LIFTS[category]
        relative = lift / declared - 1.0
        report.add(
            f"category lift, {category}",
            abs(relative) <= K.EFFECT_TOLERANCE,
            f"measured {lift:.3f}x vs declared {declared:.2f}x ({relative:+.1%} relative), "
            f"n={n} claims / {years:,.0f} policy-years",
        )
    measurements["category_lifts"] = lifts

    measured_ranking = tuple(sorted(lifts, key=lambda c: -lifts[c]))
    measurements["category_ranking"] = measured_ranking
    report.add(
        "category ranking matches the declared ordering",
        measured_ranking == K.CATEGORY_RANKING,
        f"measured {' > '.join(measured_ranking)}",
    )

    # --- the two direction-named rows of the section 8 table -----------------
    key_lifts: dict[str, float] = {}
    for key in K.EXPOSURE_KEYS:
        key_rate, n, years = rate(claim_counts, within60_key[key])
        key_lifts[key] = key_rate / reference_rate
        if key not in ("coverage_increase", "deductible_decrease"):
            continue
        declared = K.EXPOSURE_KEY_LIFTS[key]
        relative = key_lifts[key] / declared - 1.0
        report.add(
            f"declared lift, {key.replace('_', ' ')}",
            abs(relative) <= K.EFFECT_TOLERANCE,
            f"measured {key_lifts[key]:.3f}x vs declared {declared:.2f}x "
            f"({relative:+.1%} relative), n={n} claims",
        )
    measurements["exposure_key_lifts"] = key_lifts

    # --- severity bands (ADR-0008) -------------------------------------------
    bands = pd.cut(
        claim["settled_amount"],
        bins=[b[1] for b in K.SEVERITY_BANDS] + [np.inf],
        labels=[b[0] for b in K.SEVERITY_BANDS],
        right=False,
    )
    band_counts = bands.value_counts().reindex([b[0] for b in K.SEVERITY_BANDS]).fillna(0).astype(int)
    measurements["severity_bands"] = band_counts.to_dict()
    report.add(
        "every severity band is populated",
        bool((band_counts > 0).all()),
        ", ".join(f"{band}={count:,}" for band, count in band_counts.items()),
    )

    # --- limit utilisation above 100% ----------------------------------------
    utilisation = limit_utilisation(frames, claim)
    over = int((utilisation > 100).sum())
    measurements["limit_utilisation_over_100"] = over
    measurements["limit_utilisation_at_or_near_limit"] = int((utilisation >= 90).sum())
    report.add(
        "limit utilisation above 100% occurs and is never clamped",
        over > 0,
        f"{over:,} claims above 100%, {int((utilisation >= 90).sum()):,} at or near limit, "
        f"max {np.nanmax(utilisation):.0f}%",
    )

    # --- loss-to-report lag (spec 01 section 5.5) ----------------------------
    lag = (claim["report_date"] - claim["loss_date"]).dt.days
    measurements["report_lag"] = {
        "median": float(lag.median()),
        "p90": float(lag.quantile(0.90)),
        "min": int(lag.min()),
        "max": int(lag.max()),
    }
    report.add(
        "loss-to-report lag distribution",
        bool(lag.min() >= K.REPORT_LAG_MIN_DAYS)
        and bool(lag.max() <= K.REPORT_LAG_CAP_DAYS)
        and 3.0 <= lag.median() <= 5.0
        and 16.0 <= lag.quantile(0.90) <= 26.0,
        f"median {lag.median():.0f}d (declared {K.REPORT_LAG_MEDIAN_DAYS:.0f}d), "
        f"p90 {lag.quantile(0.90):.0f}d (declared {K.REPORT_LAG_P90_DAYS:.0f}d), "
        f"range {lag.min()}-{lag.max()}d",
    )

    # --- scenario populations (spec 01 section 9) ----------------------------
    assignment = frames["scenario_assignment"]
    sizes = assignment["scenario_id"].value_counts().to_dict()
    measurements["scenario_sizes"] = sizes
    wrong = {
        scenario: (sizes.get(scenario, 0), declared)
        for scenario, declared in K.SCENARIO_SIZES.items()
        if sizes.get(scenario, 0) != declared
    }
    report.add(
        "scenario populations exist at their declared sizes",
        not wrong,
        "all 11 populations correct" if not wrong else f"wrong: {wrong}",
    )

    known_policies = set(frames["policy_history"]["policy_id"])
    unknown = set(assignment["policy_id"]) - known_policies
    report.add(
        "every scenario policy exists in policy_history",
        not unknown,
        f"{len(unknown)} unknown" if unknown else "",
    )

    report_extra = check_scenario_shapes(frames, changes, anchor, measurements)
    for name, passed, detail in report_extra:
        report.add(name, passed, detail)

    # --- guaranteed activity tail (spec 01 section 5.4) ----------------------
    tail_ok, tail_detail = activity_tail(material, claim, anchor)
    measurements["activity_tail"] = tail_detail
    report.add(
        f"guaranteed activity tail through anchor-{K.ACTIVITY_TAIL_DAYS}d",
        tail_ok,
        tail_detail,
    )

    # --- volumes -------------------------------------------------------------
    measurements["row_counts"] = {table: len(frame) for table, frame in frames.items()}
    measurements["material_change_count"] = len(material)

    return report, measurements


def limit_utilisation(frames: dict[str, pd.DataFrame], claim: pd.DataFrame) -> np.ndarray:
    """Settled amount over the limit in force on that line at the loss date."""
    coverage = frames["policy_coverage_history"]
    merged = claim.merge(
        coverage[["policy_id", "coverage_line", "effective_from", "effective_to", "limit_amount"]],
        on=["policy_id", "coverage_line"],
        how="left",
    )
    in_force = (merged["effective_from"] <= merged["loss_date"]) & (
        merged["loss_date"] < merged["effective_to"]
    )
    merged = merged.loc[in_force]
    limits = merged.groupby("claim_id")["limit_amount"].first()
    amounts = claim.set_index("claim_id")["settled_amount"]
    joined = amounts.to_frame("amount").join(limits.to_frame("limit"))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(
            joined["limit"].to_numpy() > 0,
            100.0 * joined["amount"].to_numpy() / joined["limit"].to_numpy(),
            np.nan,
        )


def check_scenario_shapes(frames, changes, anchor, measurements) -> list[tuple[str, bool, str]]:
    """The planted stories are where they were declared to be."""
    assignment = frames["scenario_assignment"]
    claim = frames["claim"]
    results: list[tuple[str, bool, str]] = []
    members = {
        scenario: set(group["policy_id"])
        for scenario, group in assignment.groupby("scenario_id")
    }

    def offset(dates) -> pd.Series:
        return (anchor - dates).dt.days

    s1 = claim[claim["policy_id"].isin(members["S1"]) & (offset(claim["loss_date"]) == K.S1_LOSS_OFFSET)]
    results.append(
        (
            "S1 collision claims at the declared offset",
            len(s1) == K.SCENARIO_SIZES["S1"] and (s1["coverage_line"] == "COLL").all(),
            f"{len(s1)}/{K.SCENARIO_SIZES['S1']} at anchor-{K.S1_LOSS_OFFSET}d",
        )
    )

    coverage_raises = changes[
        (changes["change_category"] == "coverage")
        & (changes["direction"] == "increase")
        & (changes["coverage_line"] == "COLL")
        & (offset(changes["change_date"]) == K.S1_COVERAGE_RAISE_OFFSET)
        & changes["policy_id"].isin(members["S1"])
    ]
    results.append(
        (
            "S1 COLL limit increases at the declared offset",
            len(coverage_raises) == K.SCENARIO_SIZES["S1"],
            f"{len(coverage_raises)}/{K.SCENARIO_SIZES['S1']} at anchor-{K.S1_COVERAGE_RAISE_OFFSET}d",
        )
    )

    s2 = changes[
        (changes["change_category"] == "deductible")
        & (changes["direction"] == "decrease")
        & (changes["coverage_line"] == "COMP")
        & (offset(changes["change_date"]) == K.S2_DEDUCTIBLE_CUT_OFFSET)
        & changes["policy_id"].isin(members["S2"])
    ]
    results.append(
        (
            "S2 COMP deductible decreases at the declared offset",
            len(s2) == K.SCENARIO_SIZES["S2"],
            f"{len(s2)}/{K.SCENARIO_SIZES['S2']} at anchor-{K.S2_DEDUCTIBLE_CUT_OFFSET}d",
        )
    )

    s3_claims = claim[claim["policy_id"].isin(members["S3"])]
    s3_claims = s3_claims[offset(s3_claims["loss_date"]) == K.S3_LOSS_OFFSET]
    s3_changes = changes[
        changes["policy_id"].isin(members["S3"])
        & (changes["change_category"] == "address")
        & (offset(changes["change_date"]) == K.S3_ADDRESS_CHANGE_OFFSET)
    ]
    in_gap = (
        len(s3_claims) == K.SCENARIO_SIZES["S3"]
        and (offset(s3_claims["report_date"]) == K.S3_REPORT_OFFSET).all()
        and len(s3_changes) == K.SCENARIO_SIZES["S3"]
    )
    results.append(
        (
            "S3 changes fall inside the loss-to-report gap",
            in_gap,
            f"{len(s3_changes)} address changes at anchor-{K.S3_ADDRESS_CHANGE_OFFSET}d, "
            f"losses at anchor-{K.S3_LOSS_OFFSET}d reported anchor-{K.S3_REPORT_OFFSET}d",
        )
    )

    s4_changes = changes[
        changes["policy_id"].isin(members["S4"])
        & offset(changes["change_date"]).isin(K.S4_CLUSTER_OFFSETS)
    ]
    s4_claims = claim[claim["policy_id"].isin(members["S4"])]
    s4_claims = s4_claims[offset(s4_claims["loss_date"]) == K.S4_LOSS_OFFSET]
    high_severity = (s4_claims["settled_amount"] >= 10_000).all()
    results.append(
        (
            "S4 clusters carry four changes before a high-severity claim",
            len(s4_changes) == 4 * K.SCENARIO_SIZES["S4"]
            and len(s4_claims) == K.SCENARIO_SIZES["S4"]
            and bool(high_severity),
            f"{len(s4_changes)} changes, {len(s4_claims)} claims, all high-severity={bool(high_severity)}",
        )
    )

    s5 = changes[changes["policy_id"].isin(members["S5"])]
    vehicle = s5[(s5["change_category"] == "vehicle") & (offset(s5["change_date"]) == K.S5_VEHICLE_OFFSET)]
    address = s5[(s5["change_category"] == "address") & (offset(s5["change_date"]) == K.S5_ADDRESS_OFFSET)]
    results.append(
        (
            "S5 vehicle and address changes within 60 days",
            len(vehicle) == K.SCENARIO_SIZES["S5"] and len(address) == K.SCENARIO_SIZES["S5"],
            f"{len(vehicle)} vehicle at anchor-{K.S5_VEHICLE_OFFSET}d, "
            f"{len(address)} address at anchor-{K.S5_ADDRESS_OFFSET}d, "
            f"{K.S5_VEHICLE_OFFSET - K.S5_ADDRESS_OFFSET}d apart",
        )
    )

    s6_claims = claim[claim["policy_id"].isin(members["S6"])]
    s6_claims = s6_claims[offset(s6_claims["loss_date"]) == K.S6_LOSS_OFFSET]
    s6_util = limit_utilisation(frames, s6_claims)
    moderate = s6_claims["settled_amount"].between(2_500, 9_999.99).all()
    results.append(
        (
            "S6 claims are moderate band at near-limit utilisation",
            len(s6_claims) == K.SCENARIO_SIZES["S6"]
            and bool(moderate)
            and bool(np.nanmin(s6_util) >= 90),
            f"{len(s6_claims)} claims, utilisation {np.nanmin(s6_util):.0f}-{np.nanmax(s6_util):.0f}%",
        )
    )

    # C1/C2/C4 are the populations the query contracts require to be excluded.
    c1_policies = members["C1"]
    c1_claims = claim[claim["policy_id"].isin(c1_policies)]
    c1_changes = changes[changes["policy_id"].isin(c1_policies)]
    quiet = True
    for _, row in c1_claims.iterrows():
        prior = c1_changes[
            (c1_changes["policy_id"] == row["policy_id"])
            & (c1_changes["change_date"] <= row["loss_date"])
            & (c1_changes["change_date"] > row["loss_date"] - pd.Timedelta(days=K.HEADLINE_WINDOW_DAYS))
        ]
        if len(prior):
            quiet = False
            break
    results.append(
        (
            "C1 claims have no material change in the prior 90 days",
            quiet and len(c1_claims) >= K.SCENARIO_SIZES["C1"],
            f"{len(c1_claims)} high-value claims, none preceded by a material change",
        )
    )

    c2_claims = claim[claim["policy_id"].isin(members["C2"])]
    c2_changes = changes[changes["policy_id"].isin(members["C2"])]
    per_policy = len(c2_changes) / max(len(members["C2"]), 1)
    results.append(
        (
            "C2 policies change often and never claim",
            len(c2_claims) == 0 and per_policy >= 3,
            f"{len(c2_claims)} claims, {per_policy:.1f} material changes per policy",
        )
    )

    c4_claims = claim[claim["policy_id"].isin(members["C4"])]
    c4_util = limit_utilisation(frames, c4_claims)
    results.append(
        (
            "C4 near-limit claims have nothing before them",
            len(c4_claims) == K.SCENARIO_SIZES["C4"] and bool(np.nanmin(c4_util) >= 90),
            f"{len(c4_claims)} claims, utilisation {np.nanmin(c4_util):.0f}-{np.nanmax(c4_util):.0f}%",
        )
    )

    # Demo anchor policy: address, coverage increase, vehicle, claim - in that
    # order, all inside the 60 days before the loss (spec 01 section 9).
    demo_id = frames["generation_manifest"]["demo_policy_id"].iloc[0]
    demo_claims = claim[claim["policy_id"] == demo_id]
    demo_changes = changes[changes["policy_id"] == demo_id].sort_values("change_date")
    measurements["demo_policy_id"] = demo_id
    ok = False
    detail = "no collision claim found"
    if len(demo_claims):
        loss = demo_claims["loss_date"].max()
        window = demo_changes[
            (demo_changes["change_date"] > loss - pd.Timedelta(days=60))
            & (demo_changes["change_date"] <= loss)
        ]
        sequence = list(window["change_category"])
        expected = ["address", "coverage", "vehicle"]
        ok = sequence == expected and (window["direction"].iloc[1] == "increase")
        detail = f"{demo_id}: {' -> '.join(sequence)} -> collision claim"
    results.append(("demo anchor policy timeline", ok, detail))

    return results


def activity_tail(material: pd.DataFrame, claim: pd.DataFrame, anchor: pd.Timestamp) -> tuple[bool, str]:
    """Material changes and claims present throughout the staleness budget."""
    bucket = K.ACTIVITY_TAIL_BUCKET_DAYS
    empty: list[str] = []
    counts = []
    for start in range(0, K.ACTIVITY_TAIL_DAYS, bucket):
        lo = anchor - pd.Timedelta(days=start + bucket)
        hi = anchor - pd.Timedelta(days=start)
        n_changes = int(
            ((material["change_date"] > lo) & (material["change_date"] <= hi)).sum()
        )
        n_claims = int(((claim["loss_date"] > lo) & (claim["loss_date"] <= hi)).sum())
        counts.append((start, n_changes, n_claims))
        if n_changes == 0 or n_claims == 0:
            empty.append(f"anchor-{start + bucket}d..anchor-{start}d")
    total_changes = sum(c for _, c, _ in counts)
    total_claims = sum(c for _, _, c in counts)
    detail = (
        f"{total_changes:,} material changes and {total_claims:,} claims in the last "
        f"{K.ACTIVITY_TAIL_DAYS} days; every {bucket}-day bucket populated"
    )
    if empty:
        detail = f"empty buckets: {', '.join(empty)}"
    return not empty, detail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m generator.validate", description=__doc__)
    parser.add_argument("--out", required=True, help="directory holding the generated parquet files")
    args = parser.parse_args(argv)

    report, measurements = run(Path(args.out))
    print("Generator validation - measured against declared design parameters")
    print()
    print(report.render())
    print()
    print("  Declared vs measured summary")
    headline = measurements["headline"]
    print(
        f"    recent material change     {headline['recent_material_change']['rate']:.4%} "
        f"(declared {K.RATE_RECENT_MATERIAL_CHANGE:.2%})  "
        f"n={headline['recent_material_change']['claims']:,} claims / "
        f"{headline['recent_material_change']['policy_years']:,.0f} policy-years"
    )
    print(
        f"    no recent material change  {headline['no_recent_material_change']['rate']:.4%} "
        f"(declared {K.RATE_NO_RECENT_MATERIAL_CHANGE:.2%})  "
        f"n={headline['no_recent_material_change']['claims']:,} claims / "
        f"{headline['no_recent_material_change']['policy_years']:,.0f} policy-years"
    )
    for category in K.CATEGORY_RANKING:
        print(
            f"    lift {category:<12} {measurements['category_lifts'][category]:.3f}x "
            f"(declared {K.CATEGORY_LIFTS[category]:.2f}x)"
        )
    for key in ("coverage_increase", "deductible_decrease"):
        print(
            f"    lift {key:<20} {measurements['exposure_key_lifts'][key]:.3f}x "
            f"(declared {K.EXPOSURE_KEY_LIFTS[key]:.2f}x)"
        )
    print(f"    portfolio frequency        {measurements['baseline_annual_claim_frequency']:.4%}")
    print(f"    severity bands             {measurements['severity_bands']}")
    print(f"    row counts                 {measurements['row_counts']}")
    print(f"    material changes derived   {measurements['material_change_count']:,}")
    print()
    if not report.ok:
        print("VALIDATION FAILED")
        return 1
    print("VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
