# Noteworthy Patterns are named rules, stored at match grain and mirrored as flags

"Unusual patterns worth investigating" resolves to a fixed set of named, documented, deterministic rules. Matches are stored in `policy_pattern_match` at policy×pattern grain — carrying `pattern_code`, `pattern_name`, `matched_on_date` and evidence references — and mirrored as named boolean columns plus `noteworthy_pattern_count` on `policy_profile`.

The redundancy is deliberate, in the same spirit as `change_timing` in ADR-0004. Booleans make "policies matching X" a trivial filter and "policies with nothing noteworthy" a `count = 0` rather than a six-way `AND NOT` that Genie will eventually get wrong by one term. The match table makes "which pattern is most common" a `GROUP BY` rather than an unpivot into `UNION ALL`, and gives the evidence panel a date and evidence to show rather than only the fact that a rule fired at some point.

## The rule set

| Code | Fires when |
|---|---|
| `coverage_raised_then_claimed_same_line` | coverage increase, Linked Claim on the same Coverage Line within 60 days, `before_loss` |
| `deductible_lowered_before_claim` | deductible decrease, Linked Claim within 60 days, `before_loss` |
| `change_in_loss_report_gap` | any material change with `change_timing = 'after_loss_before_report'` |
| `rapid_change_cluster` | three or more material changes within any 30-day span |
| `vehicle_and_address_within_60d` | a vehicle change with `ABS(nearest_address_change_offset_days) <= 60` |
| `claim_near_new_limit` | an `at_or_near_limit` claim where that line's limit rose within the prior 90 days |

## Consequences

- **Both representations derive from one rule evaluation, in a single pass.** Evaluate each rule once, emit the match rows, then derive the booleans and `noteworthy_pattern_count` from those rows — never from a second copy of the predicate. Because ADR-0007 puts the generated SQL in the evidence panel, a boolean that says a rule fired while the match table holds no row is a disagreement visible on screen.
- **Pattern windows are baked, and that is a deliberate exception to ADR-0002.** "Rapid change cluster" means something specific or it means nothing; a named definition is not a user-supplied threshold. User-supplied thresholds continue to work against the raw columns.
- **`pattern_name` is user-facing text and is bound by the vocabulary rule.** Noteworthy, unusual, pattern, investigation candidate — never fraud, suspicious, or any assertion about a person. These strings surface verbatim in Genie answers and in the UI, so the enforcement point is the pipeline, not the front end.
- **The rule set is expected to grow; the column set is not the constraint.** `noteworthy_pattern_count` is the general-purpose summary, so adding a rule adds a boolean but changes no existing question.
