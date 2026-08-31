# Query Contracts

The fourteen core questions, each with an assertion that does not depend on the SQL Genie writes. Ground truth comes from the scenario catalogue in `01-data-model-and-synthetic-data.md` §9 (ADR-0015).

---

## 1. Contract types

| Type | Asserts |
|---|---|
| **Cohort** | A must-include set of policies (or events) is present, a must-exclude set is absent, and stated column values never appear |
| **Ranking** | The returned ordering of categories matches the declared effect-size ordering. Never magnitudes — those belong to generator validation |
| **Comparison** | Exactly two groups are present, each with a label, a rate and an `n` |
| **Table-routed** | The result matches a pre-computed table exactly |

Cohort membership is compared on `DISTINCT policy_id`, so a change-grain result with repeated policy ids evaluates correctly. No contract asserts cardinality: the background population legitimately contains organic matches beyond the planted ones.

## 2. Authoring rule

**Contracts and the scenario catalogue share one source.** Each scenario declares the policy ids it plants and the contracts those ids belong to. A scenario edit that orphans a contract fails the build rather than drifting silently.

## 3. Run policy

Three runs. Three passes is green; anything else is red, and there is no retry. Zero of three is a deterministic break in the semantic layer or the instructions. One or two of three is instruction ambiguity — Genie choosing between readings — and is treated as equally severe, because a live demo cannot tolerate it. Generated SQL and Genie's description are logged on every failing run, never asserted.

---

## 4. The contracts

### QC-01 — "What changed on policy P-18492 during the last year?"
**Cohort.** Must include every planted timeline event for the demo anchor policy within the window: the address change, the `COLL` limit increase, the vehicle change and the collision claim. Must not include events dated before `anchor − 365d`. Result must be ordered by date.

### QC-02 — "What changed before the latest claim on P-18492?"
**Cohort.** Must include the three material changes preceding the planted claim; must exclude every event dated after the claim's loss date. **Negative assertion:** no returned row carries `change_timing = 'after_loss_before_report'` unless the question asked for it.

### QC-03 — "Show policies where coverage increased within 30 days before a claim."
**Cohort.** Must include all 40 S1 policies. Must exclude all C1 (claim with no preceding change) and C2 (changes with no claim) policies. **Negative assertions:** no row has `change_timing = 'after_loss_before_report'`; no row has `change_direction != 'increase'`; no row has `days_to_next_claim_loss > 30`.

This is the contract that guards the critical instruction in ADR-0004. If Genie writes a bare threshold filter, the first negative assertion fails loudly rather than the cohort being quietly wrong.

### QC-04 — "Find policies with several material changes in the 90 days before a high-severity claim."
**Cohort.** Must include all 30 S4 policies. Must exclude C1 and C2. **Negative assertion:** every returned claim severity is `severe` or `catastrophic`.

The window is load-bearing for the same reason as QC-07's: report-date linkage (ADR-0004) legitimately attaches material changes made 255–977 days earlier to a policy's eventual claim, so the unwindowed "must exclude C1" is unsatisfiable by any correct SQL. Within 90 days, no C1 policy has a single qualifying change.

### QC-05 — "Which material changes most often precede high-severity claims, within 60 days?"
**Ranking.** Returned category ordering must match the declared ordering: coverage, deductible, vehicle, status, address. Magnitudes unasserted.

Wording note: this question, QC-06 and QC-13 all measure the same underlying statistic — `COUNT(DISTINCT next_claim_id)` of material changes within a 60-day, `before_loss` window (spec 03 §5) — so the declared ordering can be asserted consistently across all three. What differs between them is the claim population (high-severity band here, a dollar threshold in QC-06, a baseline comparison in QC-13), never the counting method. The question text is deliberately the same phrasing Genie's matching example carries, so the retrieved example and the generated SQL agree on the measure being asked for.

### QC-06 — "Which material changes happen most often, within 60 days, before claims above $25,000?"
**Ranking.** Same ordering assertion, same windowed `COUNT(DISTINCT next_claim_id)` formulation as QC-05 (see note there). **Negative assertion:** no returned claim amount is at or below $25,000.

