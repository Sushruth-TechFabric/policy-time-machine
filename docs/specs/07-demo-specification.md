# Demo Specification

Beat by beat. Written in **relative language** throughout — "nineteen days before the claim", never "January 19th" — because the dataset regenerates against a moving anchor (ADR-0006).

Target length: six minutes. Recorded, because Databricks Apps has no public access and a judge may never reach a live instance (ADR-0012). If the submission demands a five-minute cut, beats 2 and 7 compress first; beats 3–6 are the product and do not.

Every typed question in this script is the exact phrasing of a passing query contract (spec 05). The demo asks nothing that is not already tested at 3/3.

---

## 1. Opening frame — the problem and who it serves (30s)

State the problem before the product. Voiceover over the architecture slide (diagram 1), then cut to the app.

> Insurance systems keep years of policy history and almost never use it. Every coverage change, deductible change, vehicle swap and address move is retained — but the analytics built on top answer only one question: what does this policy look like *now*? The moment a claims professional asks "what changed before this claim?", the work becomes SCD Type 2 joins, effective-date intervals and window functions. So the question goes to an engineer, or it goes unasked.

> Policy Time Machine puts that history in reach of the people whose job it is to understand it. It supports four investigations: the story of one policy, changes before claims, patterns across the portfolio, and policies with similar histories. A claims professional reviewing a single claim and an operations analyst studying the whole book use the same screen and the same plain-English questions.

Then the disclosure, up front rather than under questioning (ADR-0014):

> The dataset is synthetic — no real data, no PII. Investigation-worthy patterns are deliberately seeded at declared, documented effect sizes — this demonstrates how historical patterns are surfaced and investigated, not that policy changes predict claims.

Front-loading this converts the sharpest available question into evidence of rigour.

---

## 2. Beat one — the landing screen: capabilities and the data (40s)

Open on the app. The landing screen *is* the capabilities slide — do not build a separate one. Read the flow diagram aloud left to right, then gesture across the five capability cards.

> Your question goes to an AI analyst — Databricks Genie — which writes SQL against your policy data and returns the answer with evidence. Five things this workbench does: spot changes before claims, follow a policy's story, compare cohorts fairly, find similar histories, and verify every answer.

Then one breath on the data, because a judge should know what Genie is standing on:

> Underneath is a medallion lakehouse in Unity Catalog. Raw SCD Type 2 history lands in bronze; a declarative pipeline with twenty enforced expectations conforms it; and Genie sees exactly six curated gold tables where the temporal relationships — days from a change to the next claim, whether a change touched the coverage line later claimed against — are pre-computed, verified columns. Genie never reinvents temporal SQL; it filters.

The dataset includes deliberate control populations — policies that changed and never claimed, claims with nothing before them — so a rate can never appear without its comparison group. Mention this here in one sentence; beat six pays it off.

---

## 3. Beat two — the cohort (45s)

Type: **"Show policies where coverage increased within 30 days before a claim."** (QC-03)

The working card shows the question being processed; the result lands as the first turn of the conversation, table with the chart beside it. Expand the evidence panel — *Evidence: N rows · view query* — and leave it open for three seconds.

> Genie wrote that SQL. Note what it didn't have to write — no window function, no effective-date join. The temporal relationship is already a column in the semantic layer, so the question is a filter. Every answer in this product carries its evidence: the generated SQL, how the question was read, and the row count. You can copy it and run it yourself.

This is the beat that earns the architecture. Do not rush the evidence panel.

---

## 4. Beat three — the timeline (60s)

Click the top result. The policy's timeline opens on the left; the conversation stays on the right. Note in passing that the timeline is the app's own deterministic query — it renders instantly and never waits on Genie.

Walk the spine: address change, then the collision limit increase, then the vehicle change, then the claim. Point at the endorsement-grouped card.

> Those two happened in one endorsement — one customer interaction, two field changes. We count it as one decision, which is why "three material changes in a month" means something here.

