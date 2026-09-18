# Frontend

The React frontend of the Policy Time Machine Databricks App. Built with Vite, tested with Vitest, linted with Oxlint. The FastAPI backend in `../backend` serves the built output from `dist/`.

```bash
npm install
npm run dev      # :5173, proxies /api to the backend on :8000
VITE_MOCK=1 npm run dev   # no backend: canned, deterministic responses from src/api/mockData.js
npm test         # vitest, jsdom
npm run lint
npm run build    # writes dist/, which is what the bundle uploads
```

Layout under `src/`:

| Path | Contents |
|---|---|
| `api/` | The backend client, and the mock fixtures behind `VITE_MOCK=1` |
| `hooks/` | Investigation state, including tabs and the trail |
| `components/` | The investigation workspace, evidence drawer, charts, timeline, and `review/` for the Brief panel, Run panel and Disposition form |
| `views/` | The Review view |
| `lib/` | Result-row normalisation and helpers |

Design and interaction rules are in [`../../docs/specs/06-ux-specification.md`](../../docs/specs/06-ux-specification.md). See [`../../docs/development.md`](../../docs/development.md) for running the whole app locally.
