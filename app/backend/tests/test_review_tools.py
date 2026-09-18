from unittest.mock import MagicMock

import pytest

import backend.review.tools as tools_module
from backend.review.tools import BudgetExceeded, GenieTool, ScratchSql, WarehouseTools, stage


def test_sequence_is_a_365_day_window_ending_on_loss_date(monkeypatch):
    seen = {}
    def fake_run_query(client, sql, params=None):
        seen["sql"], seen["params"] = sql, params
        return [{"event_date": "2026-07-01", "is_material": "true"}]
    monkeypatch.setattr(tools_module, "run_query", fake_run_query)
    result = WarehouseTools(MagicMock()).sequence("P-10155", "2026-08-01")
    assert "policy_timeline_event" in seen["sql"] and "date_sub" in seen["sql"]
    assert seen["params"] == {"policy_id": "P-10155", "loss_date": "2026-08-01"}
    assert result.row_count == 1 and result.sql == seen["sql"]


def test_relevant_changes_filters_on_next_claim_and_same_line(monkeypatch):
    seen = {}
    monkeypatch.setattr(tools_module, "run_query", lambda c, sql, params=None: seen.update(sql=sql, params=params) or [])
    WarehouseTools(MagicMock()).relevant_changes("P-10155", "C-1")
    assert "next_claim_id = :claim_id" in seen["sql"]
    assert "change_relates_to_claimed_coverage = true" in seen["sql"]


def test_genie_tool_delegates_and_carries_conversation(monkeypatch):
    calls = []
    def fake_ask(client, conversation_id, question):
        calls.append((conversation_id, question))
        return "conv-1", MagicMock(status="ok")
    monkeypatch.setattr(tools_module, "ask_genie", fake_ask)
    tool = GenieTool(MagicMock())
    conv, _ = tool.ask("q1")
    tool.ask("q2", conversation_id=conv)
    assert calls == [(None, "q1"), ("conv-1", "q2")]


class FakeCursor:
    def __init__(self, conn): self.conn = conn; self.description = None; self._rows = []
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        if sql.strip().upper().startswith("SELECT"):
            self.description = [type("D", (), {"name": "n"})()]
            self._rows = [(1,), (2,), (3,)]
    def executemany(self, sql, seq): self.conn.executed.append((sql, list(seq)))
    def fetchmany(self, n): return self._rows[:n]


class FakeConn:
    def __init__(self): self.executed = []
    def cursor(self): return FakeCursor(self)
    def transaction(self):
        class T:
            def __enter__(s): return s
            def __exit__(s, *a): return False
        return T()


def test_stage_writes_jsonb_rows():
    conn = FakeConn()
    stage(conn, "stage_timeline", [{"a": 1}, {"a": 2}])
    sql, seq = conn.executed[-1]
    assert "INSERT INTO review.stage_timeline" in sql and len(seq) == 2


def test_scratch_sql_is_select_only_capped_and_budgeted():
    conn = FakeConn()
    scratch = ScratchSql(conn, max_statements=2, max_rows=2)
    out = scratch.run("SELECT count(*) FROM review.stage_timeline")
    assert out["columns"] == ["n"] and out["row_count"] == 2
    assert "error" in scratch.run("DELETE FROM review.stage_timeline")
    with pytest.raises(BudgetExceeded):
        scratch.run("SELECT 1")
