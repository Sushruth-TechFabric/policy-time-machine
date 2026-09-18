# Operations guide

How Policy Time Machine runs day to day, how to tell whether it is healthy, and what to do when it is not. Deployment and configuration are in [`deployment.md`](./deployment.md).

## What runs, and when

| Component | Trigger | Healthy when |
|---|---|---|
| `policy_time_machine_regeneration` job | Daily, 09:00 UTC, one concurrent run | All six tasks succeed, and the `build_briefs` log reports completed Runs |
| Lakeflow pipeline | Task 4 of the job, full refresh | Every expectation passes |
| Databricks App | Always on | `GET /api/health` returns 200, and a signed-in user with grants gets answers |
| Review agent | On demand from the app, and nightly from `build_briefs` | Runs complete, and no Working Branch outlives its Run |

The job's tasks, in order:

| Task | Does | Fails when |
|---|---|---|
| `generate` | Regenerates the reference dataset at today's UTC date | Generator error |
| `validate` | Checks realised effect sizes, category ranking, band population and scenario sizes against their declared values | Any drift beyond ±15% relative, or a changed ranking |
| `load_source_tables` | Replaces the ten `ptm_bronze` tables, and `claim_fraud_truth` in `ptm_eval` | Load error |
| `refresh_pipeline` | Full refresh into `ptm_silver` and `ptm_gold` | Any expectation violated |
| `route_claims` | Applies the Routing Rule and records Routed Claims | Warehouse or Lakebase error |
| `build_briefs` | Runs the agent over undisposed Routed Claims with no Brief, newest first, up to `REVIEW_NIGHTLY_CAP` | **Never.** A failed Run is re-queued and reported in the task log, and the task still exits 0 |

Because `build_briefs` always exits 0, a green job does not prove Briefs were built. Read its log line:

```
[build_briefs] 18/20 Runs completed
```

### Staleness budget

The reference dataset guarantees material changes and claims through 120 days before its anchor date ([ADR-0006](./adr/0006-dataset-is-anchored-to-generation-date.md)). Questions that use "recent" stay answerable for roughly 119 days after the last successful regeneration, so a missed nightly run is not an incident. A week of missed runs is worth a look. The Routing Rule measures "recent" from the dataset anchor, so the review queue is stable between regenerations.

## Release gate

Run before every release to a shared environment, in this order ([spec 08](./specs/08-test-strategy.md) §7):

1. Regenerate the dataset: `databricks bundle run policy_time_machine_regeneration`
2. Generator validation passes. This is the job's `validate` task
3. The pipeline runs with all expectations green
4. Chip execution passes: `app/.venv/bin/python -m ci.genie.run_chips`
5. The query contract suite passes three of three on all fifteen: `app/.venv/bin/python -m ci.genie.run_contracts`
6. The branch smoke test and the Brief contract pass:
   ```bash
   LAKEBASE_PROJECT_ID=policy-time-machine app/.venv/bin/python -m ci.review.smoke_branch
   LAKEBASE_PROJECT_ID=policy-time-machine app/.venv/bin/python -m ci.review.run_brief_contract
   ```

The contract suites also run after any change to Genie instructions, Unity Catalog comments or gold schemas. **Never retry a contract until it goes green.** Zero of three is a deterministic break. One or two of three is instruction ambiguity, which carries equal severity. Results land in `ci/genie/results/` and `ci/review/results/`.

Before a live demonstration ([spec 13](./specs/13-meetup-demo-specification.md)), steps 1 to 6 and the rehearsal must use the same dataset, with no regeneration in between.

## Observability

| Signal | Where |
|---|---|
| Job and task status, task logs | Workflows run page |
| Expectation pass and fail counts | The pipeline's event log and graph |
| What the agent did in a Run: steps, tool calls, model turns | MLflow experiment `/Shared/policy-time-machine-review` (carrying the `[dev <user>]` prefix in the development target). This is the durable audit record, because the step log dies with the Working Branch ([ADR-0017](./adr/0017-agent-runs-on-a-disposable-lakebase-branch.md)) |
| Run outcome, Brief, Disposition | Lakebase `review` database: `run`, `brief`, `disposition` |
| Live Working Branches | The Lakebase project's branches page. At rest, only `production` should exist |
| App logs | The app's Logs tab in the workspace |

