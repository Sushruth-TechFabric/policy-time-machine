# Specifications

File numbers reflect the order they were written, not the order to read them in.

## Reading order

**Start here** — what the product is and who it serves

1. [`09-product-charter.md`](./09-product-charter.md) — problem, thesis, scope, boundaries, success criteria
2. [`10-personas-and-jobs.md`](./10-personas-and-jobs.md) — who this is for, and who it isn't
3. [`12-user-journeys.md`](./12-user-journeys.md) — what happens on screen, end to end
4. [`11-product-requirements.md`](./11-product-requirements.md) — every requirement with its verification

**Build the data** — fully specified; blocks nothing

5. [`01-data-model-and-synthetic-data.md`](./01-data-model-and-synthetic-data.md) — source model, identifier contract, generator, scenarios
6. [`02-semantic-layer.md`](./02-semantic-layer.md) — the six curated tables and the expectations catalogue
7. [`03-genie-knowledge.md`](./03-genie-knowledge.md) — routing, defined terms, example SQL, approved vocabulary

**Build the app**

8. [`06-ux-specification.md`](./06-ux-specification.md) — layout, states, visual constraints, and what is out of scope

**Verify and ship**

9. [`05-query-contracts.md`](./05-query-contracts.md) — the fifteen contracts
10. [`08-test-strategy.md`](./08-test-strategy.md) — four layers, and what is deliberately not tested
11. [`07-demo-specification.md`](./07-demo-specification.md) — beat by beat
12. [`04-implementation-plan.md`](./04-implementation-plan.md) — sequencing, parallel tracks, cut order

## Also

- [`../../CONTEXT.md`](../../CONTEXT.md) — the glossary. Read it before anything else; these documents use its vocabulary precisely.
- [`../adr/`](../adr/) — fifteen decisions with their reasoning. The specifications state *what*; the ADRs record *why*, including the alternatives rejected and the two decisions later superseded.

## Open parameters

- Submission deadline — converts `04` §6 into a schedule and fixes where the cut line falls
- Dataset volumes — currently an assumption in `01` §4
- Target workspace, catalog and schema names