Then the second axis:

> The claim is $24,700. That's the moderate band. But it's 97% of a limit raised nine weeks earlier — and that's a different finding from a large claim on a large limit.

Pattern markers on the spine get one sentence: each names a documented rule that fired — a Noteworthy Pattern, never a score.

---

## 5. Beat four — multi-turn (30s)

Type, without repeating context: **"which of these had a claim near the new limit?"** (QC-15, turn two)

The new turn appends below the first — the investigation reads as a running conversation, every earlier answer still on screen. The cohort narrows. This is the single moment that proves Genie is holding conversation state (ADR-0011), and it has its own contract, so it is a tested property rather than a hope.

---

## 6. Beat five — similarity (35s)

Click **Find similar policies →** on the timeline itself — the question comes from the product, not from memory.

Neighbours return ranked, with `top_reasons` visible in the result.

> Similar means the behaviour matched — change velocity, category mix, which patterns fired. Not that they live in the same city. And it tells you why each one matched, which an embedding could not.

Use case, in one line: this is how a review of one policy becomes a review of the cohort that behaves like it.

---

## 7. Beat six — the portfolio, honestly (50s)

Type: **"Which material changes most often precede high-severity claims, within 60 days?"** (QC-05)

A ranked chart returns: coverage first, deductible second, address near baseline.

Then immediately: **"Compare policies with recent material changes against policies without."** (QC-10)

The comparison renders as paired small multiples — each group's rate beside its sample size, always both.

> 8.5% against 5.8%. Both groups shown, always, with their sizes. And the control population is real — policies that changed and never claimed, claims with nothing before them. The product surfaces patterns for a human to investigate. It does not tell you someone did something wrong.

This beat is where an investigation tool distinguishes itself from a scoring engine. Deliver the caveat as the point, not as a disclaimer.

---

## 8. Beat seven — parallel investigations (25s)

Open a new tab with **+**. The first investigation stays live — its full conversation, timeline and evidence intact. Double-click the first tab and give it a working name.

> Real investigation work is not one thread. Each tab is its own Genie conversation; switching never resets anything, and the trail survives a refresh. An analyst runs the claim review in one tab and the portfolio question in another.

Keep this beat brisk — it demonstrates maturity, not a headline capability.

---

## 9. Close (30s)

Return to the first tab. Scroll the conversation top to bottom, then point at the numbered trail across the top.

> That's the investigation. Five questions, five queries, every one auditable — and the analyst never learned the schema.

Then one line on the platform, naming the native services deliberately:

> Everything you saw is Databricks-native: Genie over six curated gold tables in Unity Catalog, built by a Lakeflow declarative pipeline where every temporal invariant is an enforced expectation, regenerated on a schedule by Workflows, served by a Databricks App, and deployed as one Asset Bundle you can run in your own workspace and reproduce this demo.

---

## 10. Rehearsal rules

1. **The thread is linear.** Trail clicks are cached scroll-backs, never a rewind of the Genie conversation — so never phrase a follow-up as though an earlier turn were the latest one. The divergence is documented but must stay off stage (ADR-0011).
2. **Regenerate, then rehearse.** Every beat depends on planted scenarios; run the query contract suite after regeneration and before recording, and record against that same dataset (spec 08 §7 — the recording and the tested dataset must be the same dataset).
3. **Contract phrasings only.** The typed questions above are tested verbatim; do not improvise wording on camera.
4. **Relative language only** in the script and voiceover.
5. **The evidence panel opens at least twice.** It is the fastest proof that the semantics are real rather than narrated.
6. **Never say fraud.** Not once, not casually, not as a joke about what the tool doesn't do. The approved vocabulary governs the voiceover as strictly as it governs the UI.

---

## 11. Fallback

If Genie is slow or fails during recording, the timeline still renders — it never blocks on Genie, and the working card shows the product handling the wait honestly. Re-record the beat rather than editing around it; a visible retry is better than a cut that hides how the product behaves.
