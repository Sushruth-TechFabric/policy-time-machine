"""Fixed workspace configuration for the Genie test layer.

Values match the task brief / `app/backend/config.py` defaults for this
workspace. No secrets here — auth is via the `DEFAULT` Databricks CLI
profile already logged in on this machine.
"""

import os

HOST = "https://dbc-1edff070-fbb9.cloud.databricks.com"
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "e39eb96b7df5ab0f")
GENIE_SPACE_ID = os.environ.get("GENIE_SPACE_ID", "01f1a5808edd1859b78359723b7c5379")
CATALOG = os.environ.get("PTM_CATALOG", "workspace")
SCHEMA = os.environ.get("PTM_SCHEMA", "ptm_gold")
# Generator artefacts (scenario ground truth, manifest) live in bronze (ADR-0016)
BRONZE_SCHEMA = os.environ.get("PTM_BRONZE_SCHEMA", "ptm_bronze")
DATABRICKS_PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE", "DEFAULT")

#: Demo anchor policy (generation_manifest.demo_policy_id at time of writing).
DEMO_POLICY_ID = "P-10155"

#: Gentle pacing between sequential Genie calls.
SLEEP_BETWEEN_CALLS_SECONDS = 3
