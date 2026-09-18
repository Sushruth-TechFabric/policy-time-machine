"""Assembles real dependencies and runs the harness — sequentially from
the Workflow (work_queue) or in one background thread per claim from the
app (RunRegistry). Runs are never concurrent across claims either: the
registry serialises through a process lock, because Free Edition allows
one non-default Lakebase branch with compute at a time."""

from __future__ import annotations

import threading
from typing import Any

from databricks.sdk import WorkspaceClient

from ..config import REVIEW_DEMO_HOLD_SECONDS, REVIEW_MLFLOW_EXPERIMENT, REVIEW_MODEL_ENDPOINT, REVIEW_RUN_TIMEOUT_SECONDS
from .harness import MlflowTracer, NoopTracer, RunDeps, RunOutcome, run_brief
from .lakebase import BranchLifecycle, connect_branch
from .model import FoundationModelClient
from .tools import GenieTool, WarehouseTools


def _tracer():
    if not REVIEW_MLFLOW_EXPERIMENT:
        return NoopTracer()
    try:
        return MlflowTracer(REVIEW_MLFLOW_EXPERIMENT)
    except Exception:  # noqa: BLE001 - tracing is observability, never a reason to fail a Run
        return NoopTracer()


def build_deps(client: WorkspaceClient, store: Any, *, demo_hold_seconds: int | None = None, tracer=None) -> RunDeps:
    return RunDeps(
        store=store,
        warehouse=WarehouseTools(client),
        genie=GenieTool(client),
        model=FoundationModelClient(client, REVIEW_MODEL_ENDPOINT),
        branches=BranchLifecycle(client),
        connect_branch=lambda wb: connect_branch(client, wb),
        demo_hold_seconds=REVIEW_DEMO_HOLD_SECONDS if demo_hold_seconds is None else demo_hold_seconds,
        run_timeout_seconds=REVIEW_RUN_TIMEOUT_SECONDS,
        tracer=tracer or _tracer(),
    )


def work_queue(deps: RunDeps, cap: int) -> list[RunOutcome]:
    outcomes: list[RunOutcome] = []
    for claim in deps.store.pending_claims(cap):
        outcome = run_brief(claim["claim_id"], deps)
        print(f"[build_briefs] {claim['claim_id']}: {outcome.status} in {outcome.elapsed_seconds:.1f}s"
              + (f" — {outcome.failure}" if outcome.failure else ""), flush=True)
        outcomes.append(outcome)
    return outcomes


class RunRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._serial = threading.Lock()  # one Run at a time, process-wide
        self._threads: dict[str, threading.Thread] = {}
        self._run_ids: dict[str, str] = {}

    def is_running(self, claim_id: str) -> bool:
        with self._lock:
            t = self._threads.get(claim_id)
            return bool(t and t.is_alive())

    def run_id_for(self, claim_id: str) -> str | None:
        with self._lock:
            return self._run_ids.get(claim_id) if self.is_running_unlocked(claim_id) else None

    def is_running_unlocked(self, claim_id: str) -> bool:
        t = self._threads.get(claim_id)
        return bool(t and t.is_alive())

    def start(self, claim_id: str, deps: RunDeps) -> str | None:
        import uuid
        with self._lock:
            if self.is_running_unlocked(claim_id):
                return None
            run_id = uuid.uuid4().hex[:12]

            def target():
                with self._serial:
                    run_brief(claim_id, deps, run_id=run_id)

            thread = threading.Thread(target=target, name=f"run-{run_id}", daemon=True)
            self._threads[claim_id] = thread
            self._run_ids[claim_id] = run_id
            thread.start()
            return run_id

    def join(self, claim_id: str, timeout: float | None = None) -> None:
        t = self._threads.get(claim_id)
        if t:
            t.join(timeout)


registry = RunRegistry()
