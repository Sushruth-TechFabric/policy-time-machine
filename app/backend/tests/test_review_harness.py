"""The harness owns the plan (ADR-0018): section order, budgets, the
vocabulary drop, promotion only on success, branch deletion on both paths."""

import json
from contextlib import nullcontext

import pytest

import backend.review.harness as harness_module
from backend.genie import GenieResult
from backend.review.harness import RunDeps, run_brief
from backend.review.lakebase import WorkingBranch
from backend.review.store import InMemoryReviewStore
from backend.review.tools import ToolResult

CLAIM_ROW = {"claim_id": "C-1", "policy_id": "P-10155", "coverage_line": "COLL", "loss_date": "2026-08-01",
             "report_date": "2026-08-05", "settled_amount": "24700", "severity_band": "severe"}


class FakeWarehouse:
    def __init__(self, relevant=None, patterns=None):
        self._relevant = relevant if relevant is not None else [
            {"change_event_id": "E-1", "change_category": "coverage", "coverage_line": "COLL",
             "change_timing": "before_loss", "days_to_next_claim_loss": 63}]
        self._patterns = patterns or []
        self.calls = []
    def claim(self, claim_id): return dict(CLAIM_ROW)
    def anchor_date(self): return "2026-09-17"
    def sequence(self, policy_id, loss_date):
        self.calls.append("sequence")
        rows = [{"event_date": "2026-05-01", "event_type": "policy_change", "is_material": "true"},
                {"event_date": "2026-05-01", "event_type": "policy_change", "is_material": "false"},
                {"event_date": "2026-08-01", "event_type": "claim_filed", "is_material": "false"}]
        return ToolResult(rows, "SELECT seq", len(rows))
    def relevant_changes(self, policy_id, claim_id):
        self.calls.append("relevant"); return ToolResult(self._relevant, "SELECT rel", len(self._relevant))
    def pattern_matches(self, policy_id, claim_id):
        self.calls.append("patterns"); return ToolResult(self._patterns, "SELECT pat", len(self._patterns))
    def similar(self, policy_id, k=5):
        self.calls.append("similar")
        rows = [{"similar_policy_id": "P-20114", "rank": 1, "similarity_score": 0.9, "top_reasons": "comparable change velocity"}]
        return ToolResult(rows, "SELECT sim", 1)


class FakeGenie:
    def __init__(self, fail=False):
        self.fail = fail; self.questions = []
    def ask(self, question, conversation_id=None):
        self.questions.append((question, conversation_id))
        if self.fail:
            return conversation_id, GenieResult(status="error", error="boom")
        return "conv-1", GenieResult(status="ok", columns=[{"name": "group"}, {"name": "rate"}, {"name": "n"}],
                                     rows=[["with", "0.085", "400"], ["without", "0.058", "3600"]],
                                     generated_sql="SELECT genie", description="d")


class ScriptedModel:
    """Answers in order: question, follow-up, then per-section sentence turns."""
    def __init__(self, sentences=None, question=None):
        self.calls = []
        self.question = question or {"shape": "relevant_before_loss",
                                     "question": "How often does a collision limit increase within 90 days before a claim precede a high-severity claim, compared with increases not followed by one?"}
        self.sentences = sentences or {}
    def complete(self, system, user, *, max_tokens=800):
        self.calls.append(user)
        if "Choose the frequency question" in user:
            return json.dumps(self.question)
        if "narrowing follow-up" in user:
            return json.dumps({"follow_up": None})
        for section in ("sequence", "relevant_changes", "frequency", "similar"):
            if f'section "{section}"' in user:
                if "SCRATCH RESULT" not in user and section == "sequence" and self.sentences.get("sequence_sql"):
                    return json.dumps({"sql": self.sentences["sequence_sql"]})
                return json.dumps({"sentence": self.sentences.get(section, f"A factual {section} sentence.")})
        raise AssertionError(f"unexpected prompt: {user[:80]}")


