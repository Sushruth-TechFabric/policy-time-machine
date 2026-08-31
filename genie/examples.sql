-- Genie curated example SQL library.
-- Rendered from genie/build_space.py; do not edit by hand.
-- Source content: docs/specs/03-genie-knowledge.md §5.

-- Q: Show policies where coverage increased within 30 days before a claim
SELECT policy_id, change_date, coverage_line, old_value_num, new_value_num,
       days_to_next_claim_loss, next_claim_amount, next_claim_severity
FROM policy_change_event
WHERE change_category = 'coverage'
  AND change_direction = 'increase'
  AND change_timing = 'before_loss'
  AND days_to_next_claim_loss <= 30
ORDER BY days_to_next_claim_loss;

-- Q: Show policies where coverage increased within 30 days before a claim, on the line later claimed against
SELECT policy_id, change_date, coverage_line, old_value_num, new_value_num,
       days_to_next_claim_loss, next_claim_amount, next_claim_severity
FROM policy_change_event
WHERE change_category = 'coverage'
  AND change_direction = 'increase'
  AND change_timing = 'before_loss'
  AND days_to_next_claim_loss <= 30
  AND change_relates_to_claimed_coverage = true
ORDER BY days_to_next_claim_loss;

-- Q: What changed on a policy in the last year
SELECT event_date, event_type, event_category, display_label,
       old_value, new_value, amount
FROM policy_timeline_event
WHERE policy_id = 'P-18492'
  AND event_date >= CURRENT_DATE - INTERVAL 1 YEAR
ORDER BY event_date;

-- Q: Which material changes most often precede high-severity claims
SELECT change_category,
       COUNT(*) AS change_count,
       COUNT(DISTINCT next_claim_id) AS claim_count
FROM policy_change_event
WHERE is_material = true
  AND change_timing = 'before_loss'
  AND days_to_next_claim_loss <= 60
  AND next_claim_severity IN ('severe','catastrophic')
GROUP BY change_category
ORDER BY claim_count DESC;

-- Q: Vehicle and address changed within 60 days of each other
SELECT policy_id, change_date, nearest_address_change_offset_days
FROM policy_change_event
WHERE change_category = 'vehicle'
  AND ABS(nearest_address_change_offset_days) <= 60;

-- Q: Changes made after the loss but before it was reported
SELECT policy_id, change_date, change_category, days_to_next_claim_loss
FROM policy_change_event
WHERE change_timing = 'after_loss_before_report';

-- Q: Claims near a recently raised limit
SELECT c.claim_id, c.policy_id, c.settled_amount, c.severity_band,
       c.limit_utilization_pct
FROM claim_event c
JOIN policy_pattern_match p
  ON p.policy_id = c.policy_id
 AND p.pattern_code = 'claim_near_new_limit'
WHERE c.at_or_near_limit = true;

-- Q: Recent changers versus everyone else — both groups, always
SELECT CASE WHEN last_material_change_date >= CURRENT_DATE - INTERVAL 90 DAY
            THEN 'recent material change'
            ELSE 'no recent material change' END AS comparison_group,
       COUNT(*) AS policies,
       AVG(claims_per_year) AS claims_per_year
FROM policy_profile
GROUP BY 1;

-- Q: Similar histories to a policy
SELECT s.rank, s.similar_policy_id, s.similarity_score, s.top_reasons,
       p.material_change_count, p.claim_count, p.noteworthy_pattern_count
FROM policy_similarity s
JOIN policy_profile p ON p.policy_id = s.similar_policy_id
WHERE s.policy_id = 'P-18492'
ORDER BY s.rank;

-- Q: Which patterns are most common
SELECT pattern_name, COUNT(DISTINCT policy_id) AS policies
FROM policy_pattern_match
GROUP BY pattern_name
ORDER BY policies DESC;

-- Q: Policies with nothing noteworthy
SELECT policy_id FROM policy_profile WHERE noteworthy_pattern_count = 0;

