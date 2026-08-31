"""Task 1 of the ``policy_time_machine_regeneration`` job: generate.

Equivalent to running

    python -m generator --seed 42 --anchor-date <run-date> --out /Volumes/workspace/ptm_bronze/raw

but invoked in-process, because a serverless Python task runs this file
directly rather than a shell. ``generator/`` is synced by the bundle as a
sibling of ``workflow/``, so the bundle root is added to ``sys.path`` and the
package is imported rather than shelled out to.

Quirk (Databricks Free Edition, serverless spark_python_task): the file is
``exec``'d by an IPython-style wrapper rather than launched as a normal
``python <file>`` process. That wrapper does not set ``__file__`` in the
executed module's globals (``os.path.abspath(__file__)`` raises
``NameError``), and it does not prepend the script's own directory to
``sys.path`` either, so neither the usual ``__file__``-relative trick nor a
plain sibling-module import can locate the bundle root. The bundle instead
passes its own deployed root as an explicit ``--bundle-root`` task parameter,
resolved from the ``${workspace.file_path}`` substitution at deploy time, and
this script scans ``sys.argv`` for it directly — no import of anything outside
the standard library happens before ``sys.path`` is fixed up.

``anchor_date`` is derived at run time as *today in UTC* (ADR-0006: the
dataset is anchored to its generation date, and the generator/warehouse must
agree on UTC so relative-date questions don't drift by a day near midnight).
The seed is fixed at 42, so identity — policy IDs, customer IDs, scenario
membership, including the DEMO policy — is stable across every regeneration;
only dates shift.
"""

from __future__ import annotations

import sys


def _bundle_root_from_argv() -> str:
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg == "--bundle-root" and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith("--bundle-root="):
            return arg.split("=", 1)[1]
    raise SystemExit(
        "--bundle-root is required (the job task passes ${workspace.file_path})"
    )


_BUNDLE_ROOT = _bundle_root_from_argv()
if _BUNDLE_ROOT not in sys.path:
    sys.path.insert(0, _BUNDLE_ROOT)

import datetime as dt  # noqa: E402

from generator.__main__ import main as generator_main  # noqa: E402

SEED = 42
CATALOG = "workspace"
OUT_DIR = f"/Volumes/{CATALOG}/ptm_bronze/raw"

# The medallion schemas and the bronze landing volume (ADR-0016). Ensured
# here with IF NOT EXISTS rather than declared as bundle `schemas` resources:
# development-mode deploys prefix bundle-managed schema names, which would
# break every hardcoded `ptm_*` reference across the pipeline, app and Genie
# space. This task runs first in the job, so the DDL is in place before the
# generator writes to the volume and the DLT pipeline publishes.
MEDALLION_DDL = (
    f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.ptm_bronze",
    f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.ptm_silver",
    f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.ptm_gold",
    f"CREATE VOLUME IF NOT EXISTS {CATALOG}.ptm_bronze.raw",
)


def _ensure_medallion_layout() -> None:
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    for statement in MEDALLION_DDL:
        print(f"[generate] {statement}")
        spark.sql(statement)


def main() -> int:
    _ensure_medallion_layout()
    anchor = dt.datetime.now(dt.timezone.utc).date().isoformat()
    print(f"[generate] seed={SEED} anchor-date={anchor} out={OUT_DIR} bundle-root={_BUNDLE_ROOT}")
    return generator_main(["--seed", str(SEED), "--anchor-date", anchor, "--out", OUT_DIR])


if __name__ == "__main__":
    # Quirk (Databricks Free Edition, serverless spark_python_task): the file
    # runs inside an IPython-style exec wrapper that treats *any* raised
    # SystemExit — including code 0 — as an uncaught exception and fails the
    # task. sys.exit(0) on success was observed failing runs with
    # "SystemExit: 0" even though the script had completed normally. Only
    # exit explicitly when there is something to fail on.
    _exit_code = main()
    if _exit_code:
        sys.exit(_exit_code)
