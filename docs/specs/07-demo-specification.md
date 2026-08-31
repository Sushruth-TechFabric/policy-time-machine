# Demo Specification

Beat by beat. Written in **relative language** throughout — "nineteen days before the claim", never "January 19th" — because the dataset regenerates against a moving anchor (ADR-0006).

Target length: five minutes. Recorded, because Databricks Apps has no public access and a judge may never reach a live instance (ADR-0012).

---

## 1. Opening frame (20s)

State the problem before the product.

> Insurance systems keep years of policy history. Answering "what changed before this claim?" means joining across policy versions with window functions and effective dates. Analysts don't do it, so the history goes unexamined.

Then the disclosure, up front rather than under questioning (ADR-0014):

> The dataset is synthetic. Investigation-worthy patterns are deliberately seeded at declared, documented effect sizes — this demonstrates how historical patterns are surfaced and investigated, not that policy changes predict claims.

Front-loading this converts the sharpest available question into evidence of rigour.

---

## 2. Beat one — the cohort (45s)

Type: **"Show policies where coverage increased within 30 days before a claim."**

Genie answers. The result table fills the right panel. Open the evidence drawer and leave it open for three seconds.

> Genie wrote that. Note what it didn't have to write — no window function, no effective-date join. The temporal relationship is already in the semantic layer, so the question is a filter.

This is the beat that earns the architecture. Do not rush the evidence drawer.

---

## 3. Beat two — the timeline (60s)

Click the top result. The timeline opens on the left.

Walk the spine: address change, then the collision limit increase, then the vehicle change, then the claim. Point at the endorsement-grouped card.

> Those two happened in one endorsement — one customer interaction, two field changes. We count it as one decision, which is why "three material changes in a month" means something here.

Then the second axis:

> The claim is $24,700. That's the moderate band. But it's 97% of a limit raised nine weeks earlier — and that's a different finding from a large claim on a large limit.

---

## 4. Beat three — multi-turn (30s)

Type, without repeating context: **"which of these had a claim near the new limit?"**

The cohort narrows. This is the single moment that proves Genie is holding conversation state (ADR-0011), and it has its own contract, QC-15, so it is a tested property rather than a hope.

---

## 5. Beat four — similarity (40s)

Type: **"Find policies with histories similar to this one."**

Twenty neighbours return with `top_reasons` visible.

> Similar means the behaviour matched — change velocity, category mix, which patterns fired. Not that they live in the same city. And it tells you why, which an embedding could not.

---

## 6. Beat five — the portfolio, honestly (45s)

Type: **"Which material changes happen most frequently before high-severity claims?"**

A ranked chart returns: coverage first, deductible second, address near baseline.

Then immediately: **"Compare policies with recent material changes against those without."**

Two groups, both with sample sizes.

> 8.5% against 5.8%. Both groups shown, always. And the control population is real — policies that changed and never claimed, claims with nothing before them. The product surfaces patterns for a human to investigate. It does not tell you someone did something wrong.

This beat is where an investigation tool distinguishes itself from a scoring engine. Deliver the caveat as the point, not as a disclaimer.

---

## 7. Close (30s)

Show the breadcrumb trail — five questions across the top of the screen.

> That's the investigation. Five questions, five queries, every one auditable. The analyst never learned the schema.

Then one line on the platform: Genie over a curated temporal layer in Unity Catalog, built by a declarative pipeline where every temporal invariant is an enforced expectation, deployed as an Asset Bundle you can run in your own workspace.

---

## 8. Rehearsal rules

1. **Forward-only.** Never click a breadcrumb backwards during a typed follow-up — the Genie thread is linear and cannot be rewound, and the divergence is documented but must stay off stage (ADR-0011).
2. **Regenerate, then rehearse.** Every beat depends on planted scenarios; run the query contract suite after regeneration and before recording.
3. **Relative language only** in the script and voiceover.
4. **The evidence drawer opens at least twice.** It is the fastest proof that the semantics are real rather than narrated.
5. **Never say fraud.** Not once, not casually, not as a joke about what the tool doesn't do.

---

## 9. Fallback

If Genie is slow or fails during recording, the timeline still renders — it never blocks on Genie. Re-record the beat rather than editing around it; a visible retry is better than a cut that hides how the product behaves.
