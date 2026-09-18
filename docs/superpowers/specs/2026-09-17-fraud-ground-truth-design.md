# Fraud Ground Truth and the Detector Surface — Design

Date: 2026-09-17
Status: design approved in brainstorming session, 2026-09-17; awaiting spec review
Sub-project: A of four (see §2)

Vocabulary is `CONTEXT.md`. Decisions with their alternatives will be recorded as ADR-0020 and ADR-0021. This document states *what* gets built.

## 1. Problem

The product is to gain a fraud detector agent. Three things stand in the way today.

1. **The charter forbids it.** `docs/specs/09-product-charter.md` says "Not a fraud detection engine. Not a fraud score", and the boundary is enforced in code: `BANNED_VOCABULARY` is checked as pipeline expectation E18, by the Claim Review Brief harness on every sentence, and by Genie contract QC-13.
2. **There is nothing to detect.** The dataset labels policies as noteworthy (S1–S6) or control (C1–C5). It has no notion of fraud. The six pattern rules already find S1–S6 deterministically, so a detector measured against those labels can only re-find what the pipeline computes.
3. **There is nothing to investigate.** A claim carries a coverage line, two dates, an amount and a status. Every other claim column is derived from policy changes. An investigating agent has no evidence to weigh that the rules have not already weighed.

This sub-project removes all three: it revises the boundary, plants a hidden fraud truth, and plants the evidence a good investigator could find. It builds no detector.

## 2. Programme context

The fraud detector is delivered as four sub-projects, each with its own spec, plan and implementation cycle.

| # | Sub-project | Delivers | Depends on |
|---|---|---|---|
| **A** | Charter revision and fraud ground truth (this document) | Scoped vocabulary rule, hidden fraud truth, planted evidence, validation | — |
| B | Decider and evaluation bench | A `Decider` interface with two implementations (Jev from TypeSafe; a Databricks serving endpoint returning the same schema) and an offline bench over the labelled claims: precision, recall, reliability curve, against the baselines declared in §6 | A |
| C | Book sweep and routing | A Workflow task scoring every claim with the Decider; a ranked queue in Lakebase | B |
| D | Investigator agent, case file, Review UI | The harness extended to a budgeted investigation, a Case File, a final Verdict over the evidence, shown beside the human Disposition | B |

Decisions already taken for the programme, recorded here so later specs inherit them:

