# Roadmap

Where the project stands, and what the first production release requires. Items are ordered by dependency within each section, not scheduled. Dates are deliberately absent until a release date is fixed ([spec 04](./specs/04-implementation-plan.md) §8).

## Current state

| Area | State |
|---|---|
| Product capabilities | All five built: policy history, change-before-claim, portfolio patterns, similar histories, claim review |
| Data | The seeded reference dataset of 8,000 personal auto policies. No real source is connected |
| Semantic layer | Six gold tables, twenty enforced expectations, authored Unity Catalog comments |
| Genie | Space authored as code, fifteen query contracts at three of three |
| Access control | On-behalf-of-user. Unity Catalog governs all policy data. The review record mirrors it in the app |
| Environments | One: development, on a Free Edition workspace |
| Automated checks | Unit suites for generator, pipeline, backend and frontend, run locally. One GitHub Actions workflow, for diagrams. Live suites run by hand |
| Operations | Daily job. No alerting. One known issue, listed in [`operations.md`](./operations.md#known-issues) |

## 1. Environments and delivery

1. **Parameterise workspace identifiers.** The Genie space id, warehouse id, catalog name and Lakebase project id are literals with development values in `databricks.yml`, `app/app.yaml`, `genie/build_space.py` and `ci/genie/config.py`. Make them per-target bundle variables with one source of truth.
2. **Add `staging` and `prod` bundle targets** on a standard workspace, in `mode: production`, deployed by a service principal and with `run_as` set to one. No person should own the gold tables, which also makes a plain `SELECT` revoke effective.
3. **A dedicated catalog** per environment in place of `workspace`. Supersede [ADR-0016](./adr/0016-the-catalog-follows-medallion-schemas.md) when the names are chosen.
4. **Continuous integration for the unit suites.** Generator, pipeline, backend, frontend tests and lint on every pull request. They already run offline in seconds.
5. **Continuous delivery.** Bundle validate on pull request, deploy to staging on merge, promote to production behind the release gate.
6. **Automate the release gate** as a job that runs chips, contracts, the branch smoke test and the Brief contract against staging, and publishes the results.
7. **Bring the Genie space under the same promotion path.** It is not a bundle resource, so space creation, update and the `CAN_RUN` grant need a scripted step per environment.

## 2. Source data onboarding

The product's value in production is the insurer's own policy history. The pipeline already expects SCD Type 2 policy and coverage history plus claims, in the shape specified in [spec 01](./specs/01-data-model-and-synthetic-data.md) §3.

1. **Identify the source system and its extract path** into `ptm_bronze`. Lakeflow Connect or an existing lakehouse feed is preferred over a custom loader.
2. **Map the source to the bronze contract**, and record every gap. Known areas to check: coverage modelled per line, a usable transaction grouping for Endorsements, separate Loss Date and Report Date, a single settled amount per claim ([ADR-0005](./adr/0005-personal-auto-only-with-coverage-lines.md), [ADR-0004](./adr/0004-claim-linkage-is-anchored-on-report-date.md), [ADR-0008](./adr/0008-severity-bands-are-fixed-with-limit-utilisation-as-a-second-axis.md)).
3. **Incremental processing.** The pipeline full-refreshes today, which is right for a regenerated dataset and wrong for a growing one.
4. **Re-examine the policy id contract.** The app detects policy ids in typed questions with a fixed pattern that the generator guarantees ([ADR-0007](./adr/0007-generic-rendering-with-input-side-policy-detection.md)). Real identifiers need their own pattern and their own collision check.
5. **Keep the reference dataset as the test fixture.** Genie contracts and the Brief contract assert against planted ground truth, which real data cannot provide. Run them against a reference-data schema in every environment.
6. **Rewrite the disclosure.** The fixed sentence in the charter describes synthetic data. With real data the boundary stays the same, association and never prediction, but the wording needs its own review.
7. **Recalibrate or retire seeded-signal validation** for the real-data path. Effect-size checks belong to the generator only.

## 3. Security, privacy and governance

1. **Data classification and PII handling.** Real policy data carries personal data. Decide which columns reach `ptm_gold`, apply column masks or exclusions, and confirm what Genie and the model endpoint may see.
2. **Row-level access** if reviewers should see only their own book. Unity Catalog row filters fit the existing on-behalf-of-user model without app changes.
3. **Revisit the review record's access model.** Briefs live in Lakebase under the app's service principal, and the app mirrors the viewer's Unity Catalog access ([ADR-0019](./adr/0019-the-review-record-is-app-owned-and-mirrors-unity-catalog.md)). Decide whether that gate is sufficient for production or whether per-viewer Postgres roles are now worth their cost.
4. **Model endpoint governance.** Choose the production endpoint, confirm data-processing terms for claim data, and put it behind AI Gateway for rate limits, usage tracking and payload logging.
5. **Retention.** Set retention for Briefs, Dispositions, run records and MLflow traces. A Brief is a record of what the data showed when it was built and is never silently rebuilt, so it may carry regulatory weight.
6. **Audit.** Confirm that system tables capture Genie and warehouse activity per viewer, and that a Disposition's author and time are tamper-evident enough for the business.
7. **Security review** of the app, the scratch SQL tool's guardrails, and the bundle's permissions.

## 4. Reliability and operations

1. **Fix the nightly Brief task's missing Genie space id**, and make the task report failure when no Run completes.
2. **Alerting** on job failure, expectation failure, zero completed nightly Runs, and orphaned Working Branches.
3. **Concurrency.** Runs are serialised by a process lock because of a Free Edition compute limit. On a standard workspace, decide the concurrency limit and move the lock out of process if the app scales beyond one instance.
4. **Service objectives.** Define targets for timeline latency, Genie answer latency and Run duration, and measure them.
5. **Cost controls.** Warehouse sizing and auto-stop, Genie and model usage budgets, the nightly cap.
6. **Backup and recovery** for the Lakebase review record, which is the only state that cannot be regenerated.
7. **Runbooks** for the procedures in [`operations.md`](./operations.md), exercised at least once in staging.

## 5. Product

Deferred by earlier decisions, and worth revisiting with real users:

- Lines of business beyond personal auto ([ADR-0005](./adr/0005-personal-auto-only-with-coverage-lines.md))
- Incurred-versus-paid claim development ([ADR-0008](./adr/0008-severity-bands-are-fixed-with-limit-utilisation-as-a-second-axis.md))
- Additional Routing Rules beyond the single current one
- Responsive layout ([spec 06](./specs/06-ux-specification.md) §6)
- Usability testing with the two personas in [spec 10](./specs/10-personas-and-jobs.md)

## Open decisions

| Decision | Needed for |
|---|---|
| Release date | Turning this document and spec 04 §6 into a schedule |
| Production workspace, catalog and schema names | Section 1 |
| Source system and owner | Section 2 |
| Who may see which policies | Section 3, items 1 to 3 |
| Production model endpoint | Section 3, item 4 |
