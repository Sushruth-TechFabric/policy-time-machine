"""Design parameters for the Policy Time Machine synthetic dataset.

Every number here is a declared design parameter traceable to
``docs/specs/01-data-model-and-synthetic-data.md``. Nothing in this module is an
observation; the whole point of declaring them is that CI can check the
generated data against them (ADR-0014).

No absolute date literal appears anywhere in this package except
:data:`FAR_FUTURE`, which is an *attribute* date (the SCD2 open-ended
``effective_to`` sentinel), explicitly permitted by spec 01 section 3.
"""

from __future__ import annotations

import datetime as _dt

# --- SCD2 open-ended marker -------------------------------------------------
# Attribute date, not an event timestamp. Spec 01 section 3 mandates this exact
# value for the current version of every SCD Type 2 row.
FAR_FUTURE = _dt.date(9999, 12, 31)  # noqa: DTZ001 - permitted attribute sentinel

# --- Coverage lines (spec 01 section 1, ADR-0005) ---------------------------
COVERAGE_LINES = ("BI", "PD", "COLL", "COMP", "UMUIM")
DEDUCTIBLE_LINES = ("COLL", "COMP")

# --- Material change categories (spec 01 section 6, ADR-0003) ---------------
MATERIAL_CATEGORIES = ("coverage", "deductible", "vehicle", "address", "status")
DERIVED_CATEGORIES = ("premium", "agent")

# --- Identifier formats (spec 01 section 2) ---------------------------------
ID_FORMATS = {
    "policy": ("P-", 5),
    "customer": ("C-", 6),
    "claim": ("CLM-", 6),
    "vehicle": ("VEH-", 6),
    "agent": ("AGT-", 4),
    "endorsement": ("END-", 8),
    "change_event": ("CHG-", 8),
    # `payment_id` carries no declared format in spec 01 section 2. `PMT-` plus
    # eight digits follows the house style and satisfies the lexical
    # reservation; flagged as a specification gap rather than a decision.
    "payment": ("PMT-", 8),
}
POLICY_REFERENCE_PATTERN = r"\bP-\d{5}\b"

# --- Volumes (spec 01 section 4) --------------------------------------------
HISTORY_DAYS = 1095  # three years before the anchor
N_CUSTOMERS = 6_500
N_POLICIES = 8_000
N_AGENTS = 80

# Fraction of policies whose inception sits at the very start of the window.
FULL_WINDOW_SHARE = 0.55
MIN_START_OFFSET_DAYS = 180  # youngest policy at generation time

# --- Claim frequency and effect sizes (spec 01 sections 7-8, ADR-0014) ------
BASELINE_ANNUAL_CLAIM_FREQUENCY = 0.060

HEADLINE_WINDOW_DAYS = 90
RATE_RECENT_MATERIAL_CHANGE = 0.085
RATE_NO_RECENT_MATERIAL_CHANGE = 0.058

CATEGORY_WINDOW_DAYS = 60
CATEGORY_LIFTS = {
    "coverage": 1.80,
    "deductible": 1.50,
    "vehicle": 1.25,
    "status": 1.15,
    "address": 1.05,
}
# The ordering is the specification; magnitudes are secondary (spec 01 section 8).
CATEGORY_RANKING = ("coverage", "deductible", "vehicle", "status", "address")

# The section 8 table names its first two rows by direction - "Coverage
# increase", "Deductible decrease" - while the ranking questions (QC-05, QC-06)
# rank by category. Both readings hold only if each direction of a category
# carries that category's declared lift, so exposure is tracked per
# (category, direction) and every scenario's directional skew is calibrated out
# rather than left to land wherever the planted claims put it.
EXPOSURE_KEYS = {
    "coverage_increase": ("coverage", "increase"),
    "coverage_decrease": ("coverage", "decrease"),
    "deductible_decrease": ("deductible", "decrease"),
    "deductible_increase": ("deductible", "increase"),
    "vehicle": ("vehicle", None),
    "address": ("address", None),
    "status": ("status", None),
}


