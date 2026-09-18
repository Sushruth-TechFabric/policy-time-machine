# Documentation

Start with the glossary, [`../CONTEXT.md`](../CONTEXT.md). Every document here uses its vocabulary precisely.

## Guides

| Document | Purpose |
|---|---|
| [`architecture.md`](./architecture.md) | How the system fits together: data flow, components, identity and access, the review agent |
| [`development.md`](./development.md) | Local setup, running the app, running every test suite, working with the Genie space |
| [`deployment.md`](./deployment.md) | The Asset Bundle, environments, configuration, one-time grants, first deploy |
| [`operations.md`](./operations.md) | The scheduled job, the release gate, health checks, known failure modes and what to do about them |
| [`roadmap.md`](./roadmap.md) | Current state, and what the first production release requires |
| [`genie-curation.md`](./genie-curation.md) | How the Genie space is curated, measured against Databricks' own guidance |

## Reference

| Location | Purpose |
|---|---|
| [`specs/`](./specs/README.md) | Product and technical specifications, with a reading order. *What* the system does |
| [`adr/`](./adr) | Architecture decision records. *Why* each decision was made, including the alternatives rejected |
| [`diagrams/`](./diagrams) | Mermaid sources with rendered SVGs. Each source is embedded verbatim in a spec, and CI fails if they drift |
| [`superpowers/`](./superpowers) | Dated design documents and implementation plans for individual features. A record of how each feature was built, not living documentation |

## Conventions

- **Specifications state what; decision records state why.** A change in behaviour updates the spec. A change in reasoning adds or supersedes an ADR. ADRs are never rewritten to hide a reversed decision.
- **The vocabulary is enforced.** Words such as "fraud", "suspicious" or "red flag" fail the pipeline if they reach a user-facing string, and the same list governs documentation and demo scripts.
- **Relative dates in anything a user or an audience sees.** The reference dataset regenerates against a moving anchor ([ADR-0006](./adr/0006-dataset-is-anchored-to-generation-date.md)), so "nine weeks earlier" stays true and a calendar date does not.
