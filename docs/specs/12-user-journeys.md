# User Journeys

Four journeys, one per capability, written as what actually happens on screen. Each names the requirements it exercises and the contract that proves it.

Dates are relative throughout — the dataset regenerates against a moving anchor.

---

## Journey 1 — Dana reviews a routed claim

**Job J1, J2. Requirements FR-07 … FR-12, FR-16. Contracts QC-02, QC-03.**

A claim lands on Dana's desk: collision, just under $25,000, on a policy she has never seen.

She types **"What changed on P-18492 before this claim?"**

Two things happen at once, and neither waits for the other. The app finds one policy identifier in her question and opens the timeline on the left from its own query. Genie receives the question and begins working; the right panel shows a skeleton.

The timeline resolves first. Four events on a spine: an address change, then a collision-limit increase from $100,000 to $300,000, then a vehicle change, then the claim. The limit increase and the address change share a card — one endorsement, two deltas — so she can see it was a single interaction rather than two decisions.

Genie's result arrives beside it: the same changes as rows, with the days between each and the loss.

She notices the claim is $24,700 against a $300,000 limit — but the timeline card for the claim says 97% of the *collision* limit at the time of loss, because the increase applied to a different line. That distinction is the difference between a finding and a coincidence, and she gets it without asking.

**What could go wrong, and doesn't:** if Genie times out, the timeline is still there. She has the sequence regardless (FR-08).

---

## Journey 2 — Dana checks whether it is unusual

**Job J3. Requirements FR-01, FR-02, FR-21. Contracts QC-03, QC-15, QC-10.**

The sequence looks noteworthy. Before she writes anything, she wants to know how common it is.

She types **"Show policies where coverage increased within 30 days before a claim."**

Forty-seven policies. She opens the evidence drawer — not because she reads SQL, but because she has been asked before how a number was produced, and she wants to know it exists.

Then, without repeating herself: **"which of these had a claim near the new limit?"**

The cohort narrows to nine. Genie resolved *these* against the previous turn. This is the moment the product stops feeling like a search box.

She follows with **"Compare policies with recent material changes against those without."**

Two rows come back, each with a rate and a count: 8.5% against 5.8%, with both populations sized. She reads that as *some difference, not a lot*, which is the correct reading — and it is the only reading available, because a single-group result is a contract failure (FR-21).

**The boundary in practice:** nothing on screen tells her the policy is a problem. She has a sequence, a frequency, and a comparison. The judgement stays hers.

---

## Journey 3 — Marcus reviews the book

**Job J5, J6. Requirements FR-17, FR-20, FR-21. Contracts QC-05, QC-06, QC-13, QC-14.**

Marcus opens the app to an input bar and three starter chips. No dashboard, no KPI row.

He types **"Which material changes happen most frequently before high-severity claims?"**

A ranked chart: coverage increases first, deductible decreases second, then vehicle, status, and address near baseline. He did not have to define *high-severity* — it means severe or catastrophic, and it means that everywhere (FR-17).

A chip offers **"Which policies match the coverage-raised-then-claimed pattern?"** He takes it. Policies come back, each carrying a named rule and a matched date rather than a score.

He clicks one. The timeline opens on the left; the cohort stays on the right. He is now in Journey 1 without having navigated anywhere.

**What he is protected from:** the ordering he saw is a designed property of the dataset, validated on every regeneration, and disclosed in the writeup. He is not reading noise, and he is not reading a discovery either.

---

## Journey 4 — Finding the shape again

**Job J4. Requirements FR-19. Contract QC-11.**

Dana has one case she understands. She wants the others.

From the open timeline she types **"Find policies with histories similar to this one."**

Twenty policies, ranked, each with its reasons in plain language — *comparable change velocity; coverage increase preceding a same-line claim; both in the top decile for material changes per year.* Not a similarity score alone: the dimensions that drove it, because they are named features rather than an embedding (ADR-0010).

She clicks the third. Its timeline replaces the first. The trail across the top now reads: *coverage up before claims › P-18492 › similar policies › P-20114*. Clicking back two steps restores the cohort instantly, without asking Genie anything again.

**The limit, surfaced rather than hidden:** she asks for fifty and gets twenty, with the cap stated. Twenty is what was computed; the product says so rather than improvising.

---

## Journey 5 — When it goes wrong

**Requirements FR-06, FR-09, FR-15.**

Three failures, and what each looks like.

**A typo'd identifier.** She types P-18499, which does not exist. The left panel says so explicitly. The right panel still shows whatever Genie made of the question. She sees a mistake, not a broken product (FR-09).

**Genie cannot answer.** The result panel states it plainly, the timeline stays open and usable, and *new investigation* appears beneath the message (FR-06).

**A thread that has gone in circles.** Genie asks a clarifying question, then another. The reset is offered on each — because escaping a poisoned thread requires noticing it, and the escape belongs exactly where the poisoning happens.

---

## Coverage

| Journey | Capability | Contracts |
|---|---|---|
| 1 | Individual policy history | QC-01, QC-02 |
| 2 | Change-before-claim, comparison | QC-03, QC-10, QC-15 |
| 3 | Portfolio patterns | QC-05, QC-06, QC-13, QC-14 |
| 4 | Similar histories | QC-11 |
| 5 | Failure states | App tests |
