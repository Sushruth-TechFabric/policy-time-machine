# Generic rendering, with the timeline routed from the question text

The app does not classify Genie's results. Every Genie answer renders as a table plus an auto-selected chart, alongside the generated SQL, row count and Genie's own description in an evidence panel. The timeline is routed instead from the **user's question text**: a regex for the policy-ID pattern, and on a single hit the app opens that policy's timeline from the deterministic ADR-0001 query path. Supersedes the two-signal output classifier considered earlier.

Detection on the input is categorically stronger than classification on the output. The app fully controls the question text, so there is no alias drift, no multi-table ambiguity, no decision table and no SQL parsing. The trade we accepted is that cohorts and comparisons lose bespoke renderers — an auto-chart is adequate for those in a demo — while the signature visual stays deterministic exactly where it matters, on the two policy-scoped MVP capabilities.

## Consequences

- **The policy-ID pattern is a contract between the generator and the app,** not an incidental format. It must be distinctive and collision-proof (`P-` followed by five digits), **lexically reserved** so no other identifier can embed it — a claim ID containing a policy ID would break detection — and seed-stable across regenerations per ADR-0006. The app matches case-insensitively on word boundaries.
- **One ID opens, several suppress.** Exactly one distinct policy ID in the question opens the timeline; two or more render generically. Side-by-side timelines are a stretch goal. The app never picks one arbitrarily.
- **The timeline never blocks on Genie and never depends on Genie succeeding.** It renders from the app's own deterministic query; Genie's result arrives beside it as evidence whenever it arrives. The demo's most important question therefore has a guaranteed visual even in Genie's worst moment.
- **A nonexistent ID gets an explicit not-found state,** never an empty timeline. An unexplained blank timeline reads as the product breaking; "no policy P-18499 found" reads as the product working.
- **Opening a timeline next to a non-temporal question is intended, not redundant.** Ambient history beside a point answer is the product thesis in miniature. No suppression heuristic should be added later.
- **Showing the generated SQL is a product feature.** In an investigation tool it belongs in the evidence panel — it is also the fastest way to demonstrate that the temporal semantics are real rather than narrated.
