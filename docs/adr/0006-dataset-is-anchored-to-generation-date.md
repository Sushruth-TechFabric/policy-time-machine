# The dataset is anchored to its generation date, and nothing is pre-computed against "now"

The generator takes an `anchor_date` (defaulting to the generation date) and a fixed seed. All event dates are `anchor + offset`; nothing absolute appears anywhere in the generator. Genie writes plain `CURRENT_DATE` arithmetic with no special instruction.

The alternatives all pay for reproducibility with a silent failure mode. A fixed historical window plus a `reference_date` table requires Genie to remember a cross join on every relative-date question, and forgetting it returns zero rows rather than an error — an empty result is the worst demo failure, because nothing looks broken. Rewriting relative phrases in the app puts natural-language parsing in front of Genie, contradicting the premise that Genie interprets intent. Requiring explicit date ranges turns the investigation bar into a query form.

## Consequences

- **Pre-compute event-to-event deltas; never event-to-now deltas.** Event-to-event columns (`days_to_next_claim_loss`, `days_to_next_claim_report`, the per-category offsets, `prior_change_count_30d/60d/90d`, `material_changes_in_loss_report_gap`) are stable forever and immune to dataset aging. Anything measured against "now" is stale the moment real time passes and will silently disagree with `CURRENT_DATE` arithmetic by exactly the staleness gap. Recency is expressed by storing **dates** and letting Genie do the arithmetic.
- **`policy_profile` carries `last_material_change_date` and `last_claim_date`**, superseding the earlier `days_since_last_material_change` day-count column, which was exactly this mistake.
- **Only recency questions depend on regeneration freshness.** Everything else survives aging untouched.
- **The staleness budget is a tested number, not a hope.** Judging often happens days or weeks after submission with no deploy in between, so "regenerate at deploy" is insufficient on its own. Either run a scheduled daily regeneration (the fixed seed keeps it idempotent in story terms) or size the guaranteed-activity tail to worst-case judging lag. The assumed maximum staleness is written down and tested.
- **The seed owns identity; the anchor owns dates.** Policy IDs, customer IDs and scenario assignments derive from the seed alone, so P-18492 is the same policy with the same story at any anchor. Event dates derive from anchor plus offset.
- **The demo script speaks in relative language** ("nineteen days before the claim") or is regenerated from the dataset. The absolute dates in the original product brief's example timeline are illustration, not script.
- **No future events, but future attributes are legitimate.** No event timestamp may exceed the anchor, but policy expiration dates rightly sit in the future. The generator must distinguish event timestamps from attribute dates, or clamping will make every policy look expired.
- **Generator and warehouse agree on UTC.** `CURRENT_DATE` evaluates in warehouse timezone; a mismatch shifts every "last 30 days" boundary by a day for a demo run near midnight.