class FakeBranches:
    def __init__(self): self.created = []; self.deleted = []
    def create(self, run_id):
        wb = WorkingBranch(run_id, f"projects/p/branches/run-{run_id}", f"projects/p/branches/run-{run_id}/endpoints/primary", "h")
        self.created.append(wb); return wb
    def delete(self, wb): self.deleted.append(wb)


class FakeBranchConn:
    """Records staged tables; scratch SELECTs return one row."""
    def __init__(self): self.executed = []
    def cursor(self):
        conn = self
        class Cur:
            description = None
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def execute(s, sql, params=None):
                conn.executed.append(sql)
                if sql.strip().upper().startswith("SELECT"):
                    s.description = [type("D", (), {"name": "c"})()]
            def executemany(s, sql, seq): conn.executed.append(sql)
            def fetchmany(s, n): return [(1,)]
        return Cur()
    def transaction(self):
        class T:
            def __enter__(s): return s
            def __exit__(s, *a): return False
        return T()
    def close(self): pass


def make_deps(store=None, warehouse=None, genie=None, model=None, branches=None, **kw):
    return RunDeps(store=store or InMemoryReviewStore(), warehouse=warehouse or FakeWarehouse(),
                   genie=genie or FakeGenie(), model=model or ScriptedModel(), branches=branches or FakeBranches(),
                   connect_branch=lambda wb: FakeBranchConn(), **kw)


def _routed(store):
    store.upsert_routed_claim({**CLAIM_ROW, "settled_amount": 24700.0}, routed_by="rule", routing_rule="r")


def test_success_promotes_brief_in_fixed_order_and_deletes_branch():
    store = InMemoryReviewStore(); _routed(store)
    warehouse, branches = FakeWarehouse(), FakeBranches()
    outcome = run_brief("C-1", make_deps(store=store, warehouse=warehouse, branches=branches))
    assert outcome.status == "completed"
    assert warehouse.calls == ["sequence", "relevant", "patterns", "similar"]
    detail = store.get_claim("C-1")
    sections = detail["brief"]["sections"]
    assert list(sections) == ["sequence", "relevant_changes", "frequency", "similar"]
    assert detail["brief"]["section_order"] == ["sequence", "relevant_changes", "frequency", "similar"]
    assert sections["sequence"]["material_change_count"] == 1
    assert sections["sequence"]["derived_change_count"] == 1
    assert sections["relevant_changes"]["situation"] == "relevant_before_loss"
    assert sections["frequency"]["shape"] == "relevant_before_loss" and sections["frequency"]["question_source"] == "model"
    assert sections["frequency"]["rows"] == [["with", "0.085", "400"], ["without", "0.058", "3600"]]
    assert all(sections[s]["sentence"] for s in sections)
    assert branches.deleted == branches.created and len(branches.created) == 1
    assert store.get_run(outcome.run_id)["status"] == "completed"


def test_vocabulary_failure_drops_the_sentence_not_the_brief():
    store = InMemoryReviewStore(); _routed(store)
    model = ScriptedModel(sentences={"similar": "These neighbours look suspicious."})
    outcome = run_brief("C-1", make_deps(store=store, model=model))
    section = store.get_claim("C-1")["brief"]["sections"]["similar"]
    assert outcome.status == "completed"
    assert section["sentence"] is None and section["sentence_dropped"] is True
    assert section["sentence_dropped_reason"] == "vocabulary check"
    assert "suspicious" not in json.dumps(store.get_claim("C-1")["brief"])


def test_genie_error_fails_run_promotes_nothing_and_deletes_branch():
    store = InMemoryReviewStore(); _routed(store)
    branches = FakeBranches()
    outcome = run_brief("C-1", make_deps(store=store, genie=FakeGenie(fail=True), branches=branches))
    assert outcome.status == "failed" and "Genie" in outcome.failure
    assert store.get_claim("C-1")["brief"] is None
    assert store.get_claim("C-1")["run_state"] == "queued"
    assert branches.deleted == branches.created


