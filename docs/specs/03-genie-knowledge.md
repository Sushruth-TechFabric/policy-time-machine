# Genie Knowledge and Instruction Specification

What the Genie space contains, what it is told, and the example SQL it learns from. This document and the Unity Catalog comments in `02-semantic-layer.md` render from a single authored source and must never disagree (ADR-0013).

---

## 1. Space contents

Exactly six tables, all curated — the `ptm_gold` schema, and nothing outside it (ADR-0002, 0009, 0010, 0016):

`policy_change_event` · `claim_event` · `policy_profile` · `policy_timeline_event` · `policy_pattern_match` · `policy_similarity`

The SCD Type 2 history (`ptm_bronze`), the silver `change_event` stream (`ptm_silver`) and every other non-gold table are excluded. Exposing both a correct path and a plausible-but-wrong path in the same space produces answers that look right and are not — the worst failure mode for an investigation tool.

The six tables and their relationships are drawn in [`docs/diagrams/02-er-genie-space.mmd`](../diagrams/02-er-genie-space.mmd), embedded in `02-semantic-layer.md`.

---

## 2. Routing rules

One line each. These tell Genie which grain a question belongs to.

| Question is about | Table |
|---|---|
| What changed, and when, and what followed | `policy_change_event` |
| Claims — counting, averaging, ranking by amount or severity | `claim_event` |
| Policies as a population — how many changes, how often, which patterns | `policy_profile` |
| One policy's story in chronological order | `policy_timeline_event` |
| Which patterns exist, how common they are, which policies match | `policy_pattern_match` |
| "Similar", "looks like", "histories like", "policies like this one" | `policy_similarity` |

Three prohibitions stated explicitly in the instructions:

1. **Never aggregate `policy_timeline_event`.** It mixes grains; counts and sums over it are wrong. Use it only to list one policy's events.
2. **Never compute similarity from raw columns.** Similarity exists only in `policy_similarity`.
3. **Never derive a pattern definition ad hoc.** Patterns exist only in `policy_pattern_match` and the `policy_profile` flags.

---

## 3. The critical instruction

This is the product's most important instruction, and the demo question depends on it (ADR-0004).

> **"Within N days before a claim" is always two filters, never one.**
>
> `days_to_next_claim_loss` is **signed**. Negative values mean the change happened *after* the loss, in the window before it was reported. A bare `days_to_next_claim_loss <= 30` therefore silently includes those changes and returns a wrong cohort.
>
> Always write:
> ```sql
> WHERE change_timing = 'before_loss'
>   AND days_to_next_claim_loss <= 30
> ```

A bare threshold filter appearing anywhere in the instruction set or example library is a defect.

---

## 4. Defined terms

Genie must use these definitions rather than improvising.

| Phrase | Means |
|---|---|
| high-severity claim | `severity_band IN ('severe','catastrophic')` |
| material change | `is_material = true` |
| next claim / subsequent claim | The claim in `next_claim_id` — next by **report** date |
| recent | Within the last 90 days, unless the user gives a window |
| near the limit | `at_or_near_limit = true`, i.e. utilisation ≥ 90% |
| rapid change cluster | The `rapid_change_cluster` pattern; do not recompute it |
| similar | A row in `policy_similarity`; top 20 only |

"Recent" is computed at query time from `last_material_change_date`, never read from a stored day-count (ADR-0006).

---

## 5. Example SQL library

Genie learns from these. Each maps to one of the fourteen example questions.

**Coverage increased within 30 days before a claim**
```sql
SELECT policy_id, change_date, coverage_line, old_value_num, new_value_num,
       days_to_next_claim_loss, next_claim_amount, next_claim_severity
FROM policy_change_event
WHERE change_category = 'coverage'
  AND change_direction = 'increase'
  AND change_timing = 'before_loss'
  AND days_to_next_claim_loss <= 30
ORDER BY days_to_next_claim_loss
```

**...and it was the line later claimed against**
```sql
  AND change_relates_to_claimed_coverage = true
```

**What changed on a policy in the last year**
```sql
SELECT event_date, event_type, event_category, display_label,
       old_value, new_value, amount
FROM policy_timeline_event
WHERE policy_id = 'P-18492'
  AND event_date >= CURRENT_DATE - INTERVAL 1 YEAR
ORDER BY event_date
```

