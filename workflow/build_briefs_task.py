# workflow/build_briefs_task.py
"""Task 6 of ``policy_time_machine_regeneration``: build_briefs.

Works the queue sequentially through the same harness the app uses:
undisposed Routed Claims without a Brief, newest Report Date first,
capped at REVIEW_NIGHTLY_CAP (design spec §10). One Working Branch at a
time (Free Edition compute limit). Never fails the job because a Run
failed — a failed Run is re-queued and reported in the task log.
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

from backend.config import REVIEW_NIGHTLY_CAP  # noqa: E402
from backend.review.lakebase import connect_main  # noqa: E402
from backend.review.runner import build_deps, work_queue  # noqa: E402
from backend.review.store import ReviewStore  # noqa: E402


def main() -> int:
    client = WorkspaceClient()
    store = ReviewStore(connect_main(client))
    outcomes = work_queue(build_deps(client, store, demo_hold_seconds=0), cap=REVIEW_NIGHTLY_CAP)
    completed = sum(1 for o in outcomes if o.status == "completed")
    print(f"[build_briefs] {completed}/{len(outcomes)} Runs completed", flush=True)
    return 0


if __name__ == "__main__":
    _exit_code = main()
    if _exit_code:
        sys.exit(_exit_code)