- The detector's output is a **Verdict with a Case File** per claim (likely fraud / unclear / likely benign, with a calibrated probability, the evidence relied on, and the benign explanation considered). The human still records the Disposition.
- **Jev** (TypeSafe's System One model: unstructured state in, typed value with a calibrated probability out) plays two roles: the whole-book sweep and the final Verdict. It does not investigate; the harness agent on Databricks Model Serving does.
- Jev sits behind a `Decider` interface with a Databricks-endpoint implementation beside it. Jev is used in the dev workspace on synthetic data only. Whether policyholder data may leave the Unity Catalog boundary is a separate production decision; until it is made, the Databricks-endpoint Decider is the production default.
- Vendor claims about calibration are verified on the planted truth, not assumed.

## 3. What gets built

1. **Charter revision** — ADR-0020, the rewritten boundary paragraph, two named surfaces in `CONTEXT.md`.
2. **Scoped vocabulary rule** — the banned list split in two, a `surface` parameter defaulting to today's behaviour, a drift test over all three copies.
3. **Fraud Truth** — `ptm_eval.claim_fraud_truth`, drawn conditional on existing behaviour from a new RNG stream.
4. **Claim notes** — a new source table `claim_note`, templated from seeded phrase pools with declared, overlapping tells.
5. **`ptm_gold.claim_context`** — one new gold table carrying behaviour facts and the note, not attached to the Genie space.
6. **Validation** — new generator checks run by the existing `validate_task`, a truth-isolation repo test, pipeline expectations.

## 4. Charter revision and the scoped vocabulary

### 4.1 Decision record

ADR-0020, "Fraud detection lives on a fenced detector surface", supersedes the boundary paragraph of the charter. The rewritten charter says: the product investigates policy history *and* estimates the probability that a claim is fraudulent. It is still not underwriting, pricing or adjudication. The human Disposition remains the only decision on record.

Unchanged:

- ADR-0009: Noteworthy Patterns are named rules, never scores.
- ADR-0018: the Brief restates facts and never weighs them. The Verdict is a separate artefact, not a fifth Brief section.
- ADR-0014: associational language. "Predicts", "causes" and "leads to" stay banned on every surface. The detector estimates a probability about one claim; it makes no causal statement about policy changes.

### 4.2 Two surfaces (`CONTEXT.md`)

- **Investigation surface** — Genie answers, pattern names, similarity reasons, timeline labels, Brief sentences, and the interface copy around them. Today's vocabulary rule applies unchanged.
- **Detector surface** — the Sweep Score, the Verdict, the Case File, and the panel that shows them. May name fraud, always about a claim and always alongside a probability.

A new "Detection" glossary section defines:

- **Fraud Truth** — the generator's hidden per-claim label. Exists for evaluation only; no product surface and no agent ever reads it.
- **Sweep Score** — the Decider's fraud probability for a claim, computed from the claim's context alone, used to rank the queue.
- **Verdict** — the Decider's typed outcome for a claim after investigation, with a calibrated probability.
- **Case File** — the evidence the investigator assembled for one Verdict, including the benign explanation it considered.

Existing `_Avoid_` lines stay, qualified "on the investigation surface".

### 4.3 Code

In `pipeline/transformations.py`:

```python
ACCUSATORY_TERMS = ("fraud", "fraudulent", "suspicious", "scheme", "deceptive",
                    "risk score", "anomaly", "anomalous", "red flag")
ALWAYS_BANNED    = ("guilty", "predicts", "causes", "leads to", "increases the risk of")
BANNED_VOCABULARY = ACCUSATORY_TERMS + ALWAYS_BANNED   # same members as today

def vocabulary_violations(text, surface="investigation"): ...
```

- `surface="investigation"` (the default) applies `BANNED_VOCABULARY`. Every existing caller — E18, the Brief sentence check, QC-13 — behaves identically.
- `surface="detector"` applies `ALWAYS_BANNED` plus a person-subject rule: a detector string is a violation if it contains a customer's name, or if a person noun (`policyholder`, `customer`, `insured`, `claimant`, `driver`) is the grammatical subject of an accusatory term. The rule is implemented as a small fixed set of regular expressions (`<person noun> (is|was|has|committed|staged|lied|faked) ...` and `<accusatory adjective> <person noun>`), not as language understanding. It catches the obvious forms; the convention carries the rest.
- `app/backend/review/vocabulary.py` mirrors the split and the parameter.

Nothing calls `surface="detector"` until sub-project D. Every output that exists after this sub-project is investigation-surface, including claim notes.

### 4.4 Drift fix

The banned list exists in three copies: `pipeline/transformations.py`, `app/backend/review/vocabulary.py`, `ci/genie/ground_truth.py`. The third already lacks `anomaly`, `anomalous`, `red flag`. It is brought into line, and the existing equality test is extended to assert all three are identical.

## 5. Fraud Truth and the planted evidence

### 5.1 Constraint

Every existing source table must stay byte-identical for a given seed and anchor, so that the fifteen Genie contracts and the ADR-0014 calibration checks are undisturbed. The generator draws from named RNG streams (`generator/build.py`, `_stream_seed(name)`), so new streams add data without shifting any existing draw.

Consequence: behaviour facts (tenure, prior claims, reinstatement) derive from existing tables and cannot be generated conditional on a fraud label. The direction is reversed: **the label is drawn conditional on the behaviour that already exists.** The planted correlation is the same; no existing row changes.

### 5.2 Fraud Truth

Table `ptm_eval.claim_fraud_truth` (`claim_id` string PK, `is_fraud` boolean). Seed-owned; drawn from a new `fraud` RNG stream after all existing generation is complete. One row per claim.

Each claim's fraud probability is a declared base rate for its population, tilted by declared odds ratios on its behaviour flags, then renormalised so the population's expected rate equals the base rate.

| Population | Claims (approx.) | Base rate | Expected fraud claims |
|---|---|---|---|
| S1–S6 planted claims | 185 | 65% | ~120 |
| C1–C5 claims | 170 | 0% | 0 |
| Background claims | ~5,150 | 1% | ~50 |

Overall prevalence is about 3%. About 30% of fraud matches no pattern rule, so rules alone miss it. About 35% of rule-matched S claims are benign, so rules alone over-refer. Inside the rule-matched group the rules cannot separate fraud from benign at all.

Behaviour flags and their declared odds ratios (modest and heterogeneous, as ADR-0014 requires of every planted effect):

| Flag | Definition | Declared odds ratio |
|---|---|---|
| Early tenure | Loss Date within 90 days of policy inception | 3.0 |
| Repeat claimant | two or more prior claims on the policy | 2.0 |
| Recent reinstatement | policy reinstated within 30 days before the Loss Date | 2.5 |
| New vehicle | a vehicle added within 30 days before the Loss Date | 1.5 |

Final values are fixed in `docs/specs/01-data-model-and-synthetic-data.md` §9, which is the source of truth; the figures above are the design's starting point.

**Verification before the numbers are fixed (first task of the plan):** measure the variance of each flag inside S1–S6. Those policies are scripted, so a flag may be near-constant there. For any flag whose minority class is below 10% of S claims, the S-population tilt for that flag is dropped. If every flag is dropped, S fraud is drawn at the flat 65% and the narrative is the only separating signal inside the rule-matched group. The background population keeps all four tilts regardless.

### 5.3 Claim notes

New source table `claim_note` (`claim_id` string PK/FK, `note_text` string). One first-notice note per claim, assembled from seeded phrase pools on a new `fraud_notes` RNG stream, conditional on `is_fraud`.

A note has five slots: what happened (pool chosen by Coverage Line), where, police report, witnesses, damage description. Each slot has an ordinary variant and a tell variant.

| Tell | P(tell given fraud) | P(tell given benign) |
|---|---|---|
| Vague location | 55% | 15% |
| No police report where one is expected (collision, theft) | 60% | 25% |
| No witnesses, late night | 45% | 15% |
| Damage description inconsistent with the claimed Coverage Line | 25% | 2% |

Tells are drawn independently. No single tell decides a claim, and about one fraud note in six carries none.

Rules for the pools:

- Pools are static constants in `generator/`, reviewed and committed. Generation makes no model call and is byte-stable for a seed.
- Every phrase appears in notes of both classes, so a phrase lookup leaks nothing; only tell *rates* differ.
- No phrase contains a banned term, a policy-id lookalike (`P-\d{5}`), or a customer name.
- Notes use relative wording for time ("two days ago", "last night"), never absolute dates, so a changed anchor does not change a note (determinism obligation 3).

### 5.4 Gold table `ptm_gold.claim_context`

| Column | Type | Meaning |
|---|---|---|
| `claim_id` | string PK | |
| `policy_age_at_loss_days` | int | Loss Date minus policy inception |
| `prior_claims_count` | int | claims on the policy with an earlier Report Date |
| `days_since_prior_claim` | int, nullable | Loss Date minus the previous claim's Loss Date |
| `reinstated_within_30d_before_loss` | boolean | |
| `vehicle_added_within_30d_before_loss` | boolean | |
| `note_text` | string | from `claim_note` |

A separate table rather than new columns on `claim_event`: Genie reads `claim_event`, and new columns there could change the SQL it writes and destabilise the contracts. `claim_context` is **not** attached to the Genie space in this sub-project. Attaching it is sub-project D's decision and comes with a full contract re-run.

Built by a new `build_claim_context` in `pipeline/transformations.py`; schema declared in the shared schema registry so the pandas and Spark sides cannot disagree; column comments in `uc_comments.py`.

Expectations (added to `expectations.py` and spec 02). Existing rules extended to the new table: E18 (vocabulary, investigation surface) and E19 (no policy-id lookalike) over `note_text`. New rules: **E21** one row in `claim_context` per row in `claim_event`, and no others; **E22** `note_text` non-null and non-empty; **E23** `prior_claims_count >= 0` and `policy_age_at_loss_days >= 0`.

### 5.5 Truth isolation

`ptm_eval` is a new schema outside the medallion schemas (recorded in ADR-0021, which amends ADR-0016's list). The app service principal already reads `ptm_bronze.generation_manifest`, so bronze is reachable by the agent and cannot hold the truth. The app service principal and the Genie space receive no grant on `ptm_eval`. Only the identity that runs the evaluation bench (sub-project B) reads it.

The Workflow's load step writes `claim_fraud_truth` to `ptm_eval`; the declarative pipeline never reads it.

## 6. Validation

New checks in `generator/validate.py`, run by the existing `validate_task`, so a bad regeneration fails the Workflow.

| Check | Asserts |
|---|---|
| Byte identity | For the test seed and anchor, the hash of every pre-existing source table equals the hash recorded before this change. |
| Declared rates | Realised fraud share in S and in background within tolerance of the declared base rates; exactly zero in C. |
| Tilts | Realised odds ratio for each retained flag within tolerance of its declared value, per population where it applies. |
| Tells | Realised rate of each tell, per class, within tolerance. |
| Separability band | A fixed reference scorer — the sum of the declared log-odds of the tells present and the flags set — reaches an AUC inside a declared band, provisionally 0.80–0.92. Separable, not trivial. |
| Rules-only baseline | Treating "any pattern match on the claim's policy" as the prediction, recall stays below a declared ceiling (off-pattern fraud guarantees misses) and precision below a declared ceiling (benign S and C5 guarantee over-referral). |
| Leakage | Every phrase occurs in both classes; no note contains a banned term or a policy-id lookalike; `is_fraud` is independent of `claim_id` order (rank correlation within tolerance of zero). |

Tolerances are declared beside the parameters in spec 01 §9, sized for the smallest population (S, about 185 claims) so they hold on every seed.

The reference scorer and the rules-only figures are emitted into the validation report. They are the two baselines sub-project B's bench must beat.

## 7. Testing

- **Generator (pytest):** the new checks above on the test seed; a second seed and a second anchor to show the truth and the notes are seed-owned and anchor-independent; the byte-identity hash.
- **Pipeline (pytest, pandas):** `build_claim_context` against hand-built fixtures — first claim on a policy (null `days_since_prior_claim`), reinstatement on day 30 and day 31, vehicle added on the Loss Date.
- **Vocabulary:** `surface="investigation"` returns today's results over the existing fixtures; `surface="detector"` allows "fraud" about a claim, rejects the person-subject forms and a customer name, still rejects `ALWAYS_BANNED`; the three-copy equality test.
- **Truth isolation (repo test):** fails if `claim_fraud_truth`, `ptm_eval` or `is_fraud` appears anywhere under `app/` or `pipeline/`, or in the Genie space definition. The names are permitted only under `generator/`, `workflow/`, `ci/` and `docs/`.
- **Live:** the regeneration Workflow runs green with the new validation; the fifteen Genie contracts remain 3/3 with no change to their assertions.

## 8. Documents touched

- `docs/specs/09-product-charter.md` — boundary paragraph.
- `CONTEXT.md` — two surfaces; Detection glossary section; qualified `_Avoid_` lines.
- `docs/specs/01-data-model-and-synthetic-data.md` — `claim_note` and the truth table in the source model; §9 fraud subsection with every declared parameter and tolerance; §11 vocabulary scope.
- `docs/specs/02-semantic-layer.md` — `claim_context` and its expectations.
- `docs/specs/08-test-strategy.md` — the new validation and isolation rows.
- `docs/adr/0020-fraud-detection-lives-on-a-fenced-detector-surface.md`
- `docs/adr/0021-fraud-truth-is-conditional-on-existing-behaviour-and-held-outside-the-medallion-schemas.md`

## 9. Definition of done

1. Regeneration Workflow green, including every check in §6.
2. Fifteen Genie contracts 3/3, assertions unchanged.
3. Existing generator, pipeline, backend and frontend suites green.
4. Validation report shows the reference-scorer AUC and the rules-only precision and recall.

## 10. Out of scope

The Decider and Jev; the book sweep; the investigator agent; any UI; attaching `claim_context` to the Genie space; shared third parties and claim-handling signals (a later ring-detection project); any change to S/C scenario ids, sizes or existing source rows.
