# Personal auto only, with coverage modelled as lines

The product covers one line of business — personal auto — and models coverage as named Coverage Lines (bodily injury liability, property damage liability, collision, comprehensive, UM/UIM), each with its own limit and, where applicable, its own deductible. Every claim is filed against one Coverage Line.

We took depth over breadth because a scalar policy-level coverage amount makes the flagship question weaker than it appears: a liability-limit increase followed by a windshield claim satisfies "coverage increased within 30 days before a claim" exactly as well as a collision-limit increase followed by a collision claim, so the returned cohort is padded with coincidence. Coverage Lines make `change_relates_to_claimed_coverage` computable, which turns the flagship finding into "raised the limit on the very line later claimed against." Adding homeowners would have doubled the coverage vocabulary, claim taxonomy, distribution set and timeline rendering for a five-minute demo that is already complete with one line of business.

## Consequences

- **The material category set drops to five** — coverage, deductible, vehicle, address, status. The `property` category and the Property entity leave the model. Amends ADR-0003.
- **`policy_change_event` carries `coverage_line`,** NULL for categories that are not line-specific (vehicle, address, status). Category stays `coverage`/`deductible`; the line is an attribute, not a new category.
- **`claim_event` carries `coverage_line`,** and `change_relates_to_claimed_coverage` is the equality of the two.
- **Deductibles exist only on collision and comprehensive.** A deductible change on a liability line is not a valid row, and the generator must not emit one.
- **Per-category proximity columns cover five categories,** not six.
- **The "does this generalise beyond auto?" question is answered in narrative, not in data.** Accepted; the semantic layer shape is line-of-business agnostic even though the dataset is not.
