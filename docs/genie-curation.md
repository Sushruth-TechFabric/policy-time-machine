# Genie curation — how this space maps to the Databricks curation hierarchy

Databricks' guidance for Genie spaces ranks curation layers: attached tables,
then table/column metadata, then SQL logic (joins, expressions, examples),
then text instructions as a last resort, plus common questions and benchmarks.
This doc maps our build to each layer and records why we deviate where we do.

## 1. Unity Catalog tables (required)

Exactly six gold tables in `workspace.ptm_gold` (ADR-0002, ADR-0016), declared
once in `genie/build_space.py`. The SCD Type 2 source tables and generator
artefacts (`ptm_bronze`) are deliberately excluded so the space never offers a
correct path and a plausible-wrong path to the same answer.

**Known boundary**: Genie is not hard-limited to attached tables — the real
boundary is Unity Catalog entitlement. In this single-account demo workspace
the demo identity can read bronze, so a user who *names* a bronze table could
pull it into a query. The scope instruction ("there is no source history table
… do not assume one exists") covers the default path; entitlement hardening is
out of scope for a competition demo.

## 2. Table and column metadata (strongly recommended)

All six tables and every column carry Unity Catalog comments, authored once in
`pipeline/uc_comments.py` and treated as semantic-layer content, not
documentation (ADR-0013). Comments enumerate categorical values
("One of coverage, deductible, vehicle, address, status, premium, agent"),
disambiguate the traps (`days_to_next_claim_loss` is signed; filter with
`change_timing`, not the sign), and hold five spec-critical definitions
verbatim, asserted at import time.

**Not used — Knowledge Store synonyms / value dictionaries**: the Knowledge
Store has no public REST API, and our column names are already business-plain
with values enumerated in comments, so the marginal value is low. If wanted,
synonyms can be added by hand in the Genie UI without touching this repo.
(Trusted-asset SQL functions, by contrast, *are* API-attachable — the
serialized space's `instructions.sql_functions` field, shape
`{id, identifier}`, verified empirically against a scratch space — and are
managed from `build_space.py` like everything else.)

## 3. SQL logic (highly recommended)

All three recommended forms are in place:

- **Joins — PK/FK constraints**: every gold table declares an informational
  primary key, and every child table declares foreign keys (all six reference
  `policy_profile(policy_id)`; `next_claim_id`, `evidence_*` and
  `similar_policy_id` reference their parents), so Genie reads the join graph
  from Unity Catalog metadata. Constraints on materialized views cannot be
  `ALTER`ed in after the fact — they are declared in the pipeline's table
  definitions, rendered from the same single-source schema declarations
  (`transformations.GOLD_KEYS` + `constrained_schema_ddl`, tested in
  `pipeline/tests/test_gold_keys.py`). They are `NOT ENFORCED` (the only kind
  Databricks supports); the pipeline expectations remain the integrity
  guarantee (ADR-0013). On top of that, the relationships Genie needs most are
  *precomputed into the tables* (ADR-0002) — the "pre-joined view" pattern.
- **Metric logic in SQL**: business terms are materialized as columns
  (`is_material`, `at_or_near_limit`, `severity_band`, `claims_per_year`) —
  the metric definition runs once, in the pipeline, under expectations —
  and the two most error-prone rules are additionally registered as
  **trusted-asset UC table functions** (`genie/functions.sql`, authored in
  `build_space.py`): `similar_histories(policy_id)` (similarity is
  precomputed-only) and `material_changes_before_claims(days)` (the
  two-filter claim window). Both are attached to the space as trusted assets,
  so Genie marks answers built on them as verified.
- **Example SQL**: 17 question→SQL pairs in `genie/build_space.py`, each a
  complete standalone query, covering every query contract's shape.

## 4. Text instructions (recommended, "last resort")

Our text instructions stay inside the sanctioned uses: behaviour (comparison
answers always return group, rate, and n — ADR-0014), output rules (approved
vocabulary, top-10 default for bare superlatives), and edge cases (the signed
day-count trap, never aggregating the mixed-grain timeline table). Metric and
join semantics live in the tables and examples per the layers above; the
"defined terms" block restates column-backed definitions rather than
introducing text-only ones.

## 5. Common questions (recommended)

Five sample questions are configured in the space UI (`SAMPLE_QUESTIONS`), and
each maps to a curated example query, so they teach Genie as well as guide
users — the "attach SQL answers" best practice.

## 6. Benchmarks (strongly recommended)

Genie's native benchmark feature is **UI-only — the REST API exposes no
benchmark endpoints** (verified against this workspace), so it cannot be
version-controlled or run from CI. We therefore run the equivalent loop
externally: `ci/genie/` executes fifteen query contracts (spec 05, ADR-0015),
each in a fresh conversation (matching benchmark semantics; QC-15 alone reuses
a conversation to test multi-turn follow-up), asserting on returned values
against ground truth computed from the planted generator manifest — never on
Genie's SQL text. The suite is rerun after every curation change; the
pre-submission gate requires 15/15 across three consecutive runs.

Native benchmarks can still be seeded by hand in the UI from the example
question→SQL pairs if a workspace-visible benchmark score is wanted; the CI
harness remains the source of truth.
