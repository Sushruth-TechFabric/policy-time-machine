# Policy Time Machine

An investigation tool for exploring how insurance policies changed over time and how those changes relate to claims, built on Databricks Genie over a curated temporal semantic layer. Start with [`docs/specs/README.md`](./docs/specs/README.md) for the reading order, [`CONTEXT.md`](./CONTEXT.md) for the vocabulary, and [`docs/adr/`](./docs/adr/) for why each decision was made.

## Review agent

The Claim Review Brief agent (decisions: ADR-0017, ADR-0018, ADR-0019 in [`docs/adr/`](./docs/adr/)) runs each review on a disposable Lakebase Working Branch and reads and writes through the Databricks Model Serving endpoint named by `REVIEW_MODEL_ENDPOINT`. A few things a judge or a fresh workspace needs to know before deploying it:

- **Free Edition allows one Lakebase project per account.** If a judge's account already has a project from a previous submission or trial, they must delete it before this bundle can deploy its own — there is no way to point the bundle at an existing project.
- **`databricks bundle destroy` soft-deletes the Lakebase project for seven days**, and the project id cannot be reused during that window. Never destroy the bundle near a demo — a re-deploy in that window will fail on the id collision, not create a fresh project.
- **`REVIEW_MODEL_ENDPOINT` must name an enabled, pay-per-token serving endpoint** (a `databricks-claude-*` foundation model endpoint). Check the workspace's serving page before first deploy; not every `databricks-claude-*` endpoint is enabled on every workspace or edition, and a disabled endpoint fails every Run rather than falling back silently.
- **One-time grants:** the app's service principal needs `CAN_RUN` on the Genie space so the app can call Genie on the user's behalf; the bundle does not grant this (Genie space permissions aren't a bundle resource type), so run it once per workspace after the space exists:

  ```bash
  databricks api patch /api/2.0/permissions/genie/01f1a5808edd1859b78359723b7c5379 --json '{"access_control_list":[{"service_principal_name":"5ee081ba-a745-4666-8ad2-41d3cfc674db","permission_level":"CAN_RUN"}]}'
  ```

### Running the agent's live checks

Two scripts verify the agent against a real workspace rather than fakes. Both need an authenticated `databricks` CLI profile and the bundle already deployed.

```bash
# Branch lifecycle smoke test: create a Working Branch + endpoint, connect,
# SELECT 1, delete both. Fails fast if the Lakebase project is missing or
# the identity lacks CAN MANAGE.
python ci/review/smoke_branch.py

# Brief contract: build a Brief for the demo policy's latest claim three
# times and assert it against the same gold tables the harness reads from,
# plus one run with an injected failure to confirm nothing partial is ever
# promoted. Expect 3/3, run alongside the fifteen Genie contracts
# (ci/genie/run_contracts.py) before any recording.
python ci/review/run_brief_contract.py
```