def exposure_key(category: str, direction: str | None) -> str:
    """The exposure key a change contributes to."""
    if category in ("coverage", "deductible"):
        return f"{category}_{direction}"
    return category

EXPOSURE_KEY_LIFTS = {
    key: CATEGORY_LIFTS[category] for key, (category, _) in EXPOSURE_KEYS.items()
}

EFFECT_TOLERANCE = 0.15  # +/- 15% relative (spec 08 section 2)

# --- Change emission mix ----------------------------------------------------
# Weights over the four categories that arrive through ordinary endorsements.
# `status` is deliberately excluded: lapse/reinstate sequences are constructed
# populations, never random noise (spec 01 section 6 rule 3, ADR-0003).
ENDORSEMENT_CATEGORY_WEIGHTS = {
    "coverage": 0.40,
    "deductible": 0.24,
    "address": 0.28,
    "vehicle": 0.08,
}
# Endorsements per policy-year, before per-policy heterogeneity.
ENDORSEMENT_RATE_PER_YEAR = 1.62
ENDORSEMENT_PROPENSITY_SHAPE = 2.0  # gamma shape; mean fixed at 1.0
# Share of endorsements carrying a second material change of another category.
MULTI_CHANGE_ENDORSEMENT_SHARE = 0.15

# Direction mix. Every planted scenario that moves coverage moves it up, and
# every planted scenario that moves a deductible moves it down, so if the
# ordinary population were direction-balanced the planted claims would land
# entirely on one side and "coverage increase" would measure well above the
# declared category lift. Keeping the ordinary population skewed the same way
# spreads that mass, which is what makes the section 8 table hold whether it is
# read per category or per the direction each row names.
COVERAGE_INCREASE_SHARE = 0.82
DEDUCTIBLE_DECREASE_SHARE = 0.80

# Constructed status population (spec 01 section 6 rule 3).
N_LAPSE_REINSTATE_POLICIES = 1_200
N_TERMINATING_POLICIES = 250  # end the window cancelled or non_renewed
N_AGENT_CHANGE_POLICIES = 320  # derived category, never material

# --- Loss-to-report lag (spec 01 section 5.5, ADR-0004) ---------------------
REPORT_LAG_MEDIAN_DAYS = 4.0
REPORT_LAG_P90_DAYS = 21.0
REPORT_LAG_CAP_DAYS = 60
REPORT_LAG_MIN_DAYS = 1  # never zero

# --- Severity bands (ADR-0008) ----------------------------------------------
SEVERITY_BANDS = (
    ("minor", 0.0, 2_500.0),
    ("moderate", 2_500.0, 10_000.0),
    ("severe", 10_000.0, 50_000.0),
    ("catastrophic", 50_000.0, float("inf")),
)
SEVERITY_MIX = {"minor": 0.44, "moderate": 0.33, "severe": 0.19, "catastrophic": 0.04}

# Coverage line mix per severity band. Liability lines carry the large losses.
CLAIM_LINE_WEIGHTS = {
    "minor": {"COLL": 0.44, "COMP": 0.36, "PD": 0.14, "BI": 0.04, "UMUIM": 0.02},
    "moderate": {"COLL": 0.42, "COMP": 0.22, "PD": 0.22, "BI": 0.10, "UMUIM": 0.04},
    "severe": {"COLL": 0.30, "COMP": 0.08, "PD": 0.22, "BI": 0.32, "UMUIM": 0.08},
    "catastrophic": {"COLL": 0.06, "COMP": 0.02, "PD": 0.12, "BI": 0.68, "UMUIM": 0.12},
}

# --- Guaranteed activity tail (spec 01 section 5.4) -------------------------
ACTIVITY_TAIL_DAYS = 120
ACTIVITY_TAIL_BUCKET_DAYS = 10

