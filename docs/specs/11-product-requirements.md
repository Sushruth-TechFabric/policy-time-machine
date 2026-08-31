# Product Requirements

Each requirement carries its verification. A requirement with no way to check it is a wish, and there are none of those here.

`MUST` is binding for MVP. `SHOULD` is expected but is on the cut list in `04-implementation-plan.md` §6.

---

## 1. Investigation

**FR-01** The app MUST accept a free-text question and route it to Genie as a message in the current conversation.
*Verified by:* QC-01 through QC-14.

**FR-02** Every question MUST be sent within one Genie conversation per investigation, so typed follow-ups resolve against carried context.
*Verified by:* QC-15 (two turns, one conversation).

**FR-03** The app MUST offer three to five follow-up chips drawn from a bank keyed to on-screen context, from six contexts: investigation start, timeline open, cohort on screen, pattern view, similarity view, aggregate view.
*Verified by:* chip execution suite.

**FR-04** Every chip MUST be authored as a complete, context-free question with entities interpolated, and MUST return a non-empty, correctly shaped result against the current dataset.
*Verified by:* chip execution suite; empty result is a build failure.

**FR-05** The app MUST render the question chain as a breadcrumb trail. Clicking a node restores the cached view without re-querying Genie and without extending the conversation.
*Verified by:* app test.

**FR-06** A "new investigation" control MUST be permanently visible, and MUST be additionally surfaced after any error, empty result or Genie clarification.
*Verified by:* app test across three mocked failure modes.

## 2. Timeline

**FR-07** When a question contains exactly one policy identifier matching `\bP-\d{5}\b`, the app MUST open that policy's timeline. Two or more identifiers MUST NOT open a timeline.
*Verified by:* app test — one, several, none, unknown.

**FR-08** The timeline MUST render from the app's own parameterised query and MUST NOT block on, or fail with, the Genie call.
*Verified by:* app test with Genie mocked to fail, time out, and return empty.

**FR-09** An unrecognised policy identifier MUST produce an explicit not-found state, never an empty timeline.
*Verified by:* app test.

**FR-10** Changes sharing an `endorsement_id` MUST render as a single card carrying its several deltas.
*Verified by:* app test against a seeded multi-delta endorsement.

**FR-11** The timeline MUST distinguish claims from changes visually, and MUST mark events matching a Noteworthy Pattern with the rule's name.
*Verified by:* app test; vocabulary by expectation E18.

**FR-12** Clicking a policy in the result panel MUST load that policy's timeline.
*Verified by:* app test.

## 3. Results and evidence

**FR-13** Genie results MUST render as a table with an auto-selected chart. There is no result-shape classification and no bespoke renderer.
*Verified by:* app test.

**FR-14** The app MUST show the generated SQL, the row count and Genie's description in a drawer, collapsed by default with a one-line summary.
*Verified by:* app test.

**FR-15** An unrecognised or unrenderable result MUST fall back to a clean table. The user MUST NOT see an error state for a successful query.
*Verified by:* app test.

## 4. Analytical semantics

**FR-16** "Within N days before a claim" MUST be evaluated as `change_timing = 'before_loss' AND days_to_next_claim_loss <= N`. A bare threshold filter is a defect.
*Verified by:* QC-03 negative assertion — the single most important check in the suite.

**FR-17** "High-severity" MUST mean `severity_band IN ('severe','catastrophic')`, never an improvised dollar figure.
*Verified by:* QC-04, QC-06.

**FR-18** "Recent" MUST default to 90 days, MUST be overridden by any user-supplied window, and MUST be computed at query time from stored dates.
*Verified by:* QC-10; expectation E20 forbids a stored day-count.

**FR-19** "Similar" MUST resolve to `policy_similarity` and MUST NOT be computed from raw columns. At most 20 neighbours; a larger request returns 20 with the limit stated.
*Verified by:* QC-11.

**FR-20** Noteworthy patterns MUST come from the six defined rules. Genie MUST NOT invent one.
*Verified by:* QC-14 negative assertion.

**FR-21** Comparison questions MUST return both groups, each with a label, a rate and a sample size. A single-group result is a failure.
*Verified by:* QC-10 negative assertion.

**FR-22** Claim aggregates derived from `policy_change_event` MUST use `COUNT(DISTINCT next_claim_id)`, since several changes share one linked claim.
*Verified by:* QC-05 example SQL; Genie instruction.

## 5. Data

**FR-23** The dataset MUST be synthetic, containing no real data and no personal information.
*Verified by:* generator specification; birth year only, no VINs.

**FR-24** Identifiers MUST derive from the seed alone and MUST be stable across regenerations at any anchor date.
*Verified by:* generator validation.

**FR-25** No identifier other than a policy identifier may match the policy pattern.
*Verified by:* expectation E19 and generator validation.

**FR-26** The dataset MUST contain the six scenario populations and the five control populations at their declared sizes.
*Verified by:* generator validation.

**FR-27** Measured effect sizes MUST fall within ±15% of declared parameters, and the category ranking MUST match the declared ordering exactly.
*Verified by:* generator validation.

**FR-28** No column may store a delta measured against the current date.
*Verified by:* expectation E20, by schema review.

## 6. Language

**FR-29** No user-facing string produced by the system — Genie answer, pattern name, similarity reason, timeline label, interface copy — may contain a term outside the approved vocabulary.
*Verified by:* expectation E18; QC-13 negative assertion.

**FR-30** The product MUST NOT assert that policy changes predict or cause claims. Findings are associational.
*Verified by:* FR-29; disclosure sentence in the demo and writeup.

**FR-31** The product MUST NOT characterise a policyholder. Policies are investigation candidates; people are not described.
*Verified by:* FR-29.

## 7. Non-functional

**NFR-01** The timeline MUST render within 1 second of a policy being selected, independent of Genie.

**NFR-02** Genie responses SHOULD return within 15 seconds; the result panel shows a skeleton state throughout and never a bare spinner.

**NFR-03** The app MUST run on Databricks Apps, bind to `DATABRICKS_APP_PORT`, and keep every file under 10 MB.

**NFR-04** Credentials MUST remain server-side. The browser reaches only the app's own endpoints.

**NFR-05** The whole system — generator job, pipeline, Genie space, app — MUST deploy from a single Asset Bundle into a clean workspace.

**NFR-06** Regeneration at a new anchor MUST preserve every policy's story, changing only its dates.

**NFR-07** The app targets a single desktop viewport. Responsive behaviour is out of scope.

---

## 8. Traceability

| Capability | Requirements | Contracts |
|---|---|---|
| Individual policy history | FR-07 … FR-12 | QC-01, QC-02 |
| Change-before-claim | FR-16, FR-17, FR-22 | QC-03, QC-04, QC-07, QC-08, QC-12 |
| Portfolio patterns | FR-20, FR-21 | QC-05, QC-06, QC-13, QC-14 |
| Similar histories | FR-19 | QC-11 |
| Progressive investigation | FR-01 … FR-06 | QC-15 |
| Product boundaries | FR-29 … FR-31 | E18, QC-13 |
