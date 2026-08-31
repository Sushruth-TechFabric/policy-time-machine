"""Task 3 of the ``policy_time_machine_regeneration`` job: load_source_tables.

Recreates the nine bronze Delta tables (spec 01 section 3, schema
``ptm_bronze`` — ADR-0016) from the parquet the generator just wrote to the
volume, one `CREATE OR REPLACE TABLE ... AS
SELECT * FROM parquet.`<path>`` per table. This runs as `spark.sql` in a
serverless Python task rather than a separate SQL task against the warehouse
(spec P8: "pick the simpler") — one script loops the nine tables with
consistent logging and a single failure mode, instead of a second job-task
type and a `.sql` file whose `source: WORKSPACE`/`GIT` resolution is its own
source of surprise in a non-git bundle.

`parquet.`<path>`` preserves the DATE columns as DATE: `generator/emit.py`
already casts them to Arrow `date32` at write time, so no manual casting is
needed here — a second, drifting copy of that column list is exactly the
failure mode ADR-0013's docstring warns about.

Table order does not matter here: these are raw sources with no foreign-key
enforcement at write time (the DLT pipeline downstream is what encodes the
real constraints), so all nine can be recreated independently.
"""

from __future__ import annotations

from pyspark.sql import SparkSession

CATALOG = "workspace"
SCHEMA = "ptm_bronze"
VOLUME_DIR = "/Volumes/workspace/ptm_bronze/raw"

# Matches generator/emit.py:TABLE_ORDER — the nine source tables the
# generator emits one parquet file per.
TABLES = (
    "customer",
    "policy_history",
    "policy_coverage_history",
    "vehicle",
    "agent",
    "claim",
    "claim_payment",
    "scenario_assignment",
    "generation_manifest",
)


def main() -> int:
    spark = SparkSession.builder.getOrCreate()
    for table in TABLES:
        path = f"{VOLUME_DIR}/{table}.parquet"
        qualified = f"{CATALOG}.{SCHEMA}.{table}"
        print(f"[load_source_tables] {qualified} <- {path}")
        spark.sql(f"CREATE OR REPLACE TABLE {qualified} AS SELECT * FROM parquet.`{path}`")
        count = spark.table(qualified).count()
        print(f"  {count:,} rows")
    return 0


if __name__ == "__main__":
    # Quirk (Databricks Free Edition, serverless spark_python_task): the exec
    # wrapper treats any raised SystemExit — even code 0 — as an uncaught
    # exception and fails the task, so only exit explicitly on failure.
    _exit_code = main()
    if _exit_code:
        raise SystemExit(_exit_code)
