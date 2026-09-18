# The agent works on a disposable Lakebase branch; only the Brief comes back

Each Run of the Claim Review Brief agent forks a Working Branch of the Lakebase review database, does all of its writes there, and is terminated by deleting the branch. The harness, not the agent, copies the finished Brief and a compact run record to the main branch through its own connection. Nothing else crosses back. Failed Runs promote nothing; the Routed Claim stays in the queue.

We chose this over a `run_id` column on main because the branch is what lets the agent be given real write freedom. On its branch the agent has a scratch SQL tool: it stages the timeline rows, the Genie result rows and the similarity neighbours as tables and queries across them to write its sentences. Arbitrary SQL from a language model is acceptable when the blast radius is a copy-on-write fork that will be deleted in a minute. On main it would not be.

We rejected syncing the six gold tables into Lakebase so the fork carries the semantic layer: it makes Genie bypassable, which undercuts the product's Genie-powered framing, and synced tables combined with branching was untested.

Lakebase branches fork and never merge. Promotion is therefore an explicit copy of a small, fixed set of rows, and the full step log dies with the branch. MLflow tracing is the durable record of what the agent did.

## Consequences

- The harness must own two connections per Run: one to the branch for the agent's tools, one to main for promotion. The agent never sees the main connection.
- A half-written Brief can never exist on main. Every reader of the review record can assume Briefs are complete.
- Branch creation and deletion are on the critical path of every Run, so branch lifecycle failures are Run failures and need their own handling.
- Retrying a failed Run means a fresh branch, never resuming the old one. Work done on a failed branch is lost by design.
- Anyone auditing a Run after the fact goes to the MLflow trace, not to Lakebase.
