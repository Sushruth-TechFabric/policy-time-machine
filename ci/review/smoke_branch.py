#!/usr/bin/env python3
"""Working Branch lifecycle smoke test: create branch + endpoint, connect,
SELECT 1, delete. Fails fast with a clear message for the two failures a
engineer deploying the bundle is most likely to hit — no Lakebase project,
or an identity without CAN MANAGE on it.

Usage: LAKEBASE_PROJECT_ID=policy-time-machine python -m ci.review.smoke_branch
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from databricks.sdk import WorkspaceClient  # noqa: E402
from databricks.sdk.errors import NotFound, PermissionDenied  # noqa: E402

from backend.review.lakebase import BranchLifecycle, connect_branch, main_branch_name  # noqa: E402
from ci.genie import config  # noqa: E402


def main() -> int:
    if not os.environ.get("LAKEBASE_PROJECT_ID"):
        print("LAKEBASE_PROJECT_ID is not set (bundle default: policy-time-machine)")
        return 1
    client = WorkspaceClient(profile=config.DATABRICKS_PROFILE)
    lifecycle = BranchLifecycle(client)
    run_id = f"smoke{int(time.time())}"
    started = time.monotonic()
    try:
        branch = lifecycle.create(run_id)
    except NotFound:
        print(f"Lakebase project not found: {main_branch_name()} — deploy the bundle first")
        return 1
    except PermissionDenied:
        print("This identity lacks CAN MANAGE on the Lakebase project — grant it in the project's permissions")
        return 1
    print(f"branch ready in {time.monotonic() - started:.1f}s: {branch.branch_name} host={branch.host}")
    try:
        with connect_branch(client, branch) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                assert cur.fetchone()[0] == 1
                cur.execute("SELECT count(*) FROM review.routed_claim")
                print(f"branch sees {cur.fetchone()[0]} routed claims inherited from main")
    finally:
        lifecycle.delete(branch)
        print(f"branch deleted; total {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
