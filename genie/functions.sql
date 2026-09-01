-- Trusted-asset SQL functions for the Genie space.
-- Rendered from genie/build_space.py; do not edit by hand.
-- Registered with: python build_space.py create-functions

CREATE OR REPLACE FUNCTION workspace.ptm_gold.similar_histories(
  p_policy_id STRING COMMENT 'The policy whose similar histories to return, e.g. P-10155'
)
RETURNS TABLE (
  rank INT,
  similar_policy_id STRING,
  similarity_score DOUBLE,
  top_reasons STRING,
  material_change_count INT,
  claim_count INT,
  noteworthy_pattern_count INT
)
COMMENT 'The top-20 policies whose histories most resemble the given policy, each with its profile summary. Similarity is precomputed and directional; a match is a historical pattern, never an assertion about a person.'
RETURN SELECT s.rank, s.similar_policy_id, s.similarity_score, s.top_reasons,
       p.material_change_count, p.claim_count, p.noteworthy_pattern_count
FROM workspace.ptm_gold.policy_similarity s
JOIN workspace.ptm_gold.policy_profile p ON p.policy_id = s.similar_policy_id
WHERE s.policy_id = p_policy_id
ORDER BY s.rank;

CREATE OR REPLACE FUNCTION workspace.ptm_gold.material_changes_before_claims(
  p_days INT COMMENT 'Window in days before the linked claim, e.g. 30'
)
RETURNS TABLE (
  policy_id STRING,
  change_date DATE,
  change_category STRING,
  coverage_line STRING,
  days_to_next_claim_loss INT,
  next_claim_id STRING,
  next_claim_amount DOUBLE,
  next_claim_severity STRING
)
COMMENT 'Material policy changes that occurred within p_days days before the linked claim happened. Encodes the required two-filter window (change_timing = before_loss AND days_to_next_claim_loss <= p_days); a bare day-count filter is always wrong.'
RETURN SELECT policy_id, change_date, change_category, coverage_line,
       days_to_next_claim_loss, next_claim_id, next_claim_amount, next_claim_severity
FROM workspace.ptm_gold.policy_change_event
WHERE is_material = true
  AND change_timing = 'before_loss'
  AND days_to_next_claim_loss <= p_days
ORDER BY days_to_next_claim_loss;

