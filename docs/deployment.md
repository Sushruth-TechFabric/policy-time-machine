# Deployment guide

Policy Time Machine deploys as one Databricks Asset Bundle, defined in [`../databricks.yml`](../databricks.yml). Deploying the bundle is how every environment gets the product. Databricks Apps has no anonymous or public access, so nothing in this guide assumes a public URL ([ADR-0012](./adr/0012-the-app-runs-on-databricks-apps-as-fastapi-plus-react.md)).

## What the bundle creates

| Resource | Name | Notes |
|---|---|---|
| Databricks App | `policy-time-machine` | FastAPI plus the built React bundle. User scopes `dashboards.genie` and `sql`. Bound to the Lakebase database |
| Lakeflow Declarative Pipeline | `policy_time_machine_pipeline` | Serverless. Writes `ptm_silver` and `ptm_gold` |
| Workflows job | `policy_time_machine_regeneration` | Daily at 09:00 UTC, one concurrent run |
| Lakebase project | `policy-time-machine` | With the `production` branch, the `primary` read-write endpoint, the app's Postgres role and the `review` database |
| MLflow experiment | `/Shared/policy-time-machine-review` | Agent traces. The app's service principal has edit rights |

The `dev` target runs in development mode, which prefixes the pipeline, job and experiment names with `[dev <your user name>]`. The names above are the unprefixed ones a production-mode target gets. The app and the Lakebase project keep their names in every mode.

The Genie space is **not** a bundle resource type. It is created and updated by `genie/build_space.py`, and its id is passed to the app as configuration.

## Environments

| Environment | Bundle target | Status |
|---|---|---|
| Development | `dev`, the default | Live. A Databricks Free Edition workspace, serverless only, catalog `workspace` |
| Staging | not yet defined | Planned. See [`roadmap.md`](./roadmap.md) |
| Production | not yet defined | Planned. See [`roadmap.md`](./roadmap.md) |

The development workspace is Free Edition, which imposes limits that the code and this guide account for. They are called out where they apply, and none of them is a design assumption: a standard workspace removes them.

Several workspace identifiers are currently literals with development values: the Genie space id and SQL warehouse id in `databricks.yml`, `app/app.yaml`, `genie/build_space.py` and `ci/genie/config.py`, and the catalog name `workspace`. Turning these into per-target bundle variables is the first step of adding a second environment, and it is tracked in the roadmap.

## Configuration

Set in the `config.env` block of the app resource in `databricks.yml`. `app/app.yaml` is its local twin, so keep the two in step.

| Variable | Purpose | Default |
|---|---|---|
| `GENIE_SPACE_ID` | The Genie space the app proxies to. Unset, Genie calls return a structured error and the rest of the app works | none |
| `DATABRICKS_WAREHOUSE_ID` | Warehouse for the app's deterministic queries | development warehouse |
| `PTM_CATALOG`, `PTM_SCHEMA` | Location of the gold tables | `workspace`, `ptm_gold` |
| `LAKEBASE_PROJECT_ID` | Lakebase project holding the review record. Unset, the review record is in-memory | none |
| `LAKEBASE_MAIN_BRANCH`, `LAKEBASE_MAIN_ENDPOINT` | Branch and endpoint that Working Branches fork from | `production`, `primary` |
| `APP_SERVICE_PRINCIPAL_ID` | The app service principal's application id, used for Lakebase grants | bundle variable |
| `REVIEW_MODEL_ENDPOINT` | Model Serving chat endpoint the agent calls | bundle variable |
| `REVIEW_MLFLOW_EXPERIMENT` | Experiment that receives agent traces | the bundle's experiment |
| `REVIEW_NIGHTLY_CAP` | Maximum Briefs the nightly job builds | `20` |
| `REVIEW_RUN_TIMEOUT_SECONDS` | Hard limit on one Run | `180` |
| `REVIEW_BRANCH_TTL_SECONDS` | Expiry on a Working Branch, a backstop if deletion fails | `900` |
| `REVIEW_DEMO_HOLD_SECONDS` | Holds a Working Branch open before deletion so it can be shown live. Keep at `0` outside a presentation | `0` |
| `GENIE_TIMEOUT_SECONDS` | Per-message Genie timeout | `60` |

`PGHOST`, `PGUSER` and `PGDATABASE` are injected by the app's Lakebase resource binding and are not set by hand.

Bundle variables: `app_service_principal_id` and `review_model_endpoint`.

### Choosing `REVIEW_MODEL_ENDPOINT`

It must name an **enabled, pay-per-token chat endpoint** in the target workspace. The harness is model-agnostic, exchanging one JSON object per turn, so any listed chat endpoint works. A disabled or absent endpoint fails every Run. There is no silent fallback. List what a workspace offers with:

```bash
databricks api get /api/2.0/serving-endpoints
```

The development workspace exposes no Claude endpoints (checked 2026-09-17), so the bundle default is `databricks-gpt-oss-120b`. Confirm the choice per workspace, then run the Brief contract.

## First deploy to a new workspace

The only target today is `dev`, and it pins the development workspace's host. Deploying anywhere else starts with step 1. Skip it when deploying the development target.