def test_wrong_shape_twice_falls_back_to_canonical_question():
    store = InMemoryReviewStore(); _routed(store)
    model = ScriptedModel(question={"shape": "pattern_only", "question": "x versus y"})
    genie = FakeGenie()
    run_brief("C-1", make_deps(store=store, model=model, genie=genie))
    freq = store.get_claim("C-1")["brief"]["sections"]["frequency"]
    assert freq["question_source"] == "canonical"
    assert "collision" in genie.questions[0][0].lower() and "compared" in genie.questions[0][0].lower()


def test_nothing_before_situation_asks_the_control_population_question():
    store = InMemoryReviewStore(); _routed(store)
    model = ScriptedModel(question={"shape": "nothing_before",
                                    "question": "What share of high-severity claims had no material change in the prior year, compared with those that did?"})
    run_brief("C-1", make_deps(store=store, warehouse=FakeWarehouse(relevant=[], patterns=[]), model=model))
    freq = store.get_claim("C-1")["brief"]["sections"]["frequency"]
    assert freq["shape"] == "nothing_before" and freq["question_source"] == "model"


def test_scratch_sql_budget_is_enforced_and_run_still_completes(monkeypatch):
    monkeypatch.setattr(harness_module, "MAX_SCRATCH_STATEMENTS", 2)
    store = InMemoryReviewStore(); _routed(store)
    class SqlHungryModel(ScriptedModel):
        def complete(self, system, user, *, max_tokens=800):
            if 'section "sequence"' in user:
                return json.dumps({"sql": "SELECT count(*) FROM review.stage_timeline"})
            return super().complete(system, user, max_tokens=max_tokens)
    outcome = run_brief("C-1", make_deps(store=store, model=SqlHungryModel()))
    assert outcome.status == "completed"
    seq = store.get_claim("C-1")["brief"]["sections"]["sequence"]
    assert seq["sentence"] is None and seq["sentence_dropped_reason"] == "scratch SQL budget"


def test_unparseable_model_output_drops_the_sentence_with_a_closed_set_reason():
    """The reason reaches the Brief panel verbatim, so it never carries the
    model's own words — only one of SENTENCE_DROPPED_REASONS."""
    store = InMemoryReviewStore(); _routed(store)

    class ProseInsteadOfJsonModel(ScriptedModel):
        def complete(self, system, user, *, max_tokens=800):
            if 'section "similar"' in user:
                return "Sure! These policies look rather suspicious to me."
            return super().complete(system, user, max_tokens=max_tokens)

    outcome = run_brief("C-1", make_deps(store=store, model=ProseInsteadOfJsonModel()))
    assert outcome.status == "completed"
    brief = store.get_claim("C-1")["brief"]
    section = brief["sections"]["similar"]
    assert section["sentence"] is None and section["sentence_dropped"] is True
    assert section["sentence_dropped_reason"] == "model output"
    assert section["sentence_dropped_reason"] in harness_module.SENTENCE_DROPPED_REASONS
    assert "suspicious" not in json.dumps(brief)


def test_second_caller_cannot_start_a_run_for_a_claim_in_progress():
    store = InMemoryReviewStore(); _routed(store)
    assert store.claim_run("C-1", "someone-else")
    outcome = run_brief("C-1", make_deps(store=store))
    assert outcome.status == "skipped"


def test_timeout_fails_the_run():
    store = InMemoryReviewStore(); _routed(store)
    ticks = iter([0, 0, 0, 500, 500, 500, 500, 500, 500, 500])
    outcome = run_brief("C-1", make_deps(store=store, clock=lambda: next(ticks), run_timeout_seconds=180))
    assert outcome.status == "failed" and "timed out" in outcome.failure


