# Meetup Demo Specification

Live, 15–20 minutes, technical audience. Product first, then four platform chapters in data-flow order, two minutes for questions. The contest script (spec 07) is untouched; this is its own document.

Rules carried over from spec 07: relative language only; contract phrasings only (spec 05 for Genie, `ci/review/run_brief_contract.py` for the Brief); the evidence panel opens at least twice; never say fraud.

Pre-flight (the day before): regenerate; run `ci/genie/run_contracts.py` (15/15 at 3/3), `ci/review/smoke_branch.py`, `ci/review/run_brief_contract.py` (3/3); set `REVIEW_DEMO_HOLD_SECONDS=20` on the app; ensure one Brief is already built for the demo policy's latest claim and one Routed Claim has none; record the four fallback clips; open the Lakebase branches page, the Workflow run page, the Genie space and a SQL editor in separate tabs; run the governance preflight from spec 07 rule 7 (the revoke there is `USE SCHEMA` on the gold schema, not `SELECT` — the demo user owns the pipeline tables).

## Chapter 0 — The product (3 min)
Beats 3, 4, 5 and 6 of spec 07, verbatim: cohort → timeline → multi-turn → similarity. End on the open timeline.

## Chapter 1 — The lakehouse (4 min)
Cut to the Workflow run page: generate → validate → load → refresh → route_claims → build_briefs. Open the pipeline graph; open one expectation (E18, the vocabulary rule) and say why a rule that lives only in a document drifts. Open `ptm_gold.policy_change_event` in Catalog Explorer and point at `next_claim_id`, `days_to_next_claim_loss`, `change_timing`: relationships are columns; thresholds stay with Genie.

## Chapter 2 — Genie (4 min)
Open the Genie space: the six tables, the instructions, the two trusted SQL functions. Re-ask the cohort question and open the evidence panel. Show `ci/genie/results/` for the last contract run: fifteen contracts, three of three, asserted against planted ground truth, never against SQL text.

## Chapter 3 — The agent and Lakebase (5 min)
Back in the app, click **Prepare a Brief** on the timeline's claim card. The Review view opens with the Run panel: "Working Branch created: run-…". Cut to the Lakebase branches page — the branch is there with its parent and creation time. Back to the app as sections complete; say the line: *the harness decides what happens, the model decides what to ask.* Point at the question the model chose and the shape it had to fit. When the panel says "Working Branch deleted by the harness", cut back to the branches page: gone. Open the Brief: four sections, each with its sentence, rows and SQL; one withheld sentence if the run produced one — say why that is a feature. Record a Disposition. Open the MLflow trace from the run record. Then open the queue and point at the nightly rule-routed claims with Briefs already built.

## Chapter 4 — Governance (2 min)
Spec 07 beat 9, with one substitution: revoke `USE SCHEMA` on the gold schema rather than `SELECT` — the demo user owns the pipeline tables, so revoking `SELECT` has no effect. Then switch to the Review view — the Brief panel is quiet too. Grant back. Line: Unity Catalog governs the source; the Brief mirrors its answer.

## Close (1 min) and questions (2 min)
Name the services: Unity Catalog, Lakeflow declarative pipeline, Workflows, Genie, Databricks Apps, Lakebase with branching, Foundation Model API, MLflow tracing, Asset Bundles.

## Fallbacks
Each chapter has a 30-second clip. Chapter 3's fallback is the pre-built Brief plus the clip of a branch appearing and disappearing. If the Run is slow, keep talking over the Run panel; the demo hold gives twenty seconds to catch the branch on screen.
