# Meetup Demo Specification

Live, 15–20 minutes, technical audience. Product first, then four platform chapters in data-flow order, two minutes for questions.

## Rules

1. **Relative language only** — "nine weeks earlier", never a calendar date — because the dataset regenerates against a moving anchor (ADR-0006).
2. **Contract phrasings only.** Every typed question is the exact phrasing of a passing query contract (spec 05); the Brief is covered by `ci/review/run_brief_contract.py`. Nothing is asked on stage that is not already tested at 3/3. Do not improvise wording.
3. **The evidence panel opens at least twice.** It is the fastest proof that the semantics are real rather than narrated.
4. **Never say fraud.** Not once, not casually, not as a joke about what the tool doesn't do. The approved vocabulary governs the presenter as strictly as it governs the UI.
5. **The thread is linear.** Trail clicks are cached scroll-backs, never a rewind of the Genie conversation — so never phrase a follow-up as though an earlier turn were the latest one (ADR-0011).
6. **Regenerate, then rehearse.** Every beat depends on planted scenarios; run the contract suites after regeneration and before rehearsal, and present against that same dataset (spec 08 §7).
7. **Only say numbers that are on screen.**

## Pre-flight (the day before)

Regenerate; run `ci/genie/run_contracts.py` (15/15 at 3/3), `ci/review/smoke_branch.py`, `ci/review/run_brief_contract.py` (3/3); set `REVIEW_DEMO_HOLD_SECONDS=20` on the app; ensure one Brief is already built for the demo policy's latest claim and one Routed Claim has none; record the four fallback clips; open the Lakebase branches page, the Workflow run page, the Genie space and a SQL editor in separate tabs.

Governance pre-flight: open the app once as the presenting user so the one-time user-authorization consent prompt is accepted off stage. Put the two statements ready in the SQL editor — `REVOKE USE SCHEMA` and `GRANT USE SCHEMA` on the gold schema for the presenting user. It is `USE SCHEMA`, not `SELECT`: the presenting user owns the pipeline tables, so revoking `SELECT` has no effect. Rehearse the revoke and confirm a direct `SELECT` actually fails before the talk.

## Opening (30s)

State the problem before the product, then the disclosure up front rather than under questioning (ADR-0014):

> The dataset is synthetic — no real data, no PII. Investigation-worthy patterns are deliberately seeded at declared, documented effect sizes — this demonstrates how historical patterns are surfaced and investigated, not that policy changes predict claims.

## Chapter 0 — The product (3 min)

**The cohort.** Type: **"Show policies where coverage increased within 30 days before a claim."** (QC-03) When the result lands, expand the evidence panel — *Evidence: N rows · view query* — and leave it open for three seconds.

> Genie wrote that SQL. Note what it didn't have to write — no window function, no effective-date join. The temporal relationship is already a column in the semantic layer, so the question is a filter. Every answer carries its evidence: the generated SQL, how the question was read, and the row count.

**The timeline.** Click the top result. Note in passing that the timeline is the app's own deterministic query — it renders instantly and never waits on Genie. Walk the spine top to bottom and point at an endorsement-grouped card.

> Those two happened in one endorsement — one customer interaction, two field changes. We count it as one decision, which is why "three material changes in a month" means something here.

Then the second axis: the claim's severity band, and separately how close it sits to a recently raised limit — a different finding from a large claim on a large limit. Pattern markers get one sentence: each names a documented rule that fired — a Noteworthy Pattern, never a score.

**Multi-turn.** Type, without repeating context: **"which of these had a claim near the new limit?"** (QC-15, turn two) The new turn appends below the first and the cohort narrows. This is the single moment that proves Genie is holding conversation state (ADR-0011), and it has its own contract.

**Similarity.** Click **Find similar policies →** on the timeline itself. Neighbours return ranked, with `top_reasons` visible.

> Similar means the behaviour matched — change velocity, category mix, which patterns fired. Not that they live in the same city. And it tells you why each one matched, which an embedding could not.

End on the open timeline.

## Chapter 1 — The lakehouse (4 min)
Cut to the Workflow run page: generate → validate → load → refresh → route_claims → build_briefs. Open the pipeline graph; open one expectation (E18, the vocabulary rule) and say why a rule that lives only in a document drifts. Open `ptm_gold.policy_change_event` in Catalog Explorer and point at `next_claim_id`, `days_to_next_claim_loss`, `change_timing`: relationships are columns; thresholds stay with Genie.

## Chapter 2 — Genie (4 min)
Open the Genie space: the six tables, the instructions, the two trusted SQL functions. Re-ask the cohort question and open the evidence panel. Show `ci/genie/results/` for the last contract run: fifteen contracts, three of three, asserted against planted ground truth, never against SQL text.

## Chapter 3 — The agent and Lakebase (5 min)
Back in the app, click **Prepare a Brief** on the timeline's claim card. The Review view opens with the Run panel: "Working Branch created: run-…". Cut to the Lakebase branches page — the branch is there with its parent and creation time. Back to the app as sections complete; say the line: *the harness decides what happens, the model decides what to ask.* Point at the question the model chose and the shape it had to fit. When the panel says "Working Branch deleted by the harness", cut back to the branches page: gone. Open the Brief: four sections, each with its sentence, rows and SQL; one withheld sentence if the run produced one — say why that is a feature. Record a Disposition. Open the MLflow trace from the run record. Then open the queue and point at the nightly rule-routed claims with Briefs already built.

## Chapter 4 — Governance (2 min)
In the SQL editor tab, run the prepared `REVOKE USE SCHEMA`. Switch back to the app and refresh. Ask one question; open the timeline.

> Same screen, same questions — no data. The app asks Genie and the warehouse **as you**, and Unity Catalog just said no. Access isn't an app feature that can drift out of sync with governance; it *is* governance. Revoke a grant and every path — answers, timelines, evidence — goes quiet together.

Then switch to the Review view — the Brief panel is quiet too. Run the prepared `GRANT USE SCHEMA`, refresh, ask the same question — results return. Keep the SQL editor visible for both statements; the enforcement being outside the app is the point. Line: Unity Catalog governs the source; the Brief mirrors its answer. **After the talk, confirm the grant ran.**

## Close (1 min) and questions (2 min)
Name the services: Unity Catalog, Lakeflow declarative pipeline, Workflows, Genie, Databricks Apps, Lakebase with branching, Foundation Model API, MLflow tracing, Asset Bundles.

## Fallbacks
Each chapter has a 30-second clip. Chapter 3's fallback is the pre-built Brief plus the clip of a branch appearing and disappearing. If the Run is slow, keep talking over the Run panel; the demo hold gives twenty seconds to catch the branch on screen. If Genie is slow or fails, the timeline still renders — it never blocks on Genie, and the working card shows the product handling the wait honestly. A visible retry is better than hiding how the product behaves.
