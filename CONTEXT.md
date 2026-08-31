# Policy Time Machine

An investigation tool for exploring how insurance policies changed over time and how those changes relate to claims. This glossary fixes the language; it deliberately contains no schema or implementation detail.

## Language

### Changes

**Policy Change**:
A single field on a policy taking a new value at a point in time. The atomic unit of history.
_Avoid_: update, modification, amendment

**Material Change**:
A Policy Change in one of the five decision categories — coverage, deductible, vehicle, address, status. These represent choices someone made about the policy, and only these are counted when the product says "how many changes."
_Avoid_: significant change, important change

**Coverage Line**:
A named protection on an auto policy — bodily injury liability, property damage liability, collision, comprehensive, uninsured/underinsured motorist — each carrying its own limit and, where applicable, its own deductible. "Coverage increased" is always a statement about one line.
_Avoid_: coverage type, peril

**Relevant Change**:
A coverage or deductible change on the same Coverage Line the Linked Claim was later filed against. Distinguishes a real finding from a coincidence.

**Derived Change**:
A Policy Change that follows mechanically from another, such as a premium recalculation after a coverage increase. Visible on a timeline, never counted as material. Premium and agent changes are always derived for our purposes.
_Avoid_: cascading change, system change

**Endorsement**:
The set of Policy Changes committed together in one transaction. A grouping for display and for answering "wasn't that really one customer interaction?" — never the unit that counts are denominated in.

**Change Category**:
Which aspect of the policy a change touched. The five material categories plus premium and agent. Renewal is a Timeline Event, never a Policy Change.

### Events

**Timeline Event**:
Anything dated that happened to a policy — a Policy Change, a Claim being filed, a payment, a renewal. The contents of a policy's story.

**Claim**:
A reported loss against a policy, filed against exactly one Coverage Line and settled at a single amount.

**Severity Band**:
Which of four fixed dollar ranges a Claim's settled amount falls into — minor, moderate, severe, catastrophic.

**High-Severity Claim**:
A Claim in the severe or catastrophic band. The product's own definition; never improvised from a dollar figure.

**Limit Utilisation**:
A Claim's settled amount as a proportion of the limit on the Coverage Line it was filed against. A separate axis from Severity Band — a modest claim can exhaust a modest limit.

**Loss Date**:
When the loss actually occurred. The default anchor for product language about timing.
_Avoid_: incident date, date of loss (in prose)

**Report Date**:
When the loss was reported to the insurer. Distinct from Loss Date, and the gap between them is itself analytically interesting.

**Linked Claim**:
For a given Policy Change, the first Claim on that policy reported at or after the change. Several changes may share one Linked Claim; that is intended.
_Avoid_: next claim, subsequent claim

**Loss-to-Report Gap**:
The interval between a Claim's Loss Date and its Report Date. A Policy Change falling inside this gap was made after the loss occurred but before the insurer knew of it.

**Change Timing**:
Where a Policy Change sits relative to its Linked Claim — either before the loss, or inside the Loss-to-Report Gap. Undefined for a change with no Linked Claim.

### Investigation

**Investigation**:
A user's line of enquiry — an opening question, the results, and the follow-ups that refine it. The unit of work in the product.

**Noteworthy Pattern**:
A named, documented, deterministic rule that a policy's history matches. Always explainable as a rule, never as a score or a judgment.
_Avoid_: risk score, anomaly, red flag

**Investigation Candidate**:
A policy surfaced as worth a human look. Carries no assertion about the policyholder.
_Avoid_: suspicious policy, fraudulent, flagged customer

**Control Population**:
Policies deliberately generated to have changes without claims, or claims without preceding changes. Present so the product cannot imply that changing a policy predicts a claim.

**Similar History**:
Two policies are similar when their behavioural histories are close — change rates, category mix, claim severity and matched Noteworthy Patterns — never when their demographics match. Similarity is directional: a policy being among another's nearest neighbours does not imply the reverse.

**Recent**:
Within the last 90 days, unless the user states a window. Always measured from today at the moment the question is asked, never stored.

**Comparison Group**:
The policies a cohort is measured against — typically those without the characteristic being investigated. A rate is never reported without one.

## Flagged ambiguities

None outstanding.

## Example dialogue

**Dev:** The customer raised their coverage on the 19th and the premium moved the same day. That's two changes before the claim, right?

**Expert:** One. The premium move is a Derived Change — nobody decided it, the rating engine did. If you count it, then every coverage increase looks like two decisions and "three material changes in a month" stops meaning anything.

**Dev:** But it still shows on the timeline?

**Expert:** It should. An adjuster wants to see the premium moved. They just don't want it inflating the count.

**Dev:** And this one — coverage went up on the 19th, the loss was on the 15th, reported the 22nd.

**Expert:** That's the interesting one. The change is after the loss but before it was reported. It's still the Linked Claim, because linkage runs off the Report Date. What tells you it's unusual is that the change landed inside the loss-to-report gap.

**Dev:** Do we call that out as a red flag?

**Expert:** We call it a Noteworthy Pattern and we name the rule that fired. The policy becomes an Investigation Candidate. We don't say anything about the person.