**Which material changes most often precede high-severity claims**
```sql
SELECT change_category,
       COUNT(*) AS change_count,
       COUNT(DISTINCT next_claim_id) AS claim_count
FROM policy_change_event
WHERE is_material = true
  AND change_timing = 'before_loss'
  AND days_to_next_claim_loss <= 60
  AND next_claim_severity IN ('severe','catastrophic')
GROUP BY change_category
ORDER BY claim_count DESC
```
Note `COUNT(DISTINCT next_claim_id)`: several changes share one claim, so `COUNT(*)` counts changes, not claims.

**Vehicle and address changed within 60 days of each other**
```sql
SELECT policy_id, change_date, nearest_address_change_offset_days
FROM policy_change_event
WHERE change_category = 'vehicle'
  AND ABS(nearest_address_change_offset_days) <= 60
```

**Changes made after the loss but before it was reported**
```sql
SELECT policy_id, change_date, change_category, days_to_next_claim_loss
FROM policy_change_event
WHERE change_timing = 'after_loss_before_report'
```

**Claims near a recently raised limit**
```sql
SELECT c.claim_id, c.policy_id, c.settled_amount, c.severity_band,
       c.limit_utilization_pct
FROM claim_event c
JOIN policy_pattern_match p
  ON p.policy_id = c.policy_id
 AND p.pattern_code = 'claim_near_new_limit'
WHERE c.at_or_near_limit = true
```

**Recent changers versus everyone else — both groups, always**
```sql
SELECT CASE WHEN last_material_change_date >= CURRENT_DATE - INTERVAL 90 DAY
            THEN 'recent material change'
            ELSE 'no recent material change' END AS comparison_group,
       COUNT(*) AS policies,
       AVG(claims_per_year) AS claims_per_year
FROM policy_profile
GROUP BY 1
```
Comparison questions return **both groups with their sample sizes**. A single group's rate is never returned alone (ADR-0014).

**Similar histories**
```sql
SELECT s.rank, s.similar_policy_id, s.similarity_score, s.top_reasons,
       p.material_change_count, p.claim_count, p.noteworthy_pattern_count
FROM policy_similarity s
JOIN policy_profile p ON p.policy_id = s.similar_policy_id
WHERE s.policy_id = 'P-18492'
ORDER BY s.rank
```

**Which patterns are most common**
```sql
SELECT pattern_name, COUNT(DISTINCT policy_id) AS policies
FROM policy_pattern_match
GROUP BY pattern_name
ORDER BY policies DESC
```

**Policies with nothing noteworthy**
```sql
SELECT policy_id FROM policy_profile WHERE noteworthy_pattern_count = 0
```

---

## 6. Stated limits

Genie surfaces these rather than improvising around them.

- **Similarity returns at most 20 neighbours.** A request for more returns 20 with the limit stated.
- **Similarity is directional.** A being similar to B does not mean B is similar to A.
- **`similarity_score` is not comparable across datasets.**
- **Claim amounts are single settled figures.** There is no claim development history.
- **Only personal auto** is in scope.

---

## 7. Approved vocabulary

One list, governing Genie's answers, `pattern_name`, `top_reasons`, timeline `display_label`, chip text and UI copy. Enforced as expectation E18.

**Use:** noteworthy · unusual pattern · investigation candidate · historical pattern · requires review · worth investigating · associated with · observed alongside · occurred before

**Never use:** fraud · fraudulent · suspicious · scheme · deceptive · guilty · risk score · predicts · causes · leads to · increases the risk of

The second list bans two distinct things — accusatory language about people, and causal language about the data. Both are product boundaries (ADR-0014).

**Standing framing sentence**, used in the writeup, the demo and any explanatory copy:

> The dataset is synthetic. Investigation-worthy patterns are deliberately seeded at declared, documented effect sizes — the product demonstrates how historical patterns are surfaced and investigated, not that policy changes predict claims.

---

## 8. Conversation behaviour

One Genie conversation per investigation (ADR-0011). Typed follow-ups rely on carried context; authored chips do not — every chip is a complete, context-free question with entities interpolated, sent inside the thread. Every chip is executed against the generated dataset in CI and must return a non-empty, correctly shaped result. A chip that returns empty is a build failure.