1. **Point the bundle at the workspace.** Add a target to `databricks.yml` with the new workspace's `host`, and replace the development literals listed under [Environments](#environments): the SQL warehouse id and the catalog name now, the Genie space id in step 7. Without a target of its own, `databricks bundle deploy` resolves the `dev` host whatever profile is logged in. The `app_service_principal_id` variable also defaults to the development app's service principal, which does not exist in a new workspace: the app has to exist before its service principal does. Create the app first (`databricks apps create policy-time-machine`), bind it to the bundle (`databricks bundle deployment bind -t <target> policy_time_machine_app policy-time-machine`), read the application id from Apps > app > Authorization, and set it in the new target or pass `--var app_service_principal_id=<id>`. This step has not been exercised yet, because no second workspace exists. Treat it as the known shape of the work, and correct it here on the first real run.
2. **Authenticate.** `databricks auth login --host <workspace-url>` and confirm Unity Catalog, Genie, Databricks Apps, Lakebase and Model Serving are available.
3. **Check for an existing Lakebase project** if the account is Free Edition. See [Lakebase constraints](#lakebase-constraints).
4. **Build the frontend.** The bundle uploads only the built output.
   ```bash
   (cd app/frontend && npm ci && npm run build)
   ```
5. **Deploy the bundle, then roll the app out.** `bundle deploy` uploads the source and updates the app resource. It does not start the new code: `bundle run` on the app resource does.
   ```bash
   databricks bundle validate -t <target>
   databricks bundle deploy -t <target>
   databricks bundle run -t <target> policy_time_machine_app
   ```
6. **Load data and build the gold tables.**
   ```bash
   databricks bundle run -t <target> policy_time_machine_regeneration
   ```
   On a first deploy the Genie space does not exist yet, so `build_briefs` cannot complete any Run. Run the job again after step 7.
7. **Create the Genie space and its functions**, then put the returned id into the app configuration and repeat step 5. `build_space.py` imports the pipeline's vocabulary rules, so it needs an environment with pandas: the app backend's works.
   ```bash
   (cd genie && ../app/.venv/bin/python build_space.py create-functions && ../app/.venv/bin/python build_space.py create)
   ```
8. **Apply the one-time grants** below.
9. **Verify.** Open the app once as yourself to accept the user-authorization consent prompt. Then run the [release gate](./operations.md#release-gate).

Every later deploy is steps 4 and 5.

## One-time grants

These are not bundle resource types, so they are applied once per workspace.

**The app's service principal needs `CAN_RUN` on the Genie space**, so the app can call Genie on a user's behalf:

```bash
databricks api patch /api/2.0/permissions/genie/<GENIE_SPACE_ID> --json \
  '{"access_control_list":[{"service_principal_name":"<APP_SERVICE_PRINCIPAL_ID>","permission_level":"CAN_RUN"}]}'
```

**Users need Unity Catalog access to the gold schema, and only the gold schema:**

```sql
GRANT USE SCHEMA ON SCHEMA <catalog>.ptm_gold TO `<group>`;
GRANT SELECT     ON SCHEMA <catalog>.ptm_gold TO `<group>`;
GRANT EXECUTE    ON SCHEMA <catalog>.ptm_gold TO `<group>`;
```

`EXECUTE` covers the Unity Catalog functions attached to the Genie space as certified answers. Without it Genie fails every question with "No access to certified answer", even ones that never call a function. Whoever created the functions owns them and never sees this.

**The app's service principal needs the same three grants.** Review Runs ask Genie and the warehouse under the app's identity (ADR-0019), not the viewer's:

```sql
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA <catalog>.ptm_gold TO `<APP_SERVICE_PRINCIPAL_ID>`;
```

The service principal is granted nothing on `ptm_bronze` or `ptm_silver`. The one bronze fact a Run needs, the dataset anchor date, is copied into the review record (`review.dataset`) by the `route_claims` task, which runs as the job's run-as user. A fresh environment must run that task once before Briefs can be prepared on demand.

Grant nothing on `ptm_bronze` or `ptm_silver` to analysts. Genie is not hard-limited to its attached tables, so Unity Catalog entitlement is the real boundary that keeps source history out of reach ([`genie-curation.md`](./genie-curation.md) §1). Users also need `CAN_RUN` on the Genie space and `CAN_USE` on the warehouse.

**To remove a person's access, revoke `USE SCHEMA`.** A `SELECT` revoke has no effect on a principal that owns the tables, which is the case for whoever deployed the pipeline in a single-identity workspace. In a shared environment the pipeline should run as a service principal so that no person owns the gold tables.

## Lakebase constraints

- **`databricks bundle destroy` soft-deletes the Lakebase project for seven days**, and the project id cannot be reused in that window. A redeploy during it fails on the id collision. Never destroy the bundle in an environment people depend on, and never as a way to reset state.
- **Free Edition allows one Lakebase project per account.** If the account already has one, it must be deleted before this bundle can create its own. The bundle cannot adopt an existing project.
- **Free Edition limits concurrent compute on non-default branches**, so Runs are strictly sequential: one Working Branch alive at a time. The runner enforces this with a process lock.
- **Scale-to-zero drops idle connections.** The review store reconnects on demand, so the first request after an idle period is slower.

## What gets uploaded

The bundle's `sync` block uploads only the runtime set. Tests, docs other than the diagrams (these guides included), the Genie authoring scripts, and the verification suites stay out of the workspace, because workspace files are readable by anyone with workspace access. Keep it that way when adding directories.
