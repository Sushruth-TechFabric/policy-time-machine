# Policy Time Machine

*Ask what changed, when it changed, and what happened next.*

Policy Time Machine is an investigation workbench for insurance policy history. A claims or operations professional asks a question in plain English, such as "show policies where coverage increased within 30 days before a claim", and gets the answer, the SQL evidence behind it, a policy timeline, and a next question to ask. It runs entirely on Databricks: Genie over a curated temporal semantic layer in Unity Catalog, served by a Databricks App.

It is an investigation tool. It is not a fraud detector, a scoring engine, or an adjudication system, and that boundary is enforced in the pipeline rather than stated in a disclaimer (see the [product charter](./docs/specs/09-product-charter.md) §5).

## What it does

| Capability | What the user gets |
|---|---|
| **Individual policy history** | Every change and claim on one policy, on one dated spine, with changes from the same endorsement grouped as one decision |
| **Change-before-claim** | Cohorts of policies where a material change preceded a claim, at any window the user names |
| **Portfolio patterns** | Which kinds of change most often precede severe claims, always shown against a comparison group with sample sizes |
| **Similar histories** | Policies whose behaviour resembles this one, ranked, with the reasons for each match |
| **Claim review** | A queue of routed claims, an agent-assembled Brief of evidence for each, and a reviewer-recorded Disposition |

Every Genie answer carries its generated SQL, row count and reading. Every investigation query runs as the signed-in user, so Unity Catalog grants are the single point of access control for policy data. Claim review Briefs are prepared under the app's own gold-only identity and shown only to people who hold those same grants.

## How it works

```
Source history ─▶ Lakeflow Declarative Pipeline ─▶ ptm_gold (6 curated tables) ─▶ Genie ─▶ App ─▶ User
   (ptm_bronze)     bronze → silver → gold,            in Unity Catalog                     │
                    20 enforced expectations                                                 ▼
                                                        Claim Review Brief agent ─▶ Lakebase review record
```

The central design decision: temporal **relationships** are computed once in the pipeline as plain columns, and temporal **thresholds** stay with Genie as filter literals. "Within 30 days before a claim" becomes `days_to_next_claim_loss <= 30`. Genie never writes a lookahead join, which is the SQL text-to-SQL gets silently wrong ([ADR-0002](./docs/adr/0002-genie-sees-four-flat-tables-with-precomputed-relationships.md)).

Read [`docs/architecture.md`](./docs/architecture.md) for the full picture.

## Repository layout

| Path | Contents |
|---|---|
| [`app/`](./app) | The Databricks App: FastAPI backend (`backend/`), React frontend (`frontend/`), and the review agent (`backend/review/`) |
| [`pipeline/`](./pipeline) | Lakeflow Declarative Pipeline: transformations, the expectations catalogue, Unity Catalog comments |
| [`generator/`](./generator) | Seeded, anchor-parameterised reference dataset generator and its validation |
| [`genie/`](./genie) | The Genie space as code: instructions, example SQL, trusted SQL functions |
| [`workflow/`](./workflow) | Workflows tasks: generate, validate, load, route claims, build Briefs |
| [`ci/`](./ci) | Live verification suites: Genie query contracts, chip execution, Brief contract, Lakebase branch smoke test |
| [`docs/`](./docs) | Architecture, guides, specifications, decision records, diagrams |
| [`databricks.yml`](./databricks.yml) | The Asset Bundle: app, pipeline, job, Lakebase resources, MLflow experiment |
| [`CONTEXT.md`](./CONTEXT.md) | The glossary. Every document and every user-facing string uses this vocabulary |

## Quick start

Prerequisites: Python 3.12, Node 20 or later, and the Databricks CLI authenticated against a workspace with Unity Catalog, Genie, Databricks Apps and Lakebase enabled.

```bash
# Run every local test suite (no workspace needed)
cd app && python -m venv .venv && .venv/bin/pip install -r requirements.txt -r ../generator/requirements.txt && cd ..
app/.venv/bin/python -m pytest generator/tests
(cd app && .venv/bin/python -m pytest backend/tests)
(cd pipeline && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest)
(cd app/frontend && npm install && npm test)

# Build the frontend and deploy the bundle
(cd app/frontend && npm run build)
databricks bundle validate
databricks bundle deploy
databricks bundle run policy_time_machine_app            # roll the uploaded code out to the app
databricks bundle run policy_time_machine_regeneration   # load data and build the gold tables
```

[`docs/development.md`](./docs/development.md) covers local development in detail. [`docs/deployment.md`](./docs/deployment.md) covers environments, one-time grants and configuration.

## Documentation

| If you want to | Read |
|---|---|
| Understand the product and who it serves | [`docs/specs/09-product-charter.md`](./docs/specs/09-product-charter.md), then the [specs reading order](./docs/specs/README.md) |
| Learn the vocabulary | [`CONTEXT.md`](./CONTEXT.md) |
| Understand the system | [`docs/architecture.md`](./docs/architecture.md) |
| Set up and develop locally | [`docs/development.md`](./docs/development.md) |
| Deploy to a workspace | [`docs/deployment.md`](./docs/deployment.md) |
| Operate and troubleshoot it | [`docs/operations.md`](./docs/operations.md) |
| See what the first production release requires | [`docs/roadmap.md`](./docs/roadmap.md) |
| Understand why a decision was made | [`docs/adr/`](./docs/adr) |
| Contribute | [`CONTRIBUTING.md`](./CONTRIBUTING.md) |

## Status

All five capabilities are built and verified in the development workspace, against the seeded reference dataset. Onboarding a real policy administration source, and standing up staging and production environments, are the next milestones. [`docs/roadmap.md`](./docs/roadmap.md) tracks both.

## Data disclosure

The reference dataset is synthetic. It contains no real customers and no personal data. Investigation-worthy patterns are deliberately seeded at declared, documented effect sizes, so the product demonstrates how historical patterns are surfaced and investigated, not that policy changes predict claims ([ADR-0014](./docs/adr/0014-the-planted-signal-is-modest-heterogeneous-and-declared.md)).