# --- Scenario catalogue (spec 01 section 9) ---------------------------------
# Offsets are days *before* the anchor. Nothing here is an absolute date.
NOTEWORTHY_SCENARIOS = {
    "S1": {"name": "Coverage raised, same line claimed", "policies": 40},
    "S2": {"name": "Deductible lowered before claim", "policies": 30},
    "S3": {"name": "Change inside the loss-to-report gap", "policies": 25},
    "S4": {"name": "Rapid change cluster", "policies": 30},
    "S5": {"name": "Vehicle and address together", "policies": 35},
    "S6": {"name": "Claim near a newly raised limit", "policies": 25},
}
CONTROL_SCENARIOS = {
    "C1": {"name": "High-value claim, no preceding change", "policies": 60},
    "C2": {"name": "Frequently changed, never claimed", "policies": 80},
    "C3": {"name": "Benign gap-window change", "policies": 40},
    "C4": {"name": "Near-limit claim, no preceding change", "policies": 30},
    "C5": {"name": "Benign pattern match", "policies": 40},
}
SCENARIO_SIZES = {
    **{k: v["policies"] for k, v in NOTEWORTHY_SCENARIOS.items()},
    **{k: v["policies"] for k, v in CONTROL_SCENARIOS.items()},
}
SCENARIO_ORDER = ("S1", "S2", "S3", "S4", "S5", "S6", "C1", "C2", "C3", "C4", "C5")

# Relative offsets, in days before the anchor.
S1_COVERAGE_RAISE_OFFSET = 41
S1_LOSS_OFFSET = 17
S1_EXEMPLAR_ADDRESS_OFFSET = 55
S1_EXEMPLAR_VEHICLE_OFFSET = 30

S2_DEDUCTIBLE_CUT_OFFSET = 52
S2_LOSS_OFFSET = 20

S3_LOSS_OFFSET = 34
S3_REPORT_OFFSET = 19
S3_ADDRESS_CHANGE_OFFSET = 28

S4_CLUSTER_OFFSETS = (82, 75, 68, 60)  # four changes across 22 days
S4_LOSS_OFFSET = 31

S5_VEHICLE_OFFSET = 73
S5_ADDRESS_OFFSET = 48

S6_COVERAGE_RAISE_OFFSET = 66
S6_LOSS_OFFSET = 45
S6_LIMIT_UTILISATION = 0.97

# The demo anchor policy's collision claim sits at 97% of the newly raised
# limit, so the two-axis conjunction from ADR-0008 is visible on the S1 exemplar
# as well as on S6.
DEMO_LIMIT_UTILISATION = 0.97
DEMO_COLL_LIMIT_AFTER = 25_000.0
DEMO_COLL_LIMIT_BEFORE = 15_000.0

C1_LOSS_OFFSET_RANGE = (20, 110)
C1_QUIET_WINDOW_DAYS = 130  # no material change this far before the loss
C3_LOSS_OFFSET_RANGE = (40, 95)
C3_REPORT_LAG_RANGE = (12, 25)
C4_LOSS_OFFSET_RANGE = (25, 115)
C5_CLUSTER_SPAN_DAYS = 20
C5_CLUSTER_END_OFFSET_RANGE = (150, 260)

# --- Money ------------------------------------------------------------------
BI_LIMITS = (25_000.0, 50_000.0, 100_000.0, 250_000.0, 300_000.0, 500_000.0)
PD_LIMITS = (25_000.0, 50_000.0, 100_000.0)
UMUIM_LIMITS = (25_000.0, 50_000.0, 100_000.0, 250_000.0)
PHYSICAL_DAMAGE_LIMITS = (5_000.0, 8_000.0, 10_000.0, 15_000.0, 20_000.0, 25_000.0, 35_000.0, 50_000.0)
DEDUCTIBLES = (250.0, 500.0, 1_000.0, 2_000.0)

PREMIUM_BASE_RANGE = (780.0, 2_450.0)

POLICY_STATUSES = ("active", "lapsed", "reinstated", "cancelled", "non_renewed")
CLAIM_STATUSES = ("open", "settled")

TERM_LENGTH_DAYS = 365