### QC-07 — "Show policies where deductible decreased within 90 days before a claim."
**Cohort.** Must include all 30 S2 policies. Must exclude C1. **Negative assertions:** every row has `change_category = 'deductible'` and `change_direction = 'decrease'`; no row has a coverage line outside `COLL` and `COMP`, since only those carry deductibles; no row has `days_to_next_claim_loss > 90`.

The 90-day window is load-bearing, not decorative (ADR-0004): under report-date-anchored linkage, C1 policies (high-value claim, no preceding change) legitimately link an old, unrelated deductible decrease (300+ days prior) to the eventual claim, so an unwindowed "must exclude C1" assertion is unsatisfiable against a correct query. 90 days comfortably covers the planted S2 case (~32 days prior) while excluding the far-prior C1 case, making the exclusion assertion satisfiable by a query that follows the two-filter rule rather than by one that additionally, silently, gets the linkage wrong.

### QC-08 — "Which policies changed vehicles and addresses within 60 days?"
**Cohort.** Must include all 35 S5 policies. **Negative assertion:** no row has `ABS(nearest_address_change_offset_days) > 60`. The assertion must pass irrespective of which change came first — the symmetric case is the point of the signed offset.

### QC-09 — "Which customers have the highest number of policy changes?"
**Table-routed.** The returned top ten must match the top ten by `material_change_count` computed directly from `policy_profile`, in order. Ties broken by `customer_id` ascending.

*This question was not assigned a type in the original ruling; classified here as table-routed because the ground truth is computable from a curated table rather than from the scenario catalogue.*

### QC-10 — "Compare policies with recent material changes against policies without."
**Comparison.** Exactly two groups. Each carries a group label, a rate and an `n`. **Negative assertion:** no single-group result passes — a one-row result is a failure regardless of its contents. Both `n` values must exceed the declared minimum group size.

### QC-11 — "Find policies with histories similar to P-18492."
**Table-routed.** The returned neighbours must equal the rows in `policy_similarity` for that policy, in rank order. At most 20 rows. The planted neighbour group must appear at its declared ranks.

### QC-12 — "What happened immediately before the largest claims?"
**Cohort.** Must include the changes preceding the top claims by settled amount. Must include at least one C1 policy — a large claim with no preceding change — because a result implying every large claim has a preceding change is a wrong answer, not a clean one.

### QC-13 — "Are claims more frequent, within 60 days, following specific types of material policy changes?"
**Ranking**, with a comparison element. Category ordering must match the declared ordering, and the result must carry a baseline or comparison figure. Same windowed `COUNT(DISTINCT next_claim_id)` formulation as QC-05/06 (see note under QC-05); the comparison figure is a total baseline claim count, not a magnitude claim. **Negative assertion:** returned prose and labels contain no term from the banned vocabulary list — this question is the one most likely to elicit causal language.

### QC-14 — "Show unusual historical patterns worth investigating."
**Table-routed.** Pattern counts must equal the deterministic planted counts in `policy_pattern_match` exactly. **Negative assertion:** every `pattern_name` returned is one of the six defined codes — Genie must not invent a pattern.

### QC-15 — Multi-turn: "…which of these had a claim near the new limit?"
**Cohort, two turns in one conversation.** Turn one is QC-03. Turn two asserts the returned set is a subset of turn one's, and includes the S6 policies. Failure here means multi-turn context is not resolving — the single capability the demo claims most loudly.

---

## 5. Coverage map

| Type | Contracts |
|---|---|
| Cohort | QC-01, 02, 03, 04, 07, 08, 12, 15 |
| Ranking | QC-05, 06, 13 |
| Comparison | QC-10 |
| Table-routed | QC-09, 11, 14 |

Every MVP capability is covered: individual history (01, 02), change-before-claim (03, 04, 07, 12), portfolio patterns (05, 06, 13, 14), similar history (11).
