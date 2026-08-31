# The semantic layer is a declarative pipeline, and every invariant is an enforced expectation

The curated tables are built by a Lakeflow Declarative Pipeline, orchestrated with Workflows, deployed as a Databricks Asset Bundle, governed in Unity Catalog. Every temporal invariant decided in these ADRs is expressed as a pipeline expectation that fails the build at write time.

We chose the declarative pipeline primarily for the expectations. This project's correctness lives almost entirely in a set of subtle rules — signed deltas, NULL propagation, band partitions, denormalised columns that must agree with their sources — and a rule recorded only in a document will drift the first time an implementation detail changes. Enforced at write time, the same rules become a guardrail for the coding agent and a first-class judging artifact: our temporal semantics, verified rather than narrated.

## The expectations catalogue

A deliverable in the semantic layer spec: one row per invariant, each cross-referencing the ADR that decided it. At minimum —

| Invariant | Source |
|---|---|
| No sentinels in `change_pct`, `days_to_next_claim_*`, `limit_utilization_pct`; NULL instead | ADR-0003, 0004, 0008 |
| `next_claim_id`, both deltas and `change_timing` are NULL together or populated together | ADR-0004 |
| `change_timing` is exactly `before_loss` or `after_loss_before_report` on every linked row | ADR-0004 |
| `days_to_next_claim_report >= 0` always | ADR-0004 |
| `change_direction = 'switch'` for every categorical change, never NULL | ADR-0003 |
| Severity bands partition the amount range with no overlap and no gap | ADR-0008 |
| `next_claim_severity` agrees with `severity_band` for the same claim | ADR-0008 |
| `policy_similarity` excludes self-neighbours; `rank` is dense 1..K | ADR-0010 |
| `noteworthy_pattern_count` equals `COUNT(DISTINCT pattern_code)` in `policy_pattern_match` | ADR-0009 |
| Every `pattern_name` and `top_reasons` string draws only on the approved vocabulary | ADR-0009, 0010 |
| No event timestamp exceeds `anchor_date` | ADR-0006 |

The vocabulary expectation is worth noting: the product's no-fraud-labelling boundary is enforced as a data-quality constraint, not as a code-review convention.

## Consequences

- **The scheduled regeneration Workflow implements ADR-0006's staleness budget** — generator job, then pipeline, then similarity and pattern computation, then a freshness check.
- **The Asset Bundle packages job, pipeline, Genie space and app as one deployable unit.** This is the literal answer to "can a judge reproduce this," and it is load-bearing given that Databricks Apps has no public access.
- **Unity Catalog comments are authored semantic-layer content, not documentation.** Genie reads table and column comments as context, so they are versioned with the semantic layer spec and reviewed like the Genie instruction set — especially for the counterintuitive definitions: next claim means next by *report* date; `change_timing` is deliberately redundant with the sign of the loss delta; high-severity means severe or catastrophic.
- **Comments and Genie instructions share a single authored source** and are rendered to both. They must never be able to disagree.
