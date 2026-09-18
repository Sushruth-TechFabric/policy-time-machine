# Contributing

## Before you start

1. Read [`CONTEXT.md`](./CONTEXT.md). The vocabulary is part of the product, and some of it is enforced.
2. Read [`docs/architecture.md`](./docs/architecture.md), then the specification and decision records for the area you are changing.
3. Set up locally with [`docs/development.md`](./docs/development.md).

## Workflow

1. Branch from `main`. Keep a branch to one change.
2. Write the test first where the change is a rule. In the pipeline, a rule that protects data also gets an expectation.
3. Run the suites for what you touched. All of them run offline:
   ```bash
   app/.venv/bin/python -m pytest generator/tests
   (cd pipeline && .venv/bin/python -m pytest)
   (cd app && .venv/bin/python -m pytest backend/tests)
   (cd app/frontend && npm test && npm run lint)
   ```
4. If you changed Genie instructions, Unity Catalog comments, a gold schema or the agent's prompts, run the matching live suite and say so in the pull request. See [`docs/operations.md`](./docs/operations.md#release-gate).
5. Open a pull request that says what changed and why, and links the spec or ADR it implements.

## Rules that are easy to break

- **Approved vocabulary only.** Never "fraud", "suspicious", "red flag", "risk score" or similar, in UI copy, Genie content, agent prompts, comments that reach Unity Catalog, or demo scripts. The pipeline fails on it. The product describes a policy's history and names the rule that fired. It never characterises a person.
- **A rate never appears without its comparison group and sample sizes.**
- **Counts are of Material Changes.** Derived changes show on a timeline and are never counted.
- **The timeline never depends on Genie.**
- **The agent restates facts and never weighs them.** A Disposition is always a human's act.
- **Relative dates** in anything a user or an audience reads.
- **No secrets in the repo.** Authentication is the Databricks CLI profile locally and platform identity when deployed.

## Documentation

| Change | Update |
|---|---|
| Behaviour | The relevant spec in [`docs/specs/`](./docs/specs/README.md) |
| A decision, or a reversed one | A new ADR in [`docs/adr/`](./docs/adr), numbered next in sequence. Supersede, never rewrite |
| A new term | [`CONTEXT.md`](./CONTEXT.md), with what to avoid calling it |
| Configuration or a deploy step | [`docs/deployment.md`](./docs/deployment.md) |
| A new failure mode or procedure | [`docs/operations.md`](./docs/operations.md) |
| A diagram | The `.mmd` source and its verbatim copy in the embedding spec, then re-render the SVG and run `bash ci/render-diagrams.sh` ([how](./docs/development.md#conventions)) |

## Commits

Imperative, specific subject lines that say what the change does, for example "Gate the claim detail read on the viewer's warehouse access".
