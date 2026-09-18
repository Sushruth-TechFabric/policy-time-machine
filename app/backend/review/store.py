"""The review record on Lakebase main, plus an in-memory twin for tests.

Every state transition the harness makes on main goes through here, so
the "no partial Brief on main" guarantee (ADR-0017) is a property of
`complete_run` being the only writer of `review.brief`, inside one
transaction with the run and claim updates.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Callable

try:  # psycopg is only needed by ReviewStore; the in-memory twin must import without it
    import psycopg

    _DROPPED_CONNECTION: tuple[type[BaseException], ...] = (psycopg.OperationalError,)
except ImportError:  # pragma: no cover - the app, the Workflow tasks and CI all have psycopg
    _DROPPED_CONNECTION = ()

DISPOSITION_OUTCOMES = ("closer_look", "nothing_noteworthy", "more_information")
MISSING = object()
STALE_RUN_SECONDS = 1200  # A Run's wall clock is capped at 180s + demo hold, branch TTL is 900s; 20 min is safely past both


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InMemoryReviewStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.claims: dict[str, dict] = {}
        self.runs: dict[str, dict] = {}
        self.briefs: dict[str, dict] = {}
        self.dispositions: dict[str, dict] = {}
        self.investigations: dict[str, str | None] = {}

    def upsert_routed_claim(self, claim: dict, routed_by: str, routing_rule: str | None) -> None:
        with self._lock:
            existing = self.claims.get(claim["claim_id"])
            row = {**claim, "routed_by": routed_by, "routing_rule": routing_rule,
                   "run_state": existing["run_state"] if existing else "queued",
                   "active_run_id": existing["active_run_id"] if existing else None,
                   "routed_at": existing["routed_at"] if existing else _now(), "updated_at": _now()}
            self.claims[claim["claim_id"]] = row

    def claim_run(self, claim_id: str, run_id: str) -> bool:
        with self._lock:
            row = self.claims.get(claim_id)
            if not row:
                return False
            if row["run_state"] in ("queued", "failed"):
                row.update(run_state="in_progress", active_run_id=run_id, updated_at=_now())
                return True
            if row["run_state"] == "in_progress":
                updated_at = datetime.fromisoformat(row["updated_at"])
                elapsed = (datetime.now(timezone.utc) - updated_at).total_seconds()
                if elapsed > STALE_RUN_SECONDS:
                    row.update(run_state="in_progress", active_run_id=run_id, updated_at=_now())
                    return True
            return False

    def start_run(self, run_id: str, claim_id: str) -> None:
        with self._lock:
            self.runs[run_id] = {"run_id": run_id, "claim_id": claim_id, "status": "running", "current_step": None,
                                 "step_count": 0, "branch_name": None, "trace_id": None, "failure": None,
                                 "started_at": _now(), "finished_at": None}

    def update_run(self, run_id: str, *, current_step=None, step_count=None, branch_name=None) -> None:
        with self._lock:
            run = self.runs[run_id]
            if current_step is not None: run["current_step"] = current_step
            if step_count is not None: run["step_count"] = step_count
            if branch_name is not None: run["branch_name"] = branch_name

    def complete_run(self, run_id, claim_id, brief: dict, anchor_date: str, trace_id: str | None) -> None:
        with self._lock:
            self.briefs[claim_id] = {"claim_id": claim_id, "run_id": run_id, "anchor_date": anchor_date,
                                     "built_at": _now(), "body": brief}
            self.runs[run_id].update(status="completed", trace_id=trace_id, finished_at=_now(), current_step="promoted")
            self.claims[claim_id].update(run_state="brief_ready", active_run_id=None, updated_at=_now())

    def fail_run(self, run_id, claim_id, failure: str) -> None:
        with self._lock:
            self.runs[run_id].update(status="failed", failure=failure, finished_at=_now())
            self.claims[claim_id].update(run_state="queued", active_run_id=None, updated_at=_now())

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            return dict(self.runs[run_id]) if run_id in self.runs else None

    def _queue_row(self, claim: dict) -> dict:
        return {**claim, "has_brief": claim["claim_id"] in self.briefs,
                "disposition": self.dispositions.get(claim["claim_id"])}

    def list_queue(self) -> list[dict]:
        with self._lock:
            rows = [self._queue_row(c) for c in self.claims.values()]
            return sorted(rows, key=lambda r: (r["report_date"], r["claim_id"]), reverse=True)

    def get_claim(self, claim_id: str) -> dict | None:
        with self._lock:
            claim = self.claims.get(claim_id)
            if not claim:
                return None
            brief = self.briefs.get(claim_id)
            run = self.runs.get(claim["active_run_id"]) if claim["active_run_id"] else None
            return {**claim, "brief": brief["body"] if brief else None,
                    "brief_anchor_date": brief["anchor_date"] if brief else None,
                    "brief_built_at": brief["built_at"] if brief else None,
                    "disposition": self.dispositions.get(claim_id), "active_run": dict(run) if run else None,
                    "last_run": self._last_run(claim_id)}

    def _last_run(self, claim_id: str) -> dict | None:
        """The most recent Run for this claim, whatever its outcome. A failed
        Run clears `active_run_id`, so this is the only way the view can say
        the last Run failed."""
        runs = [r for r in self.runs.values() if r["claim_id"] == claim_id]
        return dict(max(runs, key=lambda r: r["started_at"])) if runs else None

    def record_disposition(self, claim_id, outcome, note, recorded_by) -> dict:
        if outcome not in DISPOSITION_OUTCOMES:
            raise ValueError(f"unknown outcome {outcome!r}")
        with self._lock:
            if claim_id not in self.briefs:
                raise LookupError("no Brief for this claim yet")
            row = {"claim_id": claim_id, "outcome": outcome, "note": note, "recorded_by": recorded_by, "recorded_at": _now()}
            self.dispositions[claim_id] = row
            return dict(row)

    def pending_claims(self, limit: int) -> list[dict]:
        with self._lock:
            rows = [c for c in self.claims.values()
                    if c["claim_id"] not in self.briefs and c["claim_id"] not in self.dispositions
                    and c["run_state"] in ("queued", "failed")]
            return sorted(rows, key=lambda r: (r["report_date"], r["claim_id"]), reverse=True)[:limit]

    def create_investigation(self, investigation_id: str) -> None:
        with self._lock:
            self.investigations[investigation_id] = None

    def get_conversation(self, investigation_id: str):
        with self._lock:
            return self.investigations.get(investigation_id, MISSING)

    def set_conversation(self, investigation_id: str, conversation_id: str | None) -> None:
        with self._lock:
            self.investigations[investigation_id] = conversation_id


class ReviewStore:
    """psycopg-backed. The connection is autocommit; multi-statement
    transitions open an explicit transaction.

    Free Edition Lakebase scales the instance to zero and drops idle
    connections, so a process-wide connection is routinely dead by the next
    request. Callers that can re-dial (the app) pass a `reconnect` factory
    and every statement retries once on a dropped connection; callers whose
    process is short-lived (the Workflow tasks, the CI scripts) pass only
    `conn` and see the original error.
    """

    def __init__(self, conn, reconnect: Callable[[], Any] | None = None) -> None:
        self._conn = conn
        self._reconnect_factory = reconnect
        self._lock = threading.RLock()

    def _reconnect(self) -> bool:
        if self._reconnect_factory is None:
            return False
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001 - the connection is already gone
            pass
        self._conn = self._reconnect_factory()
        return True

    def _run(self, work):
        """One statement (or one transaction), re-dialled once if the
        connection was dropped. A dropped connection never committed, so
        replaying the whole transaction is safe."""
        with self._lock:
            if getattr(self._conn, "closed", False) and self._reconnect():
                return work()
            try:
                return work()
            except _DROPPED_CONNECTION:
                if not self._reconnect():
                    raise
                return work()

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        def work():
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                if cur.description is None:
                    return []
                cols = [d.name for d in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]
        return self._run(work)

    def _exec(self, sql: str, params: tuple = ()) -> int:
        def work():
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.rowcount
        return self._run(work)

    def upsert_routed_claim(self, claim: dict, routed_by: str, routing_rule: str | None) -> None:
        self._exec(
            """INSERT INTO review.routed_claim (claim_id, policy_id, coverage_line, loss_date, report_date,
                   settled_amount, severity_band, routed_by, routing_rule)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (claim_id) DO UPDATE SET routed_by = EXCLUDED.routed_by,
                   routing_rule = EXCLUDED.routing_rule, updated_at = now()""",
            (claim["claim_id"], claim["policy_id"], claim["coverage_line"], claim["loss_date"], claim["report_date"],
             claim["settled_amount"], claim["severity_band"], routed_by, routing_rule),
        )

    def claim_run(self, claim_id: str, run_id: str) -> bool:
        return self._exec(
            """UPDATE review.routed_claim SET run_state = 'in_progress', active_run_id = %s, updated_at = now()
               WHERE claim_id = %s AND (run_state IN ('queued', 'failed') OR (run_state = 'in_progress' AND updated_at < now() - make_interval(secs => %s)))""",
            (run_id, claim_id, STALE_RUN_SECONDS),
        ) == 1

    def start_run(self, run_id: str, claim_id: str) -> None:
        self._exec("INSERT INTO review.run (run_id, claim_id, status) VALUES (%s, %s, 'running')", (run_id, claim_id))

    def update_run(self, run_id: str, *, current_step=None, step_count=None, branch_name=None) -> None:
        self._exec(
            """UPDATE review.run SET current_step = COALESCE(%s, current_step),
                   step_count = COALESCE(%s, step_count), branch_name = COALESCE(%s, branch_name)
               WHERE run_id = %s""",
            (current_step, step_count, branch_name, run_id),
        )

    def complete_run(self, run_id, claim_id, brief: dict, anchor_date: str, trace_id: str | None) -> None:
        def work():
            with self._conn.transaction(), self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO review.brief (claim_id, run_id, anchor_date, body) VALUES (%s, %s, %s, %s::jsonb)
                       ON CONFLICT (claim_id) DO UPDATE SET run_id = EXCLUDED.run_id, anchor_date = EXCLUDED.anchor_date,
                       built_at = now(), body = EXCLUDED.body""",
                    (claim_id, run_id, anchor_date, json.dumps(brief, default=str)),
                )
                cur.execute("UPDATE review.run SET status='completed', trace_id=%s, finished_at=now(), current_step='promoted' WHERE run_id=%s",
                            (trace_id, run_id))
                cur.execute("UPDATE review.routed_claim SET run_state='brief_ready', active_run_id=NULL, updated_at=now() WHERE claim_id=%s",
                            (claim_id,))
        self._run(work)

    def fail_run(self, run_id, claim_id, failure: str) -> None:
        def work():
            with self._conn.transaction(), self._conn.cursor() as cur:
                cur.execute("UPDATE review.run SET status='failed', failure=%s, finished_at=now() WHERE run_id=%s", (failure[:500], run_id))
                cur.execute("UPDATE review.routed_claim SET run_state='queued', active_run_id=NULL, updated_at=now() WHERE claim_id=%s", (claim_id,))
        self._run(work)

    def get_run(self, run_id: str) -> dict | None:
        rows = self._rows("SELECT * FROM review.run WHERE run_id = %s", (run_id,))
        return rows[0] if rows else None

    def list_queue(self) -> list[dict]:
        rows = self._rows(
            """SELECT c.*, (b.claim_id IS NOT NULL) AS has_brief,
                      d.outcome AS d_outcome, d.note AS d_note, d.recorded_by AS d_by, d.recorded_at AS d_at
               FROM review.routed_claim c
               LEFT JOIN review.brief b ON b.claim_id = c.claim_id
               LEFT JOIN review.disposition d ON d.claim_id = c.claim_id
               ORDER BY c.report_date DESC, c.claim_id DESC""")
        return [self._with_disposition(r) for r in rows]

    @staticmethod
    def _with_disposition(r: dict) -> dict:
        disposition = None
        if r.get("d_outcome"):
            disposition = {"outcome": r["d_outcome"], "note": r["d_note"], "recorded_by": r["d_by"], "recorded_at": r["d_at"]}
        out = {k: v for k, v in r.items() if not k.startswith("d_")}
        out["disposition"] = disposition
        return out

    def get_claim(self, claim_id: str) -> dict | None:
        rows = self._rows(
            """SELECT c.*, b.body AS brief, b.anchor_date AS brief_anchor_date, b.built_at AS brief_built_at,
                      d.outcome AS d_outcome, d.note AS d_note, d.recorded_by AS d_by, d.recorded_at AS d_at
               FROM review.routed_claim c
               LEFT JOIN review.brief b ON b.claim_id = c.claim_id
               LEFT JOIN review.disposition d ON d.claim_id = c.claim_id
               WHERE c.claim_id = %s""", (claim_id,))
        if not rows:
            return None
        row = self._with_disposition(rows[0])
        row["active_run"] = self.get_run(row["active_run_id"]) if row.get("active_run_id") else None
        # A failed Run clears active_run_id, so the most recent Run is the
        # only way the view can say the last Run failed.
        last = self._rows("SELECT * FROM review.run WHERE claim_id = %s ORDER BY started_at DESC LIMIT 1", (claim_id,))
        row["last_run"] = last[0] if last else None
        return row

    def record_disposition(self, claim_id, outcome, note, recorded_by) -> dict:
        if outcome not in DISPOSITION_OUTCOMES:
            raise ValueError(f"unknown outcome {outcome!r}")
        if not self._rows("SELECT 1 FROM review.brief WHERE claim_id = %s", (claim_id,)):
            raise LookupError("no Brief for this claim yet")
        rows = self._rows(
            """INSERT INTO review.disposition (claim_id, outcome, note, recorded_by) VALUES (%s,%s,%s,%s)
               ON CONFLICT (claim_id) DO UPDATE SET outcome=EXCLUDED.outcome, note=EXCLUDED.note,
                   recorded_by=EXCLUDED.recorded_by, recorded_at=now()
               RETURNING claim_id, outcome, note, recorded_by, recorded_at""",
            (claim_id, outcome, note, recorded_by))
        return rows[0]

    def pending_claims(self, limit: int) -> list[dict]:
        return self._rows(
            """SELECT c.* FROM review.routed_claim c
               LEFT JOIN review.brief b ON b.claim_id = c.claim_id
               LEFT JOIN review.disposition d ON d.claim_id = c.claim_id
               WHERE b.claim_id IS NULL AND d.claim_id IS NULL AND c.run_state IN ('queued', 'failed')
               ORDER BY c.report_date DESC, c.claim_id DESC LIMIT %s""", (limit,))

    def create_investigation(self, investigation_id: str) -> None:
        self._exec("INSERT INTO review.investigation (investigation_id) VALUES (%s) ON CONFLICT DO NOTHING", (investigation_id,))

    def get_conversation(self, investigation_id: str):
        rows = self._rows("SELECT conversation_id FROM review.investigation WHERE investigation_id = %s", (investigation_id,))
        return rows[0]["conversation_id"] if rows else MISSING

    def set_conversation(self, investigation_id: str, conversation_id: str | None) -> None:
        self._exec("UPDATE review.investigation SET conversation_id = %s, updated_at = now() WHERE investigation_id = %s",
                   (conversation_id, investigation_id))
