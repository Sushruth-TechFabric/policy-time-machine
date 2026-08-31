"""Policy Time Machine — FastAPI backend (task P5).

Serves the built React static bundle from `/` and the `/api/*`
endpoints the frontend is coded against (see the API contract in the
task brief). The app is a thin client over Genie and two deterministic
queries (ADR-0012): Genie answers questions, the app owns the
policy-scoped timeline/similar/patterns drilldowns and never lets a
Genie failure take the rest of the response down with it (ADR-0007).
"""

import os
from pathlib import Path
from typing import Any

from databricks.sdk import WorkspaceClient
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .chips import chips_for_context
from .deps import get_client
from .genie import ask_genie
from .investigations import InvestigationNotFoundError, store
from .policy_ids import detect_policy_ids, resolve_timeline_policy_id
from .queries import get_patterns, get_similar, get_timeline
from .warehouse import WarehouseError

app = FastAPI(title="Policy Time Machine")

APP_ROOT = Path(__file__).resolve().parent.parent  # .../app
STATIC_DIR = APP_ROOT / "frontend" / "dist"


class MessageRequest(BaseModel):
    question: str


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/investigations")
def create_investigation() -> dict:
    investigation_id = store.create()
    return {"investigation_id": investigation_id}


@app.post("/api/investigations/{investigation_id}/messages")
def post_message(investigation_id: str, body: MessageRequest, client: WorkspaceClient = Depends(get_client)) -> dict:
    try:
        conversation_id = store.get_conversation_id(investigation_id)
    except InvestigationNotFoundError:
        raise HTTPException(status_code=404, detail=f"no investigation {investigation_id}")

    detected_ids = detect_policy_ids(body.question)
    timeline_policy_id = resolve_timeline_policy_id(detected_ids)

    new_conversation_id, genie_result = ask_genie(client, conversation_id, body.question)
    store.set_conversation_id(investigation_id, new_conversation_id)

    return {
        "detected_policy_ids": detected_ids,
        "timeline_policy_id": timeline_policy_id,
        "genie": genie_result.to_dict(),
    }


@app.get("/api/policies/{policy_id}/timeline")
def policy_timeline(policy_id: str, client: WorkspaceClient = Depends(get_client)) -> dict:
    events = _run_deterministic(get_timeline, client, policy_id)
    return {"found": len(events) > 0, "events": events}


@app.get("/api/policies/{policy_id}/similar")
def policy_similar(policy_id: str, client: WorkspaceClient = Depends(get_client)) -> dict:
    neighbours = _run_deterministic(get_similar, client, policy_id)
    return {"neighbours": neighbours}


@app.get("/api/policies/{policy_id}/patterns")
def policy_patterns(policy_id: str, client: WorkspaceClient = Depends(get_client)) -> dict:
    patterns = _run_deterministic(get_patterns, client, policy_id)
    return {"patterns": patterns}


@app.get("/api/chips")
def chips(context: str = Query(...)) -> dict:
    return {"chips": chips_for_context(context)}


def _run_deterministic(fn, client: WorkspaceClient, policy_id: str) -> list[dict[str, Any]]:
    """Run a deterministic warehouse read, turning failures into a clean
    HTTP error instead of a crash (VERIFY: timeline may 502 locally
    without tables — that's fine, it must not take the process down).
    """
    try:
        return fn(client, policy_id)
    except WarehouseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("DATABRICKS_APP_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