Alerting is not configured yet. See [`roadmap.md`](./roadmap.md).

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Every panel shows "You don't have access to the policy data" | The viewer lacks `USE SCHEMA` or `SELECT` on `ptm_gold`. This is Unity Catalog working as designed | Grant access, per [`deployment.md`](./deployment.md#one-time-grants) |
| Timeline works, Genie answers fail for everyone | App service principal lacks `CAN_RUN` on the Genie space, the space id is wrong, or the user has not accepted the consent prompt | Re-apply the grant and check `GENIE_SPACE_ID` |
| A Review Run fails with "Genie could not answer the frequency question" while Investigate works | The app service principal lacks `EXECUTE` on `ptm_gold`, so Genie cannot load the space's certified-answer functions. Investigate runs as the viewer; Runs run as the app | Grant `EXECUTE` on the schema to the service principal, per [`deployment.md`](./deployment.md#one-time-grants) |
| A Review Run fails at once with "the dataset anchor date is not in the review record yet" | `route_claims` has never run against this Lakebase project, so `review.dataset` is empty | Run it: `databricks bundle run policy_time_machine_regeneration --only route_claims` |
| "Genie is not configured" | `GENIE_SPACE_ID` is unset in that process | Set it. See known issue below for the nightly job |
| Every Run fails at the first model step | `REVIEW_MODEL_ENDPOINT` names a disabled or absent endpoint | List endpoints, pick an enabled pay-per-token chat endpoint, redeploy |
| Runs queue behind each other | By design, one Working Branch at a time | None. Raise only if the workspace tier allows concurrent branch compute |
| A `run-…` branch is still present long after a Run | Deletion failed. The branch expires by itself after `REVIEW_BRANCH_TTL_SECONDS` | Delete it by hand if it blocks new Runs, and check the app log for the deletion error |
| First review request after idle is slow | Lakebase scaled to zero and dropped the connection | None. The store reconnects |
| `validate` fails after a generator change | Realised effect sizes moved outside tolerance | Treat as a real failure. Fix the generator or deliberately re-declare the parameter in spec 01 §8, never widen the tolerance |
| `bundle deploy` fails on a Lakebase id collision | The project was destroyed within the last seven days | Wait out the soft-delete window. Do not use `bundle destroy` to reset state |
| A contract passes one or two runs of three | Instruction ambiguity in the Genie space | Fix the instruction or the column comment, then re-run. Do not retry to green |

## Known issues

- **The nightly `build_briefs` task does not receive `GENIE_SPACE_ID`.** The job passes four parameters to the task and the Genie space id is not among them, so in the job process Genie reports "not configured" and each Run fails at the frequency step. The task still exits 0. Briefs requested from the app are unaffected. Fix: pass the id as a job parameter and add it to the task's parameter map, then confirm from the task log. Verify this against a live job run before relying on nightly Briefs.

## Routine procedures

**Give a person access.** Add them to the group that holds the gold-schema grants, Genie `CAN_RUN` and warehouse `CAN_USE`.

**Remove a person's access.** Remove them from the group, or revoke `USE SCHEMA` on `ptm_gold`. The app reflects it on their next request.

**Change the Genie space.** Edit `genie/build_space.py`, render, review the diff, `update <SPACE_ID>`, then run chips and contracts.

**Change the agent's model.** Set the `review_model_endpoint` bundle variable, deploy, run the Brief contract.

**Roll back the app.** From the previous good commit, build the frontend, `databricks bundle deploy`, then `databricks bundle run policy_time_machine_app`. The deploy alone uploads the code without rolling it out. The review record in Lakebase is unaffected by an app redeploy.
