"""The Claim Review Brief harness (ADR-0017, ADR-0018).

Fixed plan: claim -> branch -> sequence -> relevant changes -> question ->
Genie -> similar -> sentences -> promote -> delete branch. The model is
consulted at exactly three points (question, follow-up, sentences) and
never touches the plan, main, or the branch lifecycle.
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from .lakebase import BranchLifecycle, WorkingBranch
from .model import ModelClient, ModelOutputError, parse_json_object
from .prompts import LINE_NAMES, PROMPT_VERSION, SYSTEM, follow_up_prompt, question_prompt, sentence_prompt
from .questions import Situation, canonical_question, detect_situation, validate_question, window_days
from .schema import ensure_stage_tables
from .tools import BudgetExceeded, GenieTool, ScratchSql, WarehouseTools, stage
from .vocabulary import violations

SECTIONS = ("sequence", "relevant_changes", "frequency", "similar")
TITLES = {"sequence": "The sequence", "relevant_changes": "The relevant changes",
          "frequency": "How common this is", "similar": "Similar histories"}
MAX_GENIE_TURNS = 2
MAX_SENTENCE_TURNS = 3
MAX_SCRATCH_STATEMENTS = 8
PREVIEW_ROWS = 12


class Tracer(Protocol):
    def span(self, name: str, kind: str): ...
    def last_trace_id(self) -> str | None: ...


class NoopTracer:
    def span(self, name: str, kind: str):
        return nullcontext()

    def last_trace_id(self) -> str | None:
        return None


class MlflowTracer:
    def __init__(self, experiment: str) -> None:
        import mlflow
        self._mlflow = mlflow
        mlflow.set_tracking_uri("databricks")
        mlflow.set_experiment(experiment)

    @contextmanager
    def span(self, name: str, kind: str):
        from mlflow.entities import SpanType
        span_type = {"agent": SpanType.AGENT, "tool": SpanType.TOOL, "llm": SpanType.LLM}.get(kind, SpanType.UNKNOWN)
        with self._mlflow.start_span(name=name, span_type=span_type) as span:
            yield span

    def last_trace_id(self) -> str | None:
        return self._mlflow.get_last_active_trace_id()


class RunFailed(RuntimeError):
    pass


@dataclass
class RunDeps:
    store: Any
    warehouse: WarehouseTools
    genie: GenieTool
    model: ModelClient
    branches: BranchLifecycle
    connect_branch: Callable[[WorkingBranch], Any]
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    demo_hold_seconds: int = 0
    run_timeout_seconds: int = 180
    tracer: Tracer = field(default_factory=NoopTracer)


@dataclass
class RunOutcome:
    run_id: str
    claim_id: str
    status: str  # completed | failed | skipped
    failure: str | None
    brief: dict | None
    trace_id: str | None
    elapsed_seconds: float


def _preview(rows: list, limit: int = PREVIEW_ROWS) -> dict:
    return {"row_count": len(rows), "rows": rows[:limit]}


def _truthy(value) -> bool:
    return str(value).lower() in ("true", "1", "t", "yes")


class _Run:
    def __init__(self, claim_id: str, deps: RunDeps, run_id: str) -> None:
        self.claim_id, self.deps, self.run_id = claim_id, deps, run_id
        self.started = deps.clock()
        self.step_count = 0
        self.branch: WorkingBranch | None = None
        self.conn = None
        self.claim: dict = {}

    # -- bookkeeping -------------------------------------------------------
    def step(self, label: str, *, tool: str | None = None, sql: str | None = None, row_count: int | None = None, payload: dict | None = None) -> None:
        self.step_count += 1
        self.deps.store.update_run(self.run_id, current_step=label, step_count=self.step_count)
        if self.conn is not None:
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO review.run_step (step, tool, sql, row_count, elapsed_ms, payload) VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
                    (label, tool, sql, row_count, int((self.deps.clock() - self.started) * 1000),
                     json.dumps(payload or {}, default=str)),
                )
        self.check_timeout()

    def check_timeout(self) -> None:
        if self.deps.clock() - self.started > self.deps.run_timeout_seconds:
            raise RunFailed(f"Run timed out after {self.deps.run_timeout_seconds}s")

    def model_json(self, user: str, name: str) -> dict:
        with self.deps.tracer.span(name, "llm"):
            text = self.deps.model.complete(SYSTEM, user)
        return parse_json_object(text)

    # -- sections -----------------------------------------------------------
    def sequence(self) -> dict:
        with self.deps.tracer.span("sequence", "tool"):
            result = self.deps.warehouse.sequence(self.claim["policy_id"], self.claim["loss_date"])
        stage(self.conn, "stage_timeline", result.rows)
        self.step("sequence", tool="warehouse", sql=result.sql, row_count=result.row_count)
        changes = [r for r in result.rows if r.get("event_type") == "policy_change"]
        material = sum(1 for r in changes if _truthy(r.get("is_material")))
        return {"title": TITLES["sequence"], "rows": result.rows, "material_change_count": material,
                "derived_change_count": len(changes) - material, "sql": result.sql, "row_count": result.row_count}

    def relevant(self) -> tuple[dict, Situation, list[dict], list[dict]]:
        with self.deps.tracer.span("relevant_changes", "tool"):
            rel = self.deps.warehouse.relevant_changes(self.claim["policy_id"], self.claim_id)
            pat = self.deps.warehouse.pattern_matches(self.claim["policy_id"], self.claim_id)
        stage(self.conn, "stage_relevant_changes", rel.rows)
        stage(self.conn, "stage_patterns", pat.rows)
        situation = detect_situation(rel.rows, pat.rows)
        self.step("relevant_changes", tool="warehouse", sql=rel.sql, row_count=rel.row_count, payload={"situation": situation.value})
        section = {"title": TITLES["relevant_changes"], "rows": rel.rows, "patterns": pat.rows,
                   "situation": situation.value, "sql": rel.sql, "row_count": rel.row_count}
        return section, situation, rel.rows, pat.rows

    def frequency(self, situation: Situation, rel_rows: list[dict], pat_rows: list[dict]) -> dict:
        line = self.claim.get("coverage_line", "")
        window = window_days(rel_rows)
        context = {"policy_id": self.claim["policy_id"], "coverage_line": line, "line_name": LINE_NAMES.get(line, line),
                   "window_days": window, "relevant_changes": rel_rows[:5],
                   "patterns": [p.get("pattern_name") for p in pat_rows], "severity_band": self.claim.get("severity_band")}
        proposal, rejection, source = None, None, "model"
        for attempt in range(2):
            try:
                candidate = self.model_json(question_prompt(situation.value, context, rejection), "choose_question")
            except ModelOutputError as exc:
                rejection = str(exc)
                continue
            rejection = validate_question(situation, candidate)
            if rejection is None:
                proposal = candidate["question"]
                break
        if proposal is None:
            source = "canonical"
            proposal = canonical_question(situation, coverage_line=line, line_name=LINE_NAMES.get(line, line),
                                          window=window, pattern_name=(pat_rows[0].get("pattern_name") if pat_rows else None))
        self.step("question_chosen", tool="model", payload={"question": proposal, "source": source, "rejection": rejection})

        with self.deps.tracer.span("genie", "tool"):
            conversation_id, result = self.deps.genie.ask(proposal)
        if result.status != "ok":
            raise RunFailed(f"Genie could not answer the frequency question ({result.status}): {result.error or result.description or ''}")
        genie_turns, follow_up, final = 1, None, result
        self.step("genie_answered", tool="genie", sql=result.generated_sql, row_count=len(result.rows))

        if genie_turns < MAX_GENIE_TURNS:
            try:
                decision = self.model_json(follow_up_prompt(proposal, {"columns": [c["name"] for c in result.columns], "rows": result.rows[:PREVIEW_ROWS]}), "follow_up")
            except ModelOutputError:
                decision = {"follow_up": None}
            follow_up = decision.get("follow_up")
            if isinstance(follow_up, str) and follow_up.strip() and not violations(follow_up):
                with self.deps.tracer.span("genie_follow_up", "tool"):
                    _, second = self.deps.genie.ask(follow_up.strip(), conversation_id=conversation_id)
                genie_turns += 1
                if second.status == "ok":
                    final = second
                self.step("genie_follow_up", tool="genie", sql=second.generated_sql, row_count=len(second.rows), payload={"status": second.status})
            else:
                follow_up = None

        columns = [c["name"] for c in final.columns]
        stage(self.conn, "stage_frequency", [dict(zip(columns, row)) for row in final.rows])
        return {"title": TITLES["frequency"], "shape": situation.value, "question": proposal, "question_source": source,
                "follow_up": follow_up, "columns": columns, "rows": final.rows, "sql": final.generated_sql,
                "row_count": len(final.rows), "genie_status": final.status, "description": final.description}

    def similar(self) -> dict:
        with self.deps.tracer.span("similar", "tool"):
            result = self.deps.warehouse.similar(self.claim["policy_id"])
        stage(self.conn, "stage_similar", result.rows)
        self.step("similar", tool="warehouse", sql=result.sql, row_count=result.row_count)
        return {"title": TITLES["similar"], "rows": result.rows, "sql": result.sql, "row_count": result.row_count}

    def sentence(self, name: str, section: dict, scratch: ScratchSql) -> None:
        preview = _preview(section["rows"])
        history: list[dict] = []
        sentence, reason = None, None
        for _ in range(MAX_SENTENCE_TURNS):
            try:
                reply = self.model_json(sentence_prompt(name, preview, history, self.claim["policy_id"]), f"sentence_{name}")
            except ModelOutputError as exc:
                reason = f"model output: {exc}"
                break
            if isinstance(reply.get("sql"), str):
                try:
                    out = scratch.run(reply["sql"])
                except BudgetExceeded as exc:
                    reason = f"scratch SQL budget: {exc}"
                    break
                history.append({"sql": reply["sql"], **out})
                self.step(f"scratch_sql_{name}", tool="scratch_sql", sql=reply["sql"], row_count=out.get("row_count"))
                continue
            candidate = reply.get("sentence")
            if not isinstance(candidate, str) or not candidate.strip():
                reason = "no sentence returned"
                break
            bad = violations(candidate, self.claim["policy_id"])
            if bad:
                reason = f"vocabulary: {', '.join(bad)}"
            else:
                sentence = candidate.strip()
            break
        else:
            reason = "sentence turns exhausted"
        section["sentence"] = sentence
        section["sentence_dropped"] = sentence is None
        section["sentence_dropped_reason"] = reason
        self.step(f"sentence_{name}", tool="model", payload={"dropped": sentence is None, "reason": reason})

    # -- the plan -----------------------------------------------------------
    def execute(self) -> dict:
        self.claim = self.deps.warehouse.claim(self.claim_id) or {}
        if not self.claim:
            raise RunFailed(f"claim {self.claim_id} not found in claim_event")
        self.branch = self.deps.branches.create(self.run_id)
        self.deps.store.update_run(self.run_id, branch_name=self.branch.branch_name)
        self.conn = self.deps.connect_branch(self.branch)
        ensure_stage_tables(self.conn)
        self.step("branch_created", tool="lakebase", payload={"branch": self.branch.branch_name})

        sections: dict[str, dict] = {}
        sections["sequence"] = self.sequence()
        rel_section, situation, rel_rows, pat_rows = self.relevant()
        sections["relevant_changes"] = rel_section
        sections["frequency"] = self.frequency(situation, rel_rows, pat_rows)
        sections["similar"] = self.similar()

        scratch = ScratchSql(self.conn, max_statements=MAX_SCRATCH_STATEMENTS)
        for name in SECTIONS:
            self.sentence(name, sections[name], scratch)

        return {"claim_id": self.claim_id, "policy_id": self.claim["policy_id"], "coverage_line": self.claim.get("coverage_line"),
                "loss_date": str(self.claim.get("loss_date")), "report_date": str(self.claim.get("report_date")),
                "anchor_date": self.deps.warehouse.anchor_date(), "built_at": datetime.now(timezone.utc).isoformat(),
                "run_id": self.run_id, "prompt_version": PROMPT_VERSION, "sections": sections}

    def teardown(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:  # noqa: BLE001
                pass
        if self.branch is not None:
            if self.deps.demo_hold_seconds > 0:
                self.deps.store.update_run(self.run_id, current_step="demo_hold")
                self.deps.sleep(self.deps.demo_hold_seconds)
            self.deps.branches.delete(self.branch)
            self.deps.store.update_run(self.run_id, current_step="branch_deleted")


def run_brief(claim_id: str, deps: RunDeps, run_id: str | None = None) -> RunOutcome:
    run_id = run_id or uuid.uuid4().hex[:12]
    started = deps.clock()
    if not deps.store.claim_run(claim_id, run_id):
        return RunOutcome(run_id, claim_id, "skipped", "a Run is already in progress for this claim", None, None, 0.0)
    deps.store.start_run(run_id, claim_id)
    run = _Run(claim_id, deps, run_id)
    brief: dict | None = None
    failure: str | None = None
    trace_id: str | None = None
    try:
        with deps.tracer.span(f"claim_review_brief:{claim_id}", "agent"):
            brief = run.execute()
    except (RunFailed, BudgetExceeded, ModelOutputError) as exc:
        failure = str(exc)
    except Exception as exc:  # noqa: BLE001 - any other failure is still "Run failed", never a crash
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        trace_id = deps.tracer.last_trace_id()
        try:
            if brief is not None and failure is None:
                deps.store.complete_run(run_id, claim_id, brief, anchor_date=brief["anchor_date"], trace_id=trace_id)
        except Exception as exc:  # noqa: BLE001 - promotion failing is a Run failure
            failure, brief = f"promotion failed: {exc}", None
        try:
            run.teardown()
        except Exception as exc:  # noqa: BLE001 - branch cleanup failure must not mask the outcome; TTL is the backstop
            failure = failure or f"branch cleanup failed: {exc}"
        if failure is not None:
            deps.store.fail_run(run_id, claim_id, failure)
    status = "completed" if failure is None else "failed"
    return RunOutcome(run_id, claim_id, status, failure, brief if status == "completed" else None, trace_id, deps.clock() - started)
