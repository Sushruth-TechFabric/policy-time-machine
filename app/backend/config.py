"""Runtime configuration, read once from the environment.

Inside Databricks Apps these are injected by the platform / app.yaml;
locally they fall back to the defaults from the P5 task brief so the
backend is runnable against a real workspace with only DATABRICKS
CLI auth configured (`DEFAULT` profile).
"""

import os

#: SQL warehouse used for the app's own deterministic queries
#: (timeline / similar / patterns) — never used by Genie, which has
#: its own warehouse configured on the Genie space.
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "e39eb96b7df5ab0f")

#: Unity Catalog catalog/schema holding the six curated tables.
CATALOG = os.environ.get("PTM_CATALOG", "workspace")
SCHEMA = os.environ.get("PTM_SCHEMA", "ptm_gold")

#: Genie space id. Deliberately no default — when unset, Genie calls
#: short-circuit to a structured "error" result so the rest of the
#: app (timelines, chips) keeps working.
GENIE_SPACE_ID = os.environ.get("GENIE_SPACE_ID") or None

#: Per-message Genie timeout, per the API contract (60s).
GENIE_TIMEOUT_SECONDS = int(os.environ.get("GENIE_TIMEOUT_SECONDS", "60"))

# --- Review agent (design spec 2026-09-17) ---------------------------------
#: Lakebase project/branch/endpoint the bundle declares. Working Branches are
#: forked from LAKEBASE_MAIN_BRANCH at runtime and never declared.
LAKEBASE_PROJECT_ID = os.environ.get("LAKEBASE_PROJECT_ID") or None
LAKEBASE_MAIN_BRANCH = os.environ.get("LAKEBASE_MAIN_BRANCH", "production")
LAKEBASE_MAIN_ENDPOINT = os.environ.get("LAKEBASE_MAIN_ENDPOINT", "primary")
#: Injected by the Databricks Apps resource binding; absent in the Workflow,
#: where lakebase.py resolves them from the SDK instead.
LAKEBASE_DATABASE = os.environ.get("PGDATABASE", "review")
LAKEBASE_HOST = os.environ.get("PGHOST") or None
LAKEBASE_USER = os.environ.get("PGUSER") or None
#: The app SP's application id; the migration grants it table privileges so
#: tables created by the Workflow's run-as user stay readable by the app.
APP_SERVICE_PRINCIPAL_ID = os.environ.get("APP_SERVICE_PRINCIPAL_ID") or None

REVIEW_MODEL_ENDPOINT = os.environ.get("REVIEW_MODEL_ENDPOINT", "databricks-claude-sonnet-4-5")
REVIEW_MLFLOW_EXPERIMENT = os.environ.get("REVIEW_MLFLOW_EXPERIMENT", "/Shared/policy-time-machine-review")
REVIEW_DEMO_HOLD_SECONDS = int(os.environ.get("REVIEW_DEMO_HOLD_SECONDS", "0"))
REVIEW_NIGHTLY_CAP = int(os.environ.get("REVIEW_NIGHTLY_CAP", "20"))
REVIEW_RUN_TIMEOUT_SECONDS = int(os.environ.get("REVIEW_RUN_TIMEOUT_SECONDS", "180"))
REVIEW_BRANCH_TTL_SECONDS = int(os.environ.get("REVIEW_BRANCH_TTL_SECONDS", "900"))


def lakebase_configured() -> bool:
    return bool(LAKEBASE_PROJECT_ID)
