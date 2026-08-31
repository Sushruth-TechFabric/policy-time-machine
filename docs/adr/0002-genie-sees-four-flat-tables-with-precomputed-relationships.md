# Genie sees flat curated tables with pre-computed relationships

The Genie space exposes four core curated tables — `policy_change_event`, `claim_event`, `policy_profile`, `policy_timeline_event` — and never the underlying SCD Type 2 history. Two further tables were added later: `policy_pattern_match` (ADR-0009) and `policy_similarity` (ADR-0010), for six in total. Temporal *relationships* are materialized as columns; temporal *thresholds* are left to Genie as WHERE literals.

We did this because the questions the product exists to answer ("coverage increased within 30 days before a claim") require correlated lookahead joins across policy versions and claims — exactly the SQL that is hardest for a text-to-SQL system to get right, and whose failures are silent rather than loud. By materializing `days_to_next_claim` and the per-category offset columns, every windowed question collapses to a flat filter, which is what Genie is reliable at. Correctness is tested once in the pipeline instead of re-derived on every question.

## Consequences

- **Grains stay separate.** `policy_change_event` and `claim_event` are not unioned for analysis. A claim with three preceding changes appears on three change rows, so any claim aggregate computed from `policy_change_event` must use `COUNT(DISTINCT next_claim_id)`. Claim-grain questions belong on `claim_event`. `policy_timeline_event` is for reading one policy's story, never for counting.
- **`next_claim_id` is many-to-one by design.** Multiple changes preceding the same claim all point at it. This is required for "several material changes before a high-severity claim" and must not be treated as a duplication bug.
- **Claim linkage is anchored by report date.** Superseded in detail by ADR-0004; the original wording here anchored linkage on loss date, which made the post-loss/pre-report pattern inexpressible.
- **No sentinels.** A change with no subsequent claim has NULL deltas, never 9999. Genie will average a sentinel into a mean without complaining.
- **Category proximity uses signed offsets.** One column per material category (`nearest_<category>_change_offset_days`), negative for before and positive for after, so symmetric co-occurrence is `ABS(...) <= N` and direction is a sign filter. Same-category offsets refer to the previous distinct change of that category.
- **New question shapes may require new columns.** The semantic layer is opinionated; extending it is a pipeline change, not a prompt change. Accepted deliberately.
- **Similarity and noteworthiness are not Genie's job.** Similar-history ranking is computed in the app from a handcrafted, explainable feature vector. "Unusual patterns" resolves to named, documented boolean rules on `policy_profile` — never to Genie's own judgment, which would be fraud scoring by another name.
