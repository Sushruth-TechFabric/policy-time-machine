# Development guide

Everything needed to work on Policy Time Machine locally. For deploying to a workspace, see [`deployment.md`](./deployment.md).

## Prerequisites

- Python 3.12
- Node 20 or later
- The Databricks CLI, authenticated with a profile that can reach the development workspace. Only the live suites and running the backend against real data need this. Every unit test runs offline.

## Environments per component

Each Python component keeps its own virtual environment so its dependencies stay honest.

```bash
# From the repo root. Each line runs in a subshell, so the working directory does not move.

# App backend (also runs the generator tests, the Genie authoring script and the live suites)
(cd app && python -m venv .venv && .venv/bin/pip install -r requirements.txt -r ../generator/requirements.txt)

# Pipeline rules: pandas and pytest only, no Spark
(cd pipeline && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt)

# Frontend
(cd app/frontend && npm install)
```

## Running the tests

| Suite | Command, from the repo root | Covers |
|---|---|---|
| Generator | `app/.venv/bin/python -m pytest generator/tests` | Determinism, anchoring, scenario populations, identifier reservation |
| Pipeline | `cd pipeline && .venv/bin/python -m pytest` | Every transformation rule, the expectations catalogue, Unity Catalog comments |
| Backend | `cd app && .venv/bin/python -m pytest backend/tests` | Routes, access handling, timeline independence, the review harness, store and runner |
| Frontend | `cd app/frontend && npm test` | Hooks, views, the Review view, no-access mirroring |
| Frontend lint | `cd app/frontend && npm run lint` | Oxlint |
| Diagrams | `bash ci/render-diagrams.sh` | Every Mermaid source renders and is embedded verbatim in a spec |

All of these run without a workspace. Run the suites for whatever you touched before opening a pull request.

## Running the app locally

The backend runs against the development workspace using your CLI profile. Without the forwarded user token that Databricks Apps supplies, it falls back to your own identity, which is what you want locally.

```bash
# Terminal 1: backend on :8000
cd app
export GENIE_SPACE_ID=<genie space id>          # unset: Genie calls return a structured error, the rest still works
export DATABRICKS_WAREHOUSE_ID=<warehouse id>
export LAKEBASE_PROJECT_ID=policy-time-machine   # unset: the review record falls back to in-memory
export REVIEW_MODEL_ENDPOINT=databricks-gpt-oss-120b   # the code default is an endpoint the development workspace does not have
.venv/bin/uvicorn backend.main:app --reload --port 8000

# Terminal 2: frontend on :5173, proxying /api to :8000
cd app/frontend
npm run dev
```

Configuration is read once from the environment in `app/backend/config.py`. The full list of variables is in [`deployment.md`](./deployment.md#configuration).

## Generating the reference dataset locally

```bash
app/.venv/bin/python -m generator --seed 42 --anchor-date 2026-01-01 --out data/raw
```

The seed owns identities and stories. The anchor owns dates, and defaults to today. `data/` is ignored by git: regenerate, never commit.

## Working on the pipeline

Put rules in `pipeline/transformations.py` as plain functions and test them in `pipeline/tests/`. Put invariants in `pipeline/expectations.py`. `pipeline/dlt_pipeline.py` should stay free of logic: it reads, calls the builders, and attaches expectations. A rule that matters gets an expectation, not only a test, because the expectation is what protects production data.

If a change adds or renames a gold column:

1. Update [`specs/02-semantic-layer.md`](./specs/02-semantic-layer.md) and the comment in `pipeline/uc_comments.py`.
2. Check `genie/build_space.py` and `app/backend/chips.json` for references.
3. Re-run the chip and contract suites after deploying.

## Working on the Genie space

The space is authored once, in `genie/build_space.py`. It imports the vocabulary rules from `pipeline/transformations.py`, so it needs an environment with pandas. The app backend's has it.

```bash
cd genie
../app/.venv/bin/python build_space.py render             # regenerate instructions.md, examples.sql, functions.sql for review
../app/.venv/bin/python build_space.py show               # print the payload the API will receive
../app/.venv/bin/python build_space.py update <SPACE_ID>  # full replace of an existing space
../app/.venv/bin/python build_space.py create-functions   # register the trusted SQL functions
```

Commit the rendered files with the source change so the diff is reviewable. Any change here triggers the query contracts.

## Live verification suites

These call a real workspace and cost real time and money, so they are not part of every commit. [`operations.md`](./operations.md#release-gate) says when they are required.

```bash
# From the repo root. The Genie suites need only databricks-sdk. The review suites import the
# backend, so they need the app backend's environment, which serves all four.
app/.venv/bin/python -m ci.genie.run_chips                                                      # every offered chip is answerable
app/.venv/bin/python -m ci.genie.run_contracts                                                  # fifteen contracts, three runs each
LAKEBASE_PROJECT_ID=policy-time-machine app/.venv/bin/python -m ci.review.smoke_branch          # Working Branch lifecycle
LAKEBASE_PROJECT_ID=policy-time-machine app/.venv/bin/python -m ci.review.run_brief_contract    # Brief contract, 3/3 plus an injected failure
```

Workspace identifiers for these suites come from the environment, with development defaults in `ci/genie/config.py`. Never retry a contract until it goes green: one or two passes of three is instruction ambiguity, and it is a finding.

## Conventions

- **Vocabulary.** Use the terms in [`../CONTEXT.md`](../CONTEXT.md), including in code identifiers and comments where practical. The banned list in `pipeline/transformations.py` is enforced on user-facing strings.
- **Decisions.** A decision that a future engineer would otherwise have to rediscover gets an ADR in [`adr/`](./adr).
- **Diagrams.** Edit the `.mmd` source, paste the identical source into the spec that embeds it, and re-render the committed SVG: `npx --yes @mermaid-js/mermaid-cli -i docs/diagrams/<name>.mmd -o docs/diagrams/rendered/<name>.svg`. `ci/render-diagrams.sh` only checks that every source renders and is embedded verbatim. It renders into a temporary directory and does not refresh `docs/diagrams/rendered/`.
