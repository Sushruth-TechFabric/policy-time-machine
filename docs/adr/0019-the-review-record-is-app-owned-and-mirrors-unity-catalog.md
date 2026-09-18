# The review record is app-owned and mirrors Unity Catalog rather than enforcing its own access

The Lakebase review database (Routed Claims, Runs, Briefs, Dispositions, the investigation-to-conversation map) is accessed with the app's own identity and the Workflow's run-as identity. Viewers never connect to Lakebase. A Disposition records who made it from the viewer identity the platform forwards, but the write is the app's. In the Review view, the Brief panel goes quiet whenever the on-behalf-of timeline read beside it reports no access, so a viewer revoked in Unity Catalog does not read gold-derived facts through a Brief.

This deliberately departs from the product's existing rule that Unity Catalog is the single enforcement point (OBO access-control design, 2026-08-31). We considered on-behalf-of Postgres roles per viewer, which would keep the rule intact, and rejected it: it needs per-user role provisioning, a second thing to revoke on camera, and depends on the forwarded app token being acceptable as a Postgres credential, which was unverified. At this stage the cost outweighs the consistency; the decision is revisited if per-viewer Postgres roles become practical.

The honest framing, and the one the demo uses: Unity Catalog governs the source; the Brief is a derivative record the app owns; the app mirrors the source's answer. The mirror is a gate in the app, not enforcement in the platform, and the docs say so rather than imply otherwise.

## Consequences

- The governance beat still holds on screen: one revoke empties answers, timelines and Briefs on the same refresh.
- A reader auditing access must know that Briefs are readable by the app identity regardless of any viewer's grants. The data path is app to Lakebase, never viewer to Lakebase.
- If the product ever needed real per-viewer isolation of the review record, this decision is the one to revisit, most likely with per-viewer Postgres roles or row-level security keyed on the forwarded identity.
- Working Branch creation and deletion are always the harness's act under app identity, in every entry point.
