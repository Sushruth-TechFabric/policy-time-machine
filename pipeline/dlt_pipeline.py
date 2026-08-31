"""Lakeflow Declarative Pipeline for the Policy Time Machine semantic layer.

Builds the six curated tables of `docs/specs/02-semantic-layer.md` from the raw
source tables of spec 01 §3, with the expectations of spec 02 §8 enforced at
write time (ADR-0013).

This module is a **thin wrapper and nothing else**. Every transformation rule
lives in ``transformations.py`` and every expectation predicate lives in
``expectations.py``; both import without PySpark, and both are unit tested
locally against hand-built fixtures.

------------------------------------------------------------------------------
How the wrapper maps onto the shared logic, and why
------------------------------------------------------------------------------
Two options were open: re-express the logic as PySpark (window functions,
correlated lookahead joins) or run the shared pandas functions from Spark. **The
shared functions are called directly** — read the source Delta tables, hand the
pandas frames to ``transformations.build_all``, write the results back — for
three reasons:

1. *A second implementation is the failure mode the ADRs name by hand.* ADR-0008
   requires ``next_claim_severity`` and ``severity_band`` to come from the same
   code path. ADR-0009 requires the ``policy_profile`` booleans and the
   ``policy_pattern_match`` rows to come from one rule pass, "never from a second
   copy of the predicate", because ADR-0007 puts the generated SQL in the
   evidence panel where a disagreement is visible on screen. A PySpark mirror of
   ``transformations.py`` reintroduces exactly that risk for every column, and
   the local suite would stop testing what actually runs.
2. *The dataset is deliberately sized for it.* Spec 01 §4 targets ~8,000
   policies, ~95,000 change events and ~5,500 claims, "sized so exact similarity
   computation stays trivial"; ADR-0010 leans on the same fact for exact
   brute-force neighbours. That is tens of megabytes.
3. *Similarity cannot be distributed anyway.* Z-scores are population statistics
   and top-K is an all-pairs scan, so ``policy_profile`` has to be collected
   whatever else happens.

The scale-out path, should the corpus ever outgrow the driver, is
``groupBy("policy_id").applyInPandas(...)`` over the same ``build_*`` functions
for the four per-policy tables, leaving ``policy_profile`` and
``policy_similarity`` on the driver. It is deliberately not taken: at this volume
it buys nothing and costs a cogroup/broadcast plumbing layer for the four inputs
each builder needs.

------------------------------------------------------------------------------
Expectations
------------------------------------------------------------------------------
All are ``@dlt.expect_all_or_fail``: a violated invariant fails the run rather
than quarantining rows, because these rules are the product's correctness rather
than a data quality score.

E1–E12, E17, E18 and E19 are attached to the table they constrain. E8, E13, E14
and E16 span tables or rows and are enforced by the ``qa_*`` temporary assertion
tables at the foot of this module, which materialise the join or the window and
fail on any violating row.

**E20 — "no column stores an event-to-now delta" — is a property of the schema,
not of a row, and spec 02 §8 enforces it by review against the specification.**
That review, recorded here:

* The only recency columns in the curated layer are
  ``policy_profile.last_material_change_date`` and ``last_claim_date``. Both are
  DATE. "Recent" is computed at query time, defaulting to 90 days.
* Every stored delta is event-to-event, anchored on two dated events, so none
  goes stale as real time passes: ``days_to_next_claim_loss``,
  ``days_to_next_claim_report``, ``loss_to_report_days``,
  ``days_since_last_material_change_before_loss``, and the five
  ``nearest_*_change_offset_days``.
* ``material_changes_per_year`` and ``claims_per_year`` normalise by tenure,
  which ADR-0010 requires so tenure does not dominate similarity. They answer
  "how often", not "how long ago", so they are rates rather than deltas.
* ``policy_start_date``, ``term_start_date`` and ``term_end_date`` are attribute
  dates, not event timestamps; ``term_end_date`` legitimately sits in the future
  and is exempt from E17 (spec 01 §5 rule 2).

``tests/test_profile.py::test_e20_no_column_stores_an_event_to_now_delta`` keeps
the same review executable as a column-name check.

------------------------------------------------------------------------------
Configuration — Spark conf, set in the Asset Bundle pipeline definition
------------------------------------------------------------------------------
``ptm.catalog``      default ``workspace``
``ptm.schema``       default ``policy_time_machine``
``ptm.anchor_date``  ``YYYY-MM-DD``; the generator's anchor (ADR-0006). Left
                     unset by the scheduled regeneration job (P8): when empty,
                     ``ANCHOR_DATE`` is read from
                     ``generation_manifest.anchor_date`` instead, so E17 always
                     checks the anchor the data was actually built at, not the
                     date the pipeline happened to run. Only set explicitly for
                     a one-off run against a manifest-less or ad hoc dataset.
``ptm.k``            default 20; similarity top-K
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

import dlt
import pandas as pd
from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql import types as Tp

import expectations as X
import transformations as T

spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

CATALOG = spark.conf.get("ptm.catalog", "workspace")
SCHEMA = spark.conf.get("ptm.schema", "policy_time_machine")
K = int(spark.conf.get("ptm.k", str(T.K_NEIGHBOURS)))

_ANCHOR_CONF = spark.conf.get("ptm.anchor_date", "")
if _ANCHOR_CONF:
    ANCHOR_DATE = _dt.date.fromisoformat(_ANCHOR_CONF)
else:
    # ptm.anchor_date is deliberately left unset by the bundle (P8): the
    # generator's own anchor, written to generation_manifest at emit time, is
    # the single source of truth for what the source tables actually
    # contain. Falling back to date.today() here would let a scheduled
    # pipeline run silently disagree with the dataset it is reading — the
    # anchor drifts a day off the generator's the moment the job runs after
    # midnight relative to generation.
    _manifest_anchor = spark.sql(
        f"SELECT anchor_date FROM {CATALOG}.{SCHEMA}.generation_manifest LIMIT 1"
    ).collect()[0][0]
    ANCHOR_DATE = (
        _manifest_anchor
        if isinstance(_manifest_anchor, _dt.date)
        else _dt.date.fromisoformat(str(_manifest_anchor))
    )

EXPECTATIONS = X.all_expectations(ANCHOR_DATE, K)


# ---------------------------------------------------------------------------
# Source reads and the single driver-side build
# ---------------------------------------------------------------------------

def _qualified(name: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{name}"


def _source(name: str) -> "pd.DataFrame":
    return spark.read.table(_qualified(name)).toPandas()


def _exists(name: str) -> bool:
    # spark.catalog.tableExists is not on the serverless Py4J allowlist
    # (PY4J_BLOCKED_API); information_schema is plain SQL and always is.
    return (
        spark.sql(
            f"SELECT 1 FROM {CATALOG}.information_schema.tables "
            f"WHERE table_schema = '{SCHEMA}' AND table_name = '{name}' LIMIT 1"
        ).count()
        > 0
    )


_BUILT: dict[str, Any] | None = None


def _build() -> dict[str, Any]:
    """Run the shared transformation logic once per pipeline run."""
    global _BUILT
    if _BUILT is not None:
        return _BUILT

    policy_history = _source("policy_history")
    policy_coverage_history = _source("policy_coverage_history")
    claims = _source("claim")
    claim_payment = _source("claim_payment") if _exists("claim_payment") else None

    # Spec 01 §3 lists no change-event source table, yet §2 gives change events an
    # identifier format and §4 a volume target, both of which read as generator
    # output. Both readings are supported: consume the raw table when the
    # generator emits one, otherwise reconstruct the same grain by diffing the
    # SCD Type 2 versions.
    if _exists("change_event"):
        changes = _source("change_event")
    else:
        changes = T.derive_change_events_from_scd2(
            policy_history, policy_coverage_history
        )

    _BUILT = T.build_all(
        changes=changes,
        claims=claims,
        policy_history=policy_history,
        policy_coverage_history=policy_coverage_history,
        claim_payment=claim_payment,
        anchor_date=ANCHOR_DATE,
        k=K,
    )
    return _BUILT


_SPARK_TYPES = {
    "string": Tp.StringType(),
    "date": Tp.DateType(),
    "int": Tp.IntegerType(),
    "decimal": Tp.DoubleType(),
    "boolean": Tp.BooleanType(),
}


def spark_schema(table: str) -> Tp.StructType:
    """Built from the same declared schema the pandas layer casts to, so the
    Spark and pandas views of a table cannot drift."""
    return Tp.StructType([
        Tp.StructField(name, _SPARK_TYPES[kind], True)
        for name, kind in T.SCHEMAS[table]
    ])


def _emit(table: str):
    """One curated pandas frame, as a Spark DataFrame with the declared schema.

    Rows are converted to Python natives rather than handed to Arrow: the pandas
    layer uses nullable extension dtypes (``Int64``, ``Float64``, ``boolean``) so
    that NULL stays NULL rather than becoming NaN, and this keeps that guarantee
    all the way into Delta.
    """
    pdf = _build()[table]
    kinds = dict(T.SCHEMAS[table])
    columns = [name for name, _ in T.SCHEMAS[table]]
    rows = []
    for record in pdf.to_dict("records"):
        row = []
        for column in columns:
            value = record[column]
            if value is None or (
                not isinstance(value, (_dt.date, str)) and pd.isna(value)
            ):
                row.append(None)
            elif kinds[column] == "int":
                row.append(int(value))
            elif kinds[column] == "decimal":
                row.append(float(value))
            elif kinds[column] == "boolean":
                row.append(bool(value))
            elif kinds[column] == "date":
                row.append(T.to_date(value))
            else:
                row.append(str(value))
        rows.append(tuple(row))
    return spark.createDataFrame(rows, schema=spark_schema(table))


# ---------------------------------------------------------------------------
# The six curated tables (spec 02 §2–§7)
# ---------------------------------------------------------------------------

@dlt.table(
    name="policy_change_event",
    comment="One row per field change on a policy, material or otherwise. "
            "next_claim_id is the first claim reported at or after the change "
            "and is many-to-one by design.",
    table_properties={"quality": "gold"},
)
@dlt.expect_all_or_fail(EXPECTATIONS["policy_change_event"])
def policy_change_event():
    return _emit("policy_change_event")


@dlt.table(
    name="claim_event",
    comment="One row per claim. The table for claim-level counting. All "
            "prior-change context is anchored on loss_date.",
    table_properties={"quality": "gold"},
)
@dlt.expect_all_or_fail(EXPECTATIONS["claim_event"])
def claim_event():
    return _emit("claim_event")


@dlt.table(
    name="policy_pattern_match",
    comment="One row per policy and matched noteworthy pattern. Rules are named "
            "and deterministic; a match makes a policy an investigation "
            "candidate and asserts nothing about a person.",
    table_properties={"quality": "gold"},
)
@dlt.expect_all_or_fail(EXPECTATIONS["policy_pattern_match"])
def policy_pattern_match():
    return _emit("policy_pattern_match")


@dlt.table(
    name="policy_profile",
    comment="One row per policy: current state, behavioural summary, recency "
            "dates and the noteworthy pattern flags. Recency is stored as dates, "
            "never as day counts.",
    table_properties={"quality": "gold"},
)
@dlt.expect_all_or_fail(EXPECTATIONS["policy_profile"])
def policy_profile():
    return _emit("policy_profile")


@dlt.table(
    name="policy_timeline_event",
    comment="For reading one policy's history. Do not aggregate; this table "
            "mixes grains.",
    table_properties={"quality": "gold"},
)
@dlt.expect_all_or_fail(EXPECTATIONS["policy_timeline_event"])
def policy_timeline_event():
    return _emit("policy_timeline_event")


@dlt.table(
    name="policy_similarity",
    comment="Pre-computed nearest neighbours by behavioural history, top 20 per "
            "policy. Directional: A appearing in B's list does not imply the "
            "reverse.",
    table_properties={"quality": "gold"},
)
@dlt.expect_all_or_fail(EXPECTATIONS["policy_similarity"])
def policy_similarity():
    return _emit("policy_similarity")


# ---------------------------------------------------------------------------
# Cross-table assertion tables — E8, E13, E14, E16
#
# A DLT expectation is a row predicate over one dataset, so invariants that span
# tables are enforced by materialising the join or the window and failing on any
# violating row. These are temporary: they exist to fail the run, not to be read
# by Genie, and so are never part of the six-table Genie space (ADR-0002).
# ---------------------------------------------------------------------------

@dlt.table(
    name="qa_severity_agreement",
    comment="E8 — next_claim_severity must equal severity_band for the same claim.",
    temporary=True,
)
@dlt.expect_all_or_fail(X.QA_SEVERITY_AGREEMENT)
def qa_severity_agreement():
    changes = dlt.read("policy_change_event").filter("next_claim_id IS NOT NULL").alias("c")
    claims = dlt.read("claim_event").alias("k")
    return (
        changes.join(claims, F.col("c.next_claim_id") == F.col("k.claim_id"), "inner")
        .select(
            F.col("c.change_event_id"),
            F.col("c.next_claim_id"),
            F.col("c.next_claim_severity"),
            F.col("k.severity_band"),
            F.col("c.next_claim_amount"),
            F.col("k.settled_amount"),
            F.col("c.next_claim_coverage_line"),
            F.col("k.coverage_line"),
        )
    )


@dlt.table(
    name="qa_pattern_consistency",
    comment="E13 and E14 — the policy_profile flags and noteworthy_pattern_count "
            "must agree with policy_pattern_match, because both derive from one "
            "rule evaluation pass (ADR-0009).",
    temporary=True,
)
@dlt.expect_all_or_fail(X.QA_PATTERN_CONSISTENCY)
def qa_pattern_consistency():
    aggregations = [F.countDistinct("pattern_code").alias("matched_codes")]
    aggregations += [
        F.sum(F.when(F.col("pattern_code") == code, 1).otherwise(0)).alias(f"matched_{code}")
        for code in T.PATTERN_CODES
    ]
    per_policy = dlt.read("policy_pattern_match").groupBy("policy_id").agg(*aggregations)

    profile = dlt.read("policy_profile").select(
        "policy_id", "noteworthy_pattern_count", *T.PATTERN_FLAG_COLUMNS
    )
    fills = {"matched_codes": 0}
    fills.update({f"matched_{code}": 0 for code in T.PATTERN_CODES})
    # Policies with nothing noteworthy have no match rows at all; the left join
    # plus fill is what makes "noteworthy_pattern_count = 0" a checked claim
    # rather than an untested absence.
    return profile.join(per_policy, on="policy_id", how="left").fillna(fills)


@dlt.table(
    name="qa_similarity_rank_density",
    comment="E16 — rank must be dense 1..K per policy, ordered by "
            "similarity_score DESC then similar_policy_id ASC (ADR-0010).",
    temporary=True,
)
@dlt.expect_all_or_fail(X.QA_SIMILARITY_RANK_DENSITY)
def qa_similarity_rank_density():
    window = Window.partitionBy("policy_id").orderBy(
        F.col("similarity_score").desc(), F.col("similar_policy_id").asc()
    )
    return (
        dlt.read("policy_similarity")
        .withColumn("expected_rank", F.row_number().over(window))
        .select("policy_id", "similar_policy_id", "rank", "expected_rank",
                "similarity_score")
    )
