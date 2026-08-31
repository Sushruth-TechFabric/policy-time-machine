# Similar history is a pre-computed neighbour table, not a computation

Top-K neighbours for every policy are materialised into `policy_similarity(policy_id, similar_policy_id, rank, similarity_score, top_reasons)` and queried by Genie as ordinary SQL. Neighbours are computed by exact brute-force distance in a Spark job, from a handcrafted, named feature vector. Supersedes the earlier ruling that similarity would be computed in the app layer.

The app-layer ruling had no route to be invoked. ADR-0007 limits the app to a policy-ID regex, so a typed "find policies with histories similar to P-18492" would open a timeline, forward the question to Genie — which has no similarity concept — and get back a confident answer to a different question. Treating similarity as data instead of computation makes the fourth MVP capability behave exactly like the other three, with no intent detection and no separate code path.

Exact distance rather than approximate nearest-neighbour search because demo reproducibility rests on ADR-0006's seed-owns-identity rule: P-18492's neighbour list must be identical across regenerations, and ANN gives no guarantee of stable top-K ordering under ties. At eight thousand policies the exact computation runs in seconds, so approximation would buy nothing and cost the guarantee. The table schema is engine-agnostic, so Databricks Vector Search with self-managed embeddings remains available as a later demonstration — off the critical path.

## The feature vector

Rate-normalised so tenure does not dominate: material changes per year; peak changes in any 30-day window; share of changes in each of the five material categories; net coverage direction bias; claims per year; maximum severity band as an ordinal; mean limit utilisation; share of material changes falling within 60 days before a loss; and the set of matched pattern codes.

Distance is Euclidean over z-scored numerics, plus Jaccard overlap on the pattern-code set as a separately weighted component. The pattern component is what makes `top_reasons` writable — z-scores and neighbours regenerate together from the same seed, so dataset-relativity is harmless here, unlike the percentile severity bands rejected in ADR-0008. The difference is that similarity attaches no fixed product vocabulary to absolute values.

## Consequences

- **Deterministic tie-break:** rank by `similarity_score DESC`, then `similar_policy_id ASC`. Without this, regeneration can reorder equal-scoring neighbours.
- **A policy is never its own neighbour.**
- **Top-K is directional and that is not a bug.** A appearing in B's top 20 does not imply the reverse. Documented so nobody symmetrises it.
- **K = 20, fixed at build time.** The Genie instruction states the cap, so "show me 50 similar policies" returns 20 with the limit surfaced rather than improvised.
- **`similarity_score` is unitless and dataset-relative** — comparable within a generation, not across seeds. `rank` is dense, 1..K.
- **`top_reasons` is generated at pipeline time from named dimensions,** under the same vocabulary constraint as `pattern_name`. It surfaces verbatim in the UI and in Genie's answers.
- **Genie gets a one-line routing rule:** "similar", "looks like", "histories like", "policies like this one" map to `policy_similarity`, joined to `policy_profile` for detail. Genie must never attempt to compute similarity from raw columns.
- **The timeline's "find similar policies" affordance reads the same table,** so the capability is both askable and clickable with one source of truth.
- **The generator plants neighbour groups.** Scenario policies must be each other's neighbours at known ranks so the demo's similarity moment is scripted-stable, and at least one control policy has benign top neighbours so similarity itself does not read as an accusation.
