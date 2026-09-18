# The harness owns the plan; the model owns the question

The Claim Review Brief agent runs a fixed plan. The harness executes the four Brief sections in a fixed order, makes the deterministic tool calls itself (timeline, Relevant Changes, Similar Histories), enforces the tool allowlist, the step and time budget, one Working Branch per Run, the vocabulary check on every generated sentence, promotion of the finished Brief, and the stop before Disposition. The model decides two things: which portfolio question to ask Genie in the frequency section, with at most one narrowing follow-up in the same conversation, and the wording of one factual sentence per section, written with scratch SQL over the tables it staged on its branch.

We chose this over letting the model order the tools, or over an open ReAct loop, because the product's boundary (no scores, no characterisation of a person, every claim traceable to a named rule) has to be structural. A harness that validates prose after an open loop is enforcing the charter by inspection; a harness that only ever lets the model choose a question and a sentence is enforcing it by construction. The cost is that the agent looks less autonomous than it could. That is the correct trade for a product whose primary persona is accountable for what she writes in a file.

The model's one real decision is analytically meaningful, and it is drawn from a fixed menu of four question shapes, one per situation the harness can detect from the deterministic sections: a Relevant Change inside the Loss-to-Report Gap (how often same-line changes land inside the gap versus before the loss); a Relevant Change before the loss (how often a same-line increase within the observed number of days precedes a High-Severity Claim, the window being the model's visible choice); no Relevant Change but a matched Noteworthy Pattern (how common that rule is among policies with High-Severity Claims versus without); and nothing before the loss at all (what share of High-Severity Claims had no Material Change in the prior year, the Control Population question). A question matching none of the four is rejected by the harness. The narrowing follow-up is free-form within the same Genie conversation.

## Consequences

- Every Brief has the same shape. Renderers, tests and the Disposition control can rely on it.
- Run-to-run variance lives entirely in section three and in the sentences. Query contracts for the deterministic sections apply unchanged.
- The vocabulary check runs at generation time, not in the pipeline, because expectation E18 cannot see runtime text. A sentence that fails is dropped and the section says so; the Brief is never rejected for it.
- Adding a section is a harness change and a Brief-shape change, never a prompt change.
- "Agentic" in this product means the choice of question, and the demo should say so rather than imply the model planned the review.