def test_demo_hold_sleeps_before_deleting_branch():
    store = InMemoryReviewStore(); _routed(store)
    slept = []
    run_brief("C-1", make_deps(store=store, demo_hold_seconds=20, sleep=slept.append))
    assert slept == [20]


class RaisingDeleteBranches(FakeBranches):
    def delete(self, wb):
        raise RuntimeError("network blip deleting branch")


def test_teardown_failure_after_promotion_does_not_unpromote_the_brief():
    store = InMemoryReviewStore(); _routed(store)
    branches = RaisingDeleteBranches()
    outcome = run_brief("C-1", make_deps(store=store, branches=branches))
    assert outcome.status == "completed"
    assert store.get_claim("C-1")["brief"] is not None
    assert store.get_run(outcome.run_id)["status"] == "completed"
    assert store.get_run(outcome.run_id)["current_step"] == "branch_delete_failed"
    assert store.get_claim("C-1")["run_state"] == "brief_ready"


class RaisingTraceIdTracer:
    def span(self, name, kind):
        return nullcontext()
    def last_trace_id(self):
        raise RuntimeError("mlflow blew up")


def test_last_trace_id_failure_does_not_block_promotion_or_teardown():
    store = InMemoryReviewStore(); _routed(store)
    branches = FakeBranches()
    outcome = run_brief("C-1", make_deps(store=store, branches=branches, tracer=RaisingTraceIdTracer()))
    assert outcome.status == "completed"
    assert outcome.trace_id is None
    assert branches.deleted == branches.created


class FollowUpOnceModel(ScriptedModel):
    """Like ScriptedModel, but always proposes one narrowing follow-up."""
    def __init__(self, follow_up_question, **kw):
        super().__init__(**kw)
        self._follow_up_question = follow_up_question
    def complete(self, system, user, *, max_tokens=800):
        if "narrowing follow-up" in user:
            self.calls.append(user)
            return json.dumps({"follow_up": self._follow_up_question})
        return super().complete(system, user, max_tokens=max_tokens)


def test_follow_up_asks_a_second_genie_turn_in_the_same_conversation():
    store = InMemoryReviewStore(); _routed(store)
    follow_up_question = "Show both group sizes as well."
    model = FollowUpOnceModel(follow_up_question)
    genie = FakeGenie()
    outcome = run_brief("C-1", make_deps(store=store, model=model, genie=genie))
    assert outcome.status == "completed"
    assert len(genie.questions) == 2
    assert genie.questions[1] == (follow_up_question, "conv-1")
    freq = store.get_claim("C-1")["brief"]["sections"]["frequency"]
    assert freq["follow_up"] == follow_up_question
    assert freq["follow_up_status"] == "ok"


class SecondCallFailsGenie:
    """First ask answers normally; every ask after that errors."""
    def __init__(self):
        self.questions = []
        self._calls = 0
    def ask(self, question, conversation_id=None):
        self._calls += 1
        self.questions.append((question, conversation_id))
        if self._calls == 1:
            return "conv-1", GenieResult(status="ok", columns=[{"name": "group"}, {"name": "rate"}, {"name": "n"}],
                                         rows=[["with", "0.085", "400"], ["without", "0.058", "3600"]],
                                         generated_sql="SELECT genie", description="d")
        return conversation_id, GenieResult(status="error", error="second turn failed")


def test_follow_up_answer_discarded_when_the_second_genie_turn_fails():
    store = InMemoryReviewStore(); _routed(store)
    model = FollowUpOnceModel("Show both group sizes as well.")
    genie = SecondCallFailsGenie()
    outcome = run_brief("C-1", make_deps(store=store, model=model, genie=genie))
    assert outcome.status == "completed"
    freq = store.get_claim("C-1")["brief"]["sections"]["frequency"]
    assert freq["rows"] == [["with", "0.085", "400"], ["without", "0.058", "3600"]]
    assert freq["genie_status"] == "ok"
    assert freq["follow_up"] is None
    assert freq["follow_up_status"] == "error"
