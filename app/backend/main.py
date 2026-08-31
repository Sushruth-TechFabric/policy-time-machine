"""Policy Time Machine — task zero deploy-envelope smoke test.

Minimal FastAPI app: serves the built React static bundle from `/`
and a JSON health check from `/api/health`. Binds to
$DATABRICKS_APP_PORT (falling back to 8000 for local runs).
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Policy Time Machine")

APP_ROOT = Path(__file__).resolve().parent.parent  # .../app
STATIC_DIR = APP_ROOT / "frontend" / "dist"


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("DATABRICKS_APP_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
