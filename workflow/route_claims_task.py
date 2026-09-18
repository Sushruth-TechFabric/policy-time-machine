# workflow/route_claims_task.py
"""Task 5 of ``policy_time_machine_regeneration``: route_claims.

Applies the idempotent review schema to Lakebase main, evaluates the one
Routing Rule against gold, and upserts Routed Claims. Runs as the job's
run-as user (the Lakebase project owner), so it can also grant the app
service principal the table privileges it needs (design spec §7.2).

Same ``--bundle-root`` bootstrap as generate_task.py (serverless
spark_python_task sets neither __file__ nor a script-relative sys.path).
The review package lives under app/backend, which the bundle syncs, so
``<bundle-root>/app`` is added to sys.path and ``backend.review`` imported.
"""

from __future__ import annotations

import os
import sys


def _bundle_root_from_argv() -> str:
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg == "--bundle-root" and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith("--bundle-root="):
            return arg.split("=", 1)[1]
    raise SystemExit("--bundle-root is required (the job task passes ${workspace.file_path})")


_BUNDLE_ROOT = _bundle_root_from_argv()
_APP_ROOT = os.path.join(_BUNDLE_ROOT, "app")
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

# Job parameters reach a spark_python_task as "--name value" argv pairs only
# when listed in the task's `parameters`; dbutils.widgets is unavailable in a
# plain Python task, so copy them into the environment explicitly before any
# backend.config import (config.py reads os.environ at import time).
_PARAMS = {"LAKEBASE_PROJECT_ID": "policy-time-machine",
           "APP_SERVICE_PRINCIPAL_ID": None, "REVIEW_MODEL_ENDPOINT": None, "REVIEW_MLFLOW_EXPERIMENT": None}
for _i, _arg in enumerate(sys.argv[1:]):
    if _arg.startswith("--") and _arg[2:] in _PARAMS and _i + 2 <= len(sys.argv[1:]):
        os.environ.setdefault(_arg[2:], sys.argv[1:][_i + 1])
os.environ.setdefault("LAKEBASE_PROJECT_ID", "policy-time-machine")

from databricks.sdk import WorkspaceClient  # noqa: E402

from backend.config import APP_SERVICE_PRINCIPAL_ID  # noqa: E402
from backend.review.lakebase import connect_main  # noqa: E402
from backend.review.routing import route_claims  # noqa: E402
from backend.review.schema import ensure_schema  # noqa: E402
from backend.review.store import ReviewStore  # noqa: E402


def main() -> int:
    client = WorkspaceClient()
    conn = connect_main(client)
    ensure_schema(conn, APP_SERVICE_PRINCIPAL_ID)
    store = ReviewStore(conn)
    count = route_claims(client, store)
    print(f"[route_claims] {count} routed claims upserted", flush=True)
    return 0


if __name__ == "__main__":
    _exit_code = main()
    if _exit_code:
        sys.exit(_exit_code)
