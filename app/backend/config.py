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
