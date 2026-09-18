# On-Behalf-Of-User Access Control — Design

Date: 2026-08-31
Status: approved

## Problem

The app authenticates every request as its own service principal (`deps.get_client`), so any viewer who can reach the app sees all policy data — Genie answers, evidence re-runs, and the deterministic timeline/similar/patterns drilldowns alike. The requirement: a viewer without access to the underlying data gets **no results**, enforced for real, and demonstrable on camera from a single workspace account.

A secondary question answered during brainstorming: is the dataset complex enough to carry the demo? **Verdict: yes, unchanged.** 8,000 policies over three years of SCD2 history, six planted noteworthy scenarios plus five control populations at declared effect sizes, two-axis severity, and fifteen query contracts tested at 3/3. No data curation ships with this change; this paragraph documents that decision.

## Approach

On-behalf-of-user (OBO) authorization end-to-end. Databricks Apps injects the viewer's token as the `X-Forwarded-Access-Token` request header when the app declares user-authorization scopes. The backend builds the per-request `WorkspaceClient` from that token, so **Unity Catalog grants are the single enforcement point** — the app adds no authorization logic of its own.

Rejected alternatives:

- **OBO + row filters** (viewer sees only their book): richer story, but needs a region→group mapping, extra UC setup, and a second identity to read well on camera. Out of scope for this iteration.
- **App-level "view as" toggle**: trivial to demo, but cosmetic — not enforcement.

## Components

### `app/app.yaml`

Declare user-authorization scopes so the platform forwards the viewer token: `dashboards.genie` (Genie conversation API) and `sql` (warehouse execution for evidence re-runs and drilldowns). If the current Databricks Apps docs name these scopes differently at implementation time, the docs win; the requirement is fixed — the two APIs above must execute as the viewer.

### `app/backend/deps.py`

`get_client` becomes a per-request dependency:

- If `X-Forwarded-Access-Token` is present → `WorkspaceClient` authenticated with that token (viewer identity).
- Else → the existing cached app-identity client (local dev and the test suite are unchanged).

No other module's signature changes; `genie.py`, `warehouse.py`, and `queries.py` keep receiving a `WorkspaceClient`.

### Error interpretation → `no_access` status

A viewer without SELECT surfaces as permission errors from two directions: Genie message failures and warehouse `PERMISSION_DENIED` responses. Both map to a new result status `"no_access"` alongside the existing `ok | empty | error | clarification` set, carrying a fixed friendly message — never the raw grant error text. Detection matches on the platform's permission-denied error codes/markers, not on loose substrings.

The deterministic endpoints (timeline, similar, patterns) get the same mapping: permission-denied → an empty payload with a `no_access` marker, not a 500. This closes the leak where Genie would deny but the timeline would still render.

### Frontend

`ResultPanel` renders `no_access` as its own quiet state, styled like the existing empty/error states: "You don't have access to the policy data behind this workbench. Ask your workspace admin for access to the gold tables." Timeline and similar/patterns panels show the same state. No retry buttons, no error styling — access absence is a fact, not a fault.

## Demo (single account)

A governance beat (~25s) in the demonstration script (`docs/specs/13-meetup-demo-specification.md`, Chapter 4):

1. Precondition, done once before recording: `ptm_gold`'s owner is **not** the demo user (transfer ownership to the app's service principal); the demo user holds a direct `GRANT SELECT`. A UC owner cannot lock themselves out, so ownership transfer is what makes single-account revocation demoable.
2. On camera: run `REVOKE SELECT` on the gold schema → refresh the app → the same screen, every panel in the no-access state → `GRANT SELECT` back → results return.
3. Voiceover line: access is enforced by Unity Catalog, not by the app — same screen, no data, because governance says so.

The demonstration script gains this beat; the query-contract suite still runs as the granted user before recording, per existing rehearsal rules.

## Testing

- `deps`: header present → client built from viewer token; header absent → app-identity fallback.
- `genie`/`warehouse` interpretation: permission-denied error → `no_access` status with the fixed message; other errors unchanged.
- Deterministic endpoints: permission-denied → `no_access` payload, not a 500.
- Existing tests and the contract suite pass unchanged (they use the fallback path).

## Out of scope

Row filters, column masks, per-user data partitioning, any change to the generator, pipeline, or Genie space content.
