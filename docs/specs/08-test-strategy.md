# Test Strategy

Four layers, no overlap. Each names a distinct failure mode, and every one of them is a mode where the product returns something plausible rather than something broken — which is why they are automated rather than reviewed.

| Layer | Asserts | Fails when |
|---|---|---|
| Pipeline expectations | The **data** is right | A temporal invariant is violated at write time |
| Generator validation | The **signal** is right | Realised effect sizes drift from declared parameters |
| Chip execution | The **suggestions** are answerable | A chip the product offers returns nothing |
| Query contracts | **Genie reads the data right** | A question returns a confidently wrong cohort |

---

## 1. Pipeline expectations

The twenty expectations in `02-semantic-layer.md` §8, enforced by the declarative pipeline (ADR-0013). They run on every pipeline execution and fail the build.

These are not a supplement to the specification — they *are* the specification, in executable form. A rule that lives only in a document drifts the first time an implementation detail changes.

Highest-value subset, and the reason to write them before the transformations rather than after: **E4** (seven linkage columns NULL together), **E5** and **E7** (`change_timing` valid and agreeing with the sign of the loss delta), **E6** (report delta non-negative). Those four encode ADR-0004, which is the subtlest decision in the project and the one most likely to be implemented plausibly and wrongly.

---

## 2. Generator validation

Runs in the regeneration Workflow after generation, before the pipeline.

- Measured effect sizes fall within **±15% relative** of the declared parameters in `01-data-model-and-synthetic-data.md` §8.
- The category ranking matches the declared ordering **exactly**.
- Every severity band is populated, `catastrophic` included.
- All scenario populations exist at their declared sizes with their declared policy ids.
- The guaranteed-activity tail contains material changes and claims through `anchor − 120d`.
- Identifier lexical reservation holds: no non-policy identifier matches `\bP-\d{5}\b`.

Without the ranking assertion, a regeneration could silently invert the demo's portfolio chart, and QC-05 would fail with no indication of why.

---

## 3. Chip execution

The cheap always-on layer. Every chip in the bank executes against the current dataset and must return a non-empty, correctly shaped result. **An empty chip result is a build failure** (ADR-0011).

This is what makes "guaranteed answerable" a tested property rather than an intention, and it is why chips are authored as complete context-free questions — a fragment could not be executed in isolation.

The chip bank is versioned with the semantic layer specification, so a column rename that orphans a chip breaks the build rather than the demo.

---

## 4. Query contracts

The fifteen contracts in `05-query-contracts.md`, run three times each, all three required to pass (ADR-0015).

**Triggers.** Not on every commit — Genie API calls cost real time and money.

1. Any change to Genie instructions, Unity Catalog comments, or curated table schemas
2. After every dataset regeneration, against the fresh anchor
3. As a pre-submission gate

**Reporting.** Zero of three is a deterministic break. One or two of three is instruction ambiguity — Genie choosing between readings — and carries equal severity, because a live demo cannot tolerate a coin flip. Generated SQL and Genie's descriptions are logged on failure as diagnostics, never asserted.

**Never retry until green.** Retrying converts nondeterministic wrongness into an invisible mute.

---

## 5. Application tests

Deliberately thin. The app is a thin client over Genie and two deterministic queries (ADR-0012), so most of its risk sits in the layers above.

Worth testing:

- **Policy-id detection.** One match opens, several suppress, zero suppresses, unknown id produces the not-found state. Case-insensitive with word boundaries. This regex is a contract with the generator (ADR-0007) and its failure modes are all silent.
- **Timeline independence.** The timeline renders when the Genie call fails, times out, or returns nothing. This is the demo's insurance policy and it should have a test that mocks each failure.
- **Breadcrumb restore.** Clicking a trail node restores the cached view without a re-query and without growing the thread.

Not worth testing: layout, styling, chart rendering.

---

## 6. What is deliberately not tested

- **Genie's SQL text.** Legitimate rephrasing would make the suite red on non-defects, and a muted suite is worse than no suite.
- **Result cardinality.** The background population contains organic matches, so a count assertion would be brittle and meaningless.
- **Effect magnitudes in query contracts.** Those belong to generator validation; contracts assert only that Genie surfaces the designed ranking.
- **Responsive behaviour.** Out of scope per `06-ux-specification.md` §6.

---

## 7. Pre-submission gate

In order:

1. Regenerate the dataset
2. Generator validation passes
3. Pipeline runs with all expectations green
4. Chip execution passes
5. Query contract suite passes three of three on all fifteen
6. Demo rehearsed end to end against that exact dataset
7. Recording made from that rehearsal

Steps 1 and 6 must not be separated by another regeneration. The recording and the tested dataset have to be the same dataset.
