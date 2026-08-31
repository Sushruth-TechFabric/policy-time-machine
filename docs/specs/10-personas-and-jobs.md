# Personas and Jobs to Be Done

One primary persona. Two secondary ones, listed because they shape a few decisions and because knowing who we are *not* building for is what keeps the surface small.

---

## Primary — the claims investigator

**Dana, Senior Claims Examiner.** Nine years in personal auto. Reviews claims that get routed for a closer look — high value, unusual circumstances, or an adjuster's instinct. Reads policy documents fluently, has never written SQL, and has a BI dashboard she uses for exactly two saved views.

Today, when she wants to know what changed on a policy before a loss, she requests an extract. It arrives in two to four days as a spreadsheet of policy versions with effective dates, and she reconstructs the story by eye. Most of the time she skips it, because the reconstruction costs more than the answer is usually worth.

What she brings that the product must respect: she already knows that a raised limit before a claim is usually nothing. Renewals, life events and agent advice all move limits. She is not looking for a system that flags — she is looking for one that *shows her the sequence* so she can apply the judgement she already has.

### Jobs

**J1.** When a claim is routed to me for review, I want to see the policy's material changes in the months before the loss, so I can judge whether the sequence warrants a closer look.

**J2.** When I see a coverage increase before a claim, I want to know whether it was on the line that was actually claimed against, so I can tell a real finding from a coincidence.

**J3.** When something looks unusual, I want to know how unusual it is across the portfolio, so I am not reacting to a pattern that happens to everyone.

**J4.** When I have seen one case like this, I want to find the others, so I can tell whether it is a one-off or a shape worth raising.

### What she must never be given

A score. A flag that asserts intent. Any wording that characterises the policyholder. She is accountable for what she writes in a file, and a tool that hands her a conclusion she cannot trace is a liability rather than an aid — which is why every pattern is a named rule with a stated definition and visible evidence.

---

## Secondary — the operations analyst

**Marcus, Portfolio Operations.** Watches book-level behaviour. Wants to know which kinds of change are becoming more common, whether recent-change populations behave differently from stable ones, and where to point the team's attention.

**J5.** When reviewing the book, I want to compare policies with recent material changes against those without, so I can see whether the populations differ.

**J6.** When I see a difference between groups, I want the comparison group and the sample sizes shown alongside, so I can tell whether the difference means anything.

Marcus is the reason comparison outputs *always* carry both groups and their `n` (ADR-0014). He is also the persona most at risk of over-reading a synthetic effect, which is why the disclosure is front-loaded rather than buried.

---

## Secondary — the data engineer

**Priya, Analytics Engineering.** Not a user of the investigation surface. She is the person who currently receives Dana's extract requests, and the person who would be asked to verify a finding before anyone acts on it.

**J7.** When someone brings me a finding from this tool, I want to see the query that produced it, so I can verify it without rebuilding the analysis.

Priya is why the evidence drawer shows the generated SQL rather than hiding it as a debug affordance. Her job is the reason a trail of five questions and five queries is a feature.

---

## Non-users

Named so the product does not drift toward them.

- **Underwriters.** Would want forward-looking risk assessment. The product is retrospective and says nothing about future risk.
- **SIU / fraud investigators.** Would want scoring, case management and referral workflow. Serving them would require exactly the assertions the product refuses to make.
- **Executives.** Would want a KPI landing page. The app opens on an input bar and three starter chips (`06-ux-specification.md` §6).

---

## Job-to-capability map

| Job | Capability | Contracts |
|---|---|---|
| J1 | Individual policy history | QC-01, QC-02 |
| J2 | Change-before-claim, coverage-line aware | QC-03, QC-07 |
| J3 | Portfolio patterns | QC-05, QC-06, QC-13, QC-14 |
| J4 | Similar histories | QC-11 |
| J5 | Comparison | QC-10 |
| J6 | Comparison, both groups with n | QC-10 negative assertion |
| J7 | Evidence drawer | Not a query contract; app test |

Every job maps to a capability, and every capability to a tested contract. A job with no contract is a job we are only claiming to serve.
