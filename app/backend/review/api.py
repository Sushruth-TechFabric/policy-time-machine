"""/api/review/* — the review record and on-demand Runs (design spec §9.1).

Lakebase access is app identity (ADR-0019). The one viewer-identity read
is the claim lookup on the warehouse when a Brief is requested on demand,
so a viewer without gold access gets `no_access` rather than a Brief."""

from __future__ import annotations

from databricks.sdk import WorkspaceClient
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..config import CATALOG, SCHEMA
from ..deps import _app_client, get_client, viewer_identity
from ..warehouse import WarehouseError, WarehousePermissionError, run_query
from .context import get_review_store
from .runner import build_deps, registry
from .store import DISPOSITION_OUTCOMES

router = APIRouter(prefix="/api/review")

_LOOKUP_SQL = f"""
SELECT claim_id, policy_id, coverage_line, CAST(loss_date AS STRING) AS loss_date,
       CAST(report_date AS STRING) AS report_date, settled_amount, severity_band
FROM {CATALOG}.{SCHEMA}.claim_event WHERE claim_id = :claim_id
""".strip()


def lookup_claim(client: WorkspaceClient, claim_id: str) -> dict | None:
    rows = run_query(client, _LOOKUP_SQL, {"claim_id": claim_id})
    return rows[0] if rows else None


class DispositionRequest(BaseModel):
    outcome: str
    note: str | None = None


@router.get("/queue")
def queue() -> dict:
    return {"queue": get_review_store().list_queue()}


@router.get("/claims/{claim_id}")
def claim_detail(claim_id: str) -> dict:
    detail = get_review_store().get_claim(claim_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"no routed claim {claim_id}")
    return detail


@router.post("/claims/{claim_id}/brief")
def prepare_brief(claim_id: str, client: WorkspaceClient = Depends(get_client)) -> dict:
    store = get_review_store()
    try:
        claim = lookup_claim(client, claim_id)
    except WarehousePermissionError:
        return {"no_access": True}
    except WarehouseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if claim is None:
        raise HTTPException(status_code=404, detail=f"no claim {claim_id}")
    if store.get_claim(claim_id) is None:
        store.upsert_routed_claim({**claim, "settled_amount": float(claim["settled_amount"])}, routed_by="on_demand", routing_rule=None)
    run_id = registry.start(claim_id, build_deps(_app_client(), store))
    if run_id is None:
        return {"run_id": registry.run_id_for(claim_id), "started": False, "reason": "in_progress"}
    return {"run_id": run_id, "started": True, "reason": None}


@router.get("/runs/{run_id}")
def run_status(run_id: str) -> dict:
    run = get_review_store().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"no run {run_id}")
    return run


@router.post("/claims/{claim_id}/disposition")
def record_disposition(claim_id: str, body: DispositionRequest, request: Request) -> dict:
    if body.outcome not in DISPOSITION_OUTCOMES:
        raise HTTPException(status_code=400, detail=f"outcome must be one of {DISPOSITION_OUTCOMES}")
    who = viewer_identity(request) or "local-user"
    try:
        return get_review_store().record_disposition(claim_id, body.outcome, body.note, who)
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
