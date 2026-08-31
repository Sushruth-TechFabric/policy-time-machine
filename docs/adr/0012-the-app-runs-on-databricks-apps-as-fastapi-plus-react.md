# The app runs on Databricks Apps as a FastAPI backend serving a built React frontend

Policy Time Machine is hosted natively on Databricks Apps. A FastAPI backend serves a pre-built React bundle and exposes `/api/*` endpoints; the platform runs `npm install` and `npm run build` at deploy. Node.js and hybrid frontend-plus-Python-backend architectures are officially supported, so this is a documented pattern rather than an escape hatch.

Streamlit would have been faster to a running demo, but the timeline, the investigation trail and the evidence panel are custom interactive components, and ADR-0007 made the timeline the product's differentiator — rendering it through a third-party Streamlit component would make the signature element look like a dashboard widget. Dash offers roughly half the control for comparable effort. Hosting externally on Vercel would give the best UI freedom but hands us authentication, secret management and CORS, and removes the app from the platform in an ecosystem-judged competition.

## Runtime contract

- Bind to `DATABRICKS_APP_PORT`. No port literals anywhere.
- Ubuntu 22.04, Python 3.11, Node.js 22.x; roughly 2 vCPU / 6 GB by default. The app is thin by design — Genie and the warehouse do the work — but the frontend build runs inside the same envelope, so lockfiles are pinned and the dependency tree stays lean or deploys become slow and flaky.
- 10 MB per-file limit, enforced at deploy. No bundled datasets, no large source maps, and the frontend bundle is code-split. The dataset lives in Delta tables regardless; this rule just forecloses a lazy shortcut.
- Secrets and OAuth stay server-side. The browser sees only our `/api/*` endpoints; the platform handles authentication to the warehouse and to Genie.

## Consequences

- **There is no anonymous or public access to a Databricks App.** Judges either receive workspace access or watch a recording. Both paths are planned for: the Asset Bundle makes reproduce-in-your-own-workspace real, and a recorded demo is the fallback. No part of the submission may assume a shareable public URL.
- **Implementation task zero is a deploy-envelope smoke test** — hello-world FastAPI plus a built React bundle, through the Asset Bundle, into Apps. Not because feasibility is in doubt, but because it validates the build pipeline, port binding and bundle wiring before any UI investment, and it produces the skeleton everything else lands in.
