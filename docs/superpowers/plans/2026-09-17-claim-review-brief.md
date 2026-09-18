# Claim Review Brief Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An agent with a repo-owned harness builds a four-section evidence Brief for each Routed Claim on a disposable Lakebase branch, promotes only the finished Brief to a durable review record, and the app gains a Review view where a human records the Disposition.

**Architecture:** A shared Python package `app/backend/review/` holds the harness (fixed plan, tool allowlist, budgets, vocabulary check), the Lakebase client (branch lifecycle, connections), the store, the routing rule and the model client. It is imported both by the FastAPI app (on-demand Runs, Review API) and by two new Workflow tasks (nightly routing and a capped batch of Runs). Lakebase resources live in the bundle; Working Branches are created at runtime via the SDK. Claude is called through Databricks Model Serving (`serving_endpoints.query`), traced with MLflow.

**Tech Stack:** FastAPI, databricks-sdk ≥ 0.89, psycopg 3, mlflow 3, React + Vite, pytest, vitest, Databricks Asset Bundles.

**Spec:** `docs/superpowers/specs/2026-09-17-claim-review-brief-design.md` (read it first; ADR-0017, ADR-0018, ADR-0019 and `CONTEXT.md` § Review are its vocabulary).

## Global Constraints

- Vocabulary: no user-facing string may contain any term in `BANNED_VOCABULARY` (`pipeline/transformations.py`): fraud, fraudulent, suspicious, scheme, deceptive, guilty, risk score, predicts, causes, leads to, increases the risk of, anomaly, anomalous, red flag. UI copy uses `CONTEXT.md` terms: Routed Claim, Routing Rule, Brief, Disposition, Run, Working Branch.
- The harness owns the plan; the model owns only the frequency question, the optional follow-up, and one sentence per section (ADR-0018). No summary section, no recommendation, ever.
- Only the Brief and a compact run record cross from a Working Branch to main; failed Runs promote nothing (ADR-0017).
- Viewers never connect to Lakebase; app identity only (ADR-0019). Runs call Genie and the warehouse as app identity.
- Runs are strictly sequential (Free Edition concurrent-compute limit on non-default branches).
- Model provider is Databricks Model Serving (`databricks-claude-*` pay-per-token), never the Anthropic API directly; endpoint name is configuration `REVIEW_MODEL_ENDPOINT`.
- `genie.py` never raises (module contract); every new module that talks to Databricks returns structured failures upward to the harness, which is the one place that decides "Run failed".
- Competition-simple still applies: one process, threads not queues, no new services beyond the Lakebase project and the MLflow experiment.
- Backend tests: `pytest app/backend/tests -v` from the repo root. Frontend tests: `cd app/frontend && npm test`. Pipeline tests unaffected.
- Commit after every task with the trailer:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01FMDkLSRA385pbS6zRwKDq2
  ```
- Before Task 12 (bundle deploy), run `databricks auth login --profile DEFAULT` and confirm on the workspace serving page which `databricks-claude-*` endpoint is enabled; set `REVIEW_MODEL_ENDPOINT` accordingly.

## File Structure

```
app/backend/review/__init__.py        package marker
app/backend/review/vocabulary.py      banned list + violations()          (Task 2)
app/backend/review/questions.py       Situation, shapes, validate_question (Task 3)
app/backend/review/model.py           ModelClient protocol, FoundationModelClient, parse_json_object (Task 4)
app/backend/review/lakebase.py        LakebaseConfig, connections, WorkingBranch lifecycle (Task 5)
app/backend/review/schema.py          DDL migration                        (Task 6)
app/backend/review/store.py           ReviewStore (psycopg) + InMemoryReviewStore (Task 6)
app/backend/review/tools.py           deterministic tools, Genie tool, ScratchSql (Task 7)
app/backend/review/prompts.py         system prompt + per-step user prompts (Task 8)
app/backend/review/harness.py         run_brief()                          (Task 8)
app/backend/review/routing.py         ROUTING_SQL, route_claims()          (Task 9)
app/backend/review/runner.py          RunDeps, build_deps(), work_queue(), start_run_thread() (Task 9)
app/backend/investigations.py         Lakebase-backed with in-memory fallback (Task 10)
app/backend/review/api.py             APIRouter for /api/review/*          (Task 11)
app/backend/main.py                   include router, startup migration    (Task 11)
app/backend/config.py                 new env vars                         (Task 5)
workflow/route_claims_task.py         job task 5                           (Task 12)
workflow/build_briefs_task.py         job task 6                           (Task 12)
databricks.yml, app/app.yaml          Lakebase + experiment + tasks        (Task 12)
app/frontend/src/api/client.js        review calls                         (Task 13)
app/frontend/src/views/ReviewView.jsx (+ .css)                             (Task 13)
app/frontend/src/components/review/{QueueList,BriefPanel,RunPanel,DispositionForm}.jsx (Task 13)
app/frontend/src/App.jsx, AppHeader.jsx   view toggle, seeded tabs         (Task 13, 14)
app/frontend/src/components/Timeline.jsx  Prepare a Brief                  (Task 14)
app/frontend/src/hooks/useInvestigation.js seedQuestion                    (Task 14)
ci/review/smoke_branch.py, ci/review/run_brief_contract.py                 (Task 15)
docs/specs/13-meetup-demo-specification.md, docs/specs/README.md, docs/diagrams/01-high-level.mmd, README notes (Task 16)
```

---

### Task 1: Dependency floor (databricks-sdk ≥ 0.89, psycopg, mlflow)

**Files:**
- Modify: `app/requirements.txt`
- Test: existing `app/backend/tests/` (regression gate)

**Interfaces:**
- Produces: `WorkspaceClient.postgres` (branch/endpoint/credential API) and `WorkspaceClient.serving_endpoints.query` available to every later task.

- [ ] **Step 1: Run the existing backend suite to record the baseline**

Run: `pytest app/backend/tests -q`
Expected: all pass (record the count).

- [ ] **Step 2: Bump the pins**

Replace `app/requirements.txt` with:

```
fastapi==0.118.0
uvicorn[standard]==0.37.0
databricks-sdk>=0.89,<1
psycopg[binary]>=3.2,<4
mlflow>=3.1,<4
pytest==8.3.3
httpx==0.27.2
```

- [ ] **Step 3: Install and verify the postgres service exists**

Run: `pip install -r app/requirements.txt && python -c "from databricks.sdk import WorkspaceClient; from databricks.sdk.service.postgres import Branch, BranchSpec, Duration, Endpoint, EndpointSpec, EndpointType; from databricks.sdk.service.serving import ChatMessage, ChatMessageRole; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Re-run the backend suite**

Run: `pytest app/backend/tests -q`
Expected: same count passing. If `test_messages.py` fails on the Genie attachment-result path, the new SDK has `get_message_attachment_query_result`; the existing `getattr` fallback in `genie.py` handles it, so a failure here means a mock signature changed — fix the mock, not `genie.py`.

- [ ] **Step 5: Commit**

```bash
git add app/requirements.txt
git commit -m "Review agent: dependency floor for Lakebase, psycopg and MLflow"
```

---

### Task 2: Vocabulary check

**Files:**
- Create: `app/backend/review/__init__.py` (empty)
- Create: `app/backend/review/vocabulary.py`
- Test: `app/backend/tests/test_review_vocabulary.py`

**Interfaces:**
- Produces: `BANNED_VOCABULARY: tuple[str, ...]`, `JUDGEMENT_WORDS: tuple[str, ...]`, `violations(text: str, own_policy_id: str | None = None) -> list[str]`, `is_clean(text, own_policy_id) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
# app/backend/tests/test_review_vocabulary.py
"""The runtime vocabulary check mirrors pipeline expectation E18 for text
the pipeline cannot see (model-generated sentences)."""

import importlib.util
from pathlib import Path

from backend.review.vocabulary import BANNED_VOCABULARY, is_clean, violations


def test_banned_terms_are_whole_word_and_case_insensitive():
    assert violations("This looks Suspicious.") == ["suspicious"]
    assert violations("A coverage increase occurred before the claim.") == []
    assert violations("Risk Score is high") == ["risk score"]


def test_judgement_words_are_violations():
    assert "likely" in violations("The change was likely deliberate.")


def test_other_policy_ids_are_violations_but_own_id_is_fine():
    assert violations("Similar to P-20114.", own_policy_id="P-10155") == ["policy id P-20114"]
    assert violations("P-10155 changed coverage.", own_policy_id="P-10155") == []


def test_is_clean_wraps_violations():
    assert is_clean("Three material changes occurred before the loss.", "P-10155")
    assert not is_clean("This is a red flag.", "P-10155")


def test_banned_list_matches_pipeline_when_available():
    path = Path(__file__).resolve().parents[3] / "pipeline" / "transformations.py"
    if not path.exists():
        return
    spec = importlib.util.spec_from_file_location("ptm_transformations", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert tuple(BANNED_VOCABULARY) == tuple(module.BANNED_VOCABULARY)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest app/backend/tests/test_review_vocabulary.py -q`
Expected: FAIL with `ModuleNotFoundError: backend.review`

- [ ] **Step 3: Implement**

```python
# app/backend/review/vocabulary.py
"""Runtime vocabulary check for model-generated sentences.

Pipeline expectation E18 guards every user-facing string the pipeline
writes. Sentences the agent writes at runtime never pass through the
pipeline, so the same banned list is applied here. A test asserts this
list equals ``pipeline.transformations.BANNED_VOCABULARY``.
"""

from __future__ import annotations

import re

BANNED_VOCABULARY: tuple[str, ...] = (
    "fraud", "fraudulent", "suspicious", "scheme", "deceptive", "guilty",
    "risk score", "predicts", "causes", "leads to", "increases the risk of",
    "anomaly", "anomalous", "red flag",
)

#: Words that turn a fact into a judgement. The Brief restates facts only.
JUDGEMENT_WORDS: tuple[str, ...] = ("should", "likely", "intent", "deliberately", "probably")

_POLICY_ID = re.compile(r"\bP-\d{5}\b", re.IGNORECASE)


def _pattern(term: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b", re.IGNORECASE)


_BANNED = [(term, _pattern(term)) for term in BANNED_VOCABULARY + JUDGEMENT_WORDS]


def violations(text: str, own_policy_id: str | None = None) -> list[str]:
    found = [term for term, pattern in _BANNED if pattern.search(text or "")]
    own = (own_policy_id or "").upper()
    for match in _POLICY_ID.finditer(text or ""):
        if match.group(0).upper() != own:
            found.append(f"policy id {match.group(0).upper()}")
    return found


def is_clean(text: str, own_policy_id: str | None = None) -> bool:
    return not violations(text, own_policy_id)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest app/backend/tests/test_review_vocabulary.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/backend/review/__init__.py app/backend/review/vocabulary.py app/backend/tests/test_review_vocabulary.py
git commit -m "Review agent: runtime vocabulary check mirroring E18"
```

---

### Task 3: Situations and the four question shapes

**Files:**
- Create: `app/backend/review/questions.py`
- Test: `app/backend/tests/test_review_questions.py`

**Interfaces:**
- Produces: `Situation` (str enum: `relevant_in_gap`, `relevant_before_loss`, `pattern_only`, `nothing_before`), `detect_situation(relevant_changes: list[dict], patterns: list[dict]) -> Situation`, `window_days(relevant_changes) -> int` (30/60/90 bucket), `canonical_question(situation, *, coverage_line: str, line_name: str, window: int, pattern_name: str | None) -> str`, `validate_question(situation: Situation, proposal: dict) -> str | None` (None = valid, else reason).

- [ ] **Step 1: Write the failing tests**

```python
# app/backend/tests/test_review_questions.py
from backend.review.questions import (
    Situation,
    canonical_question,
    detect_situation,
    validate_question,
    window_days,
)

GAP = {"change_timing": "after_loss_before_report", "days_to_next_claim_loss": -3}
BEFORE = {"change_timing": "before_loss", "days_to_next_claim_loss": 63}
PATTERN = {"pattern_code": "rapid_change_cluster", "pattern_name": "Rapid change cluster"}


def test_detect_situation_precedence():
    assert detect_situation([GAP, BEFORE], [PATTERN]) == Situation.RELEVANT_IN_GAP
    assert detect_situation([BEFORE], [PATTERN]) == Situation.RELEVANT_BEFORE_LOSS
    assert detect_situation([], [PATTERN]) == Situation.PATTERN_ONLY
    assert detect_situation([], []) == Situation.NOTHING_BEFORE


def test_window_days_buckets_up_to_30_60_90():
    assert window_days([{"days_to_next_claim_loss": 12}]) == 30
    assert window_days([{"days_to_next_claim_loss": 63}]) == 90
    assert window_days([{"days_to_next_claim_loss": 45}, {"days_to_next_claim_loss": 5}]) == 30
    assert window_days([]) == 90


def test_canonical_questions_are_comparisons_and_clean():
    for situation in Situation:
        q = canonical_question(
            situation, coverage_line="COLL", line_name="collision", window=60,
            pattern_name="Rapid change cluster",
        )
        assert any(word in q.lower() for word in ("versus", "compared", "against"))
        assert "fraud" not in q.lower()


def test_validate_question_accepts_matching_shape():
    proposal = {"shape": "relevant_before_loss",
                "question": "How often does a collision limit increase within 90 days before a claim precede a high-severity claim, compared with increases not followed by one?"}
    assert validate_question(Situation.RELEVANT_BEFORE_LOSS, proposal) is None


def test_validate_question_rejects_wrong_shape_missing_comparison_and_banned_terms():
    assert "shape" in validate_question(Situation.NOTHING_BEFORE, {"shape": "pattern_only", "question": "x versus y"})
    assert "comparison" in validate_question(Situation.NOTHING_BEFORE, {"shape": "nothing_before", "question": "How many claims had no change?"})
    assert "vocabulary" in validate_question(Situation.NOTHING_BEFORE, {"shape": "nothing_before", "question": "Suspicious claims versus others?"})
    assert "question" in validate_question(Situation.NOTHING_BEFORE, {"shape": "nothing_before"})
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest app/backend/tests/test_review_questions.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# app/backend/review/questions.py
"""The model's one real decision, constrained (ADR-0018 §4 shapes).

The harness detects the *situation* from the deterministic sections; the
model must produce a question of the matching *shape*. Validation is
structural (shape tag, comparison phrasing, vocabulary), never string
equality, so the model's wording is free within the shape.
"""

from __future__ import annotations

from enum import Enum

from .vocabulary import violations


class Situation(str, Enum):
    RELEVANT_IN_GAP = "relevant_in_gap"
    RELEVANT_BEFORE_LOSS = "relevant_before_loss"
    PATTERN_ONLY = "pattern_only"
    NOTHING_BEFORE = "nothing_before"


_COMPARISON_WORDS = ("versus", "compared", "against")
_WINDOWS = (30, 60, 90)


def detect_situation(relevant_changes: list[dict], patterns: list[dict]) -> Situation:
    if any(r.get("change_timing") == "after_loss_before_report" for r in relevant_changes):
        return Situation.RELEVANT_IN_GAP
    if relevant_changes:
        return Situation.RELEVANT_BEFORE_LOSS
    if patterns:
        return Situation.PATTERN_ONLY
    return Situation.NOTHING_BEFORE


def window_days(relevant_changes: list[dict]) -> int:
    """Smallest of 30/60/90 that covers the nearest before-loss Relevant Change."""
    days = [
        int(r["days_to_next_claim_loss"])
        for r in relevant_changes
        if r.get("days_to_next_claim_loss") is not None and int(r["days_to_next_claim_loss"]) >= 0
    ]
    if not days:
        return 90
    nearest = min(days)
    for w in _WINDOWS:
        if nearest <= w:
            return w
    return 90


def canonical_question(
    situation: Situation,
    *,
    coverage_line: str,
    line_name: str,
    window: int,
    pattern_name: str | None,
) -> str:
    """The harness's fallback when the model's proposal fails validation twice."""
    if situation is Situation.RELEVANT_IN_GAP:
        return (
            f"How often do coverage or deductible changes on the {line_name} line fall inside the "
            f"loss-to-report gap versus before the loss, for changes with a linked claim? Show both counts."
        )
    if situation is Situation.RELEVANT_BEFORE_LOSS:
        return (
            f"How often does a {line_name} limit increase within {window} days before a claim precede a "
            f"high-severity claim, compared with {line_name} increases not followed by a high-severity claim? "
            f"Show both groups with their counts."
        )
    if situation is Situation.PATTERN_ONLY:
        return (
            f"How common is the pattern '{pattern_name}' among policies with high-severity claims versus "
            f"policies without high-severity claims? Show both rates with sample sizes."
        )
    return (
        "What share of high-severity claims had no material change in the 365 days before the loss, "
        "compared with high-severity claims that did? Show both counts."
    )


def validate_question(situation: Situation, proposal: dict) -> str | None:
    question = proposal.get("question") if isinstance(proposal, dict) else None
    if not isinstance(question, str) or not question.strip():
        return "missing question"
    if proposal.get("shape") != situation.value:
        return f"shape must be {situation.value}"
    if not any(word in question.lower() for word in _COMPARISON_WORDS):
        return "question must name a comparison (versus / compared / against)"
    bad = violations(question)
    if bad:
        return f"vocabulary: {', '.join(bad)}"
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest app/backend/tests/test_review_questions.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/backend/review/questions.py app/backend/tests/test_review_questions.py
git commit -m "Review agent: situations and the four frequency question shapes"
```

---

### Task 4: Model client (Databricks Model Serving, JSON contract)

**Files:**
- Create: `app/backend/review/model.py`
- Test: `app/backend/tests/test_review_model.py`

**Interfaces:**
- Produces: `class ModelClient(Protocol)` with `complete(system: str, user: str, *, max_tokens: int = 800) -> str`; `class FoundationModelClient(ModelClient)` built from `(WorkspaceClient, endpoint_name)`; `parse_json_object(text: str) -> dict` raising `ModelOutputError`; `class ModelOutputError(RuntimeError)`.

- [ ] **Step 1: Write the failing tests**

```python
# app/backend/tests/test_review_model.py
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.review.model import FoundationModelClient, ModelOutputError, parse_json_object


def test_parse_json_object_strips_fences_and_prose():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Here you go: {"shape": "x", "question": "y"} thanks') == {"shape": "x", "question": "y"}


def test_parse_json_object_rejects_non_objects():
    with pytest.raises(ModelOutputError):
        parse_json_object("no json here")
    with pytest.raises(ModelOutputError):
        parse_json_object("[1, 2]")


def test_foundation_model_client_queries_endpoint_with_system_and_user():
    client = MagicMock()
    client.serving_endpoints.query.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
    )
    model = FoundationModelClient(client, "databricks-claude-sonnet-4-5")
    text = model.complete("SYS", "USER", max_tokens=100)
    assert text == '{"ok": true}'
    kwargs = client.serving_endpoints.query.call_args.kwargs
    assert kwargs["name"] == "databricks-claude-sonnet-4-5"
    assert kwargs["max_tokens"] == 100
    assert kwargs["temperature"] == 0.0
    roles = [m.role.value if hasattr(m.role, "value") else m.role for m in kwargs["messages"]]
    assert [r.lower() for r in roles] == ["system", "user"]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest app/backend/tests/test_review_model.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# app/backend/review/model.py
"""Model access through Databricks Model Serving (pay-per-token Claude).

The provider is Databricks, chosen for ecosystem fit over calling the
Anthropic API directly (design spec §8). Every model turn returns one JSON
object, so no tool-calling API is needed and any text endpoint works.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole


class ModelOutputError(RuntimeError):
    """The model's reply did not contain a single JSON object."""


class ModelClient(Protocol):
    def complete(self, system: str, user: str, *, max_tokens: int = 800) -> str: ...


class FoundationModelClient:
    def __init__(self, client: WorkspaceClient, endpoint_name: str) -> None:
        self._client = client
        self.endpoint_name = endpoint_name

    def complete(self, system: str, user: str, *, max_tokens: int = 800) -> str:
        response = self._client.serving_endpoints.query(
            name=self.endpoint_name,
            messages=[
                ChatMessage(role=ChatMessageRole.SYSTEM, content=system),
                ChatMessage(role=ChatMessageRole.USER, content=user),
            ],
            max_tokens=max_tokens,
            temperature=0.0,
        )
        return response.choices[0].message.content or ""


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json_object(text: str) -> dict:
    candidate = text or ""
    fenced = _FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1)
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ModelOutputError(f"no JSON object in model output: {text[:120]!r}")
    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ModelOutputError(str(exc)) from exc
    if not isinstance(parsed, dict):
        raise ModelOutputError("model output is not a JSON object")
    return parsed
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest app/backend/tests/test_review_model.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/backend/review/model.py app/backend/tests/test_review_model.py
git commit -m "Review agent: model client over Databricks Model Serving with a JSON contract"
```

---

### Task 5: Lakebase configuration, connections and the Working Branch lifecycle

**Files:**
- Modify: `app/backend/config.py`
- Create: `app/backend/review/lakebase.py`
- Test: `app/backend/tests/test_review_lakebase.py`

**Interfaces:**
- Consumes: `WorkspaceClient.postgres.{create_branch, create_endpoint, get_endpoint, delete_endpoint, delete_branch, generate_database_credential}` (SDK ≥ 0.89, Task 1).
- Produces: config constants `LAKEBASE_PROJECT_ID`, `LAKEBASE_MAIN_BRANCH`, `LAKEBASE_MAIN_ENDPOINT`, `LAKEBASE_DATABASE`, `LAKEBASE_HOST`, `LAKEBASE_USER`, `REVIEW_MODEL_ENDPOINT`, `REVIEW_MLFLOW_EXPERIMENT`, `REVIEW_DEMO_HOLD_SECONDS`, `REVIEW_NIGHTLY_CAP`, `REVIEW_RUN_TIMEOUT_SECONDS`, `APP_SERVICE_PRINCIPAL_ID`, `lakebase_configured() -> bool`; `@dataclass WorkingBranch(run_id, branch_name, endpoint_name, host)`; `class BranchLifecycle` with `create(run_id: str) -> WorkingBranch` and `delete(branch: WorkingBranch) -> None`; `connect_main(client) -> psycopg.Connection`; `connect_branch(client, branch: WorkingBranch) -> psycopg.Connection`; `main_endpoint_name() -> str`.

- [ ] **Step 1: Add configuration**

Append to `app/backend/config.py`:

```python
# --- Review agent (design spec 2026-09-17) ---------------------------------
#: Lakebase project/branch/endpoint the bundle declares. Working Branches are
#: forked from LAKEBASE_MAIN_BRANCH at runtime and never declared.
LAKEBASE_PROJECT_ID = os.environ.get("LAKEBASE_PROJECT_ID") or None
LAKEBASE_MAIN_BRANCH = os.environ.get("LAKEBASE_MAIN_BRANCH", "production")
LAKEBASE_MAIN_ENDPOINT = os.environ.get("LAKEBASE_MAIN_ENDPOINT", "primary")
#: Injected by the Databricks Apps resource binding; absent in the Workflow,
#: where lakebase.py resolves them from the SDK instead.
LAKEBASE_DATABASE = os.environ.get("PGDATABASE", "review")
LAKEBASE_HOST = os.environ.get("PGHOST") or None
LAKEBASE_USER = os.environ.get("PGUSER") or None
#: The app SP's application id; the migration grants it table privileges so
#: tables created by the Workflow's run-as user stay readable by the app.
APP_SERVICE_PRINCIPAL_ID = os.environ.get("APP_SERVICE_PRINCIPAL_ID") or None

REVIEW_MODEL_ENDPOINT = os.environ.get("REVIEW_MODEL_ENDPOINT", "databricks-claude-sonnet-4-5")
REVIEW_MLFLOW_EXPERIMENT = os.environ.get("REVIEW_MLFLOW_EXPERIMENT", "/Shared/policy-time-machine-review")
REVIEW_DEMO_HOLD_SECONDS = int(os.environ.get("REVIEW_DEMO_HOLD_SECONDS", "0"))
REVIEW_NIGHTLY_CAP = int(os.environ.get("REVIEW_NIGHTLY_CAP", "20"))
REVIEW_RUN_TIMEOUT_SECONDS = int(os.environ.get("REVIEW_RUN_TIMEOUT_SECONDS", "180"))
REVIEW_BRANCH_TTL_SECONDS = int(os.environ.get("REVIEW_BRANCH_TTL_SECONDS", "900"))


def lakebase_configured() -> bool:
    return bool(LAKEBASE_PROJECT_ID)
```

- [ ] **Step 2: Write the failing tests**

```python
# app/backend/tests/test_review_lakebase.py
"""Branch lifecycle against a mocked SDK: create branch -> create endpoint
-> read host; delete endpoint then branch, tolerant of a missing endpoint."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.review import lakebase
from backend.review.lakebase import BranchLifecycle, WorkingBranch


def _client():
    client = MagicMock()
    branch = SimpleNamespace(name="projects/ptm/branches/run-abc")
    client.postgres.create_branch.return_value.wait.return_value = branch
    endpoint = SimpleNamespace(
        name="projects/ptm/branches/run-abc/endpoints/primary",
        status=SimpleNamespace(hosts=SimpleNamespace(host="ep-run-abc.example.com")),
    )
    client.postgres.create_endpoint.return_value.wait.return_value = endpoint
    client.postgres.generate_database_credential.return_value = SimpleNamespace(token="tok")
    return client


def test_create_forks_main_and_returns_host(monkeypatch):
    monkeypatch.setattr(lakebase, "LAKEBASE_PROJECT_ID", "ptm")
    monkeypatch.setattr(lakebase, "LAKEBASE_MAIN_BRANCH", "production")
    client = _client()
    wb = BranchLifecycle(client).create("abc")
    assert wb == WorkingBranch(
        run_id="abc",
        branch_name="projects/ptm/branches/run-abc",
        endpoint_name="projects/ptm/branches/run-abc/endpoints/primary",
        host="ep-run-abc.example.com",
    )
    kwargs = client.postgres.create_branch.call_args.kwargs
    assert kwargs["parent"] == "projects/ptm"
    assert kwargs["branch_id"] == "run-abc"
    assert kwargs["branch"].spec.source_branch == "projects/ptm/branches/production"
    assert kwargs["branch"].spec.ttl.seconds == lakebase.REVIEW_BRANCH_TTL_SECONDS


def test_delete_removes_endpoint_then_branch_and_tolerates_missing_endpoint():
    client = _client()
    client.postgres.delete_endpoint.side_effect = RuntimeError("already gone")
    wb = WorkingBranch("abc", "projects/ptm/branches/run-abc", "projects/ptm/branches/run-abc/endpoints/primary", "h")
    BranchLifecycle(client).delete(wb)
    client.postgres.delete_branch.assert_called_once_with(name="projects/ptm/branches/run-abc")


def test_main_endpoint_name_uses_config(monkeypatch):
    monkeypatch.setattr(lakebase, "LAKEBASE_PROJECT_ID", "ptm")
    assert lakebase.main_endpoint_name() == "projects/ptm/branches/production/endpoints/primary"


def test_conninfo_uses_token_as_password_and_requires_ssl(monkeypatch):
    client = _client()
    info = lakebase.conninfo(client, host="h", endpoint_name="e", user="u@x.com", database="review")
    assert info["password"] == "tok"
    assert info["sslmode"] == "require"
    assert info["host"] == "h" and info["user"] == "u@x.com" and info["dbname"] == "review"
    client.postgres.generate_database_credential.assert_called_once_with(endpoint="e")
```

- [ ] **Step 3: Run to verify failure**

Run: `pytest app/backend/tests/test_review_lakebase.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement**

```python
# app/backend/review/lakebase.py
"""Lakebase access: connections to main, and the Working Branch lifecycle.

Branches fork and never merge (ADR-0017). The harness forks
``run-<run_id>`` from the main branch, creates a compute endpoint on it
(non-default branches have none until asked), connects with a fresh OAuth
database credential as password, and deletes endpoint then branch when
the Run ends. A TTL on the branch is the platform backstop for a crashed
process; explicit deletion is the normal path.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import (
    Branch,
    BranchSpec,
    Duration,
    Endpoint,
    EndpointSpec,
    EndpointType,
)

from ..config import (
    LAKEBASE_DATABASE,
    LAKEBASE_HOST,
    LAKEBASE_MAIN_BRANCH,
    LAKEBASE_MAIN_ENDPOINT,
    LAKEBASE_PROJECT_ID,
    LAKEBASE_USER,
    REVIEW_BRANCH_TTL_SECONDS,
)


@dataclass(frozen=True)
class WorkingBranch:
    run_id: str
    branch_name: str
    endpoint_name: str
    host: str


def main_branch_name() -> str:
    return f"projects/{LAKEBASE_PROJECT_ID}/branches/{LAKEBASE_MAIN_BRANCH}"


def main_endpoint_name() -> str:
    return f"{main_branch_name()}/endpoints/{LAKEBASE_MAIN_ENDPOINT}"


def conninfo(client: WorkspaceClient, *, host: str, endpoint_name: str, user: str, database: str) -> dict:
    token = client.postgres.generate_database_credential(endpoint=endpoint_name).token
    return {"host": host, "port": 5432, "dbname": database, "user": user, "password": token, "sslmode": "require"}


def _resolve_user(client: WorkspaceClient) -> str:
    return LAKEBASE_USER or client.current_user.me().user_name


def _resolve_main_host(client: WorkspaceClient) -> str:
    if LAKEBASE_HOST:
        return LAKEBASE_HOST
    return client.postgres.get_endpoint(name=main_endpoint_name()).status.hosts.host


def connect_main(client: WorkspaceClient) -> psycopg.Connection:
    info = conninfo(client, host=_resolve_main_host(client), endpoint_name=main_endpoint_name(),
                    user=_resolve_user(client), database=LAKEBASE_DATABASE)
    return psycopg.connect(**info, autocommit=True)


def connect_branch(client: WorkspaceClient, branch: WorkingBranch) -> psycopg.Connection:
    info = conninfo(client, host=branch.host, endpoint_name=branch.endpoint_name,
                    user=_resolve_user(client), database=LAKEBASE_DATABASE)
    return psycopg.connect(**info, autocommit=True)


class BranchLifecycle:
    def __init__(self, client: WorkspaceClient) -> None:
        self._client = client

    def create(self, run_id: str) -> WorkingBranch:
        branch = self._client.postgres.create_branch(
            parent=f"projects/{LAKEBASE_PROJECT_ID}",
            branch=Branch(spec=BranchSpec(source_branch=main_branch_name(),
                                          ttl=Duration(seconds=REVIEW_BRANCH_TTL_SECONDS))),
            branch_id=f"run-{run_id}",
        ).wait()
        endpoint = self._client.postgres.create_endpoint(
            parent=branch.name,
            endpoint=Endpoint(spec=EndpointSpec(endpoint_type=EndpointType.ENDPOINT_TYPE_READ_WRITE,
                                                autoscaling_limit_min_cu=0.5, autoscaling_limit_max_cu=1.0)),
            endpoint_id="primary",
        ).wait()
        return WorkingBranch(run_id=run_id, branch_name=branch.name, endpoint_name=endpoint.name,
                             host=endpoint.status.hosts.host)

    def delete(self, branch: WorkingBranch) -> None:
        try:
            self._client.postgres.delete_endpoint(name=branch.endpoint_name).wait()
        except Exception:  # noqa: BLE001 - endpoint may already be gone; the branch delete is what matters
            pass
        self._client.postgres.delete_branch(name=branch.branch_name).wait()
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest app/backend/tests/test_review_lakebase.py -q`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add app/backend/config.py app/backend/review/lakebase.py app/backend/tests/test_review_lakebase.py
git commit -m "Review agent: Lakebase connections and the Working Branch lifecycle"
```

---

### Task 6: Schema migration and the review store

**Files:**
- Create: `app/backend/review/schema.py`
- Create: `app/backend/review/store.py`
- Test: `app/backend/tests/test_review_store.py`

**Interfaces:**
- Produces: `schema.DDL: tuple[str, ...]`, `schema.ensure_schema(conn, app_sp_id: str | None) -> None`, `schema.STAGE_DDL: tuple[str, ...]` (branch-only tables), `schema.ensure_stage_tables(conn)`.
- Produces: `class ReviewStore` (psycopg-backed) and `class InMemoryReviewStore`, both implementing:
  - `upsert_routed_claim(claim: dict, routed_by: str, routing_rule: str | None) -> None`
  - `claim_run(claim_id: str, run_id: str) -> bool` (conditional: only from `queued`/`failed`)
  - `start_run(run_id, claim_id) -> None`, `update_run(run_id, *, current_step=None, step_count=None, branch_name=None) -> None`
  - `complete_run(run_id, claim_id, brief: dict, anchor_date: str, trace_id: str | None) -> None` (one transaction: insert brief, run completed, claim `brief_ready`)
  - `fail_run(run_id, claim_id, failure: str) -> None` (run failed, claim `queued`)
  - `get_run(run_id) -> dict | None`, `list_queue() -> list[dict]`, `get_claim(claim_id) -> dict | None` (claim + brief + disposition + active run)
  - `record_disposition(claim_id, outcome, note, recorded_by) -> dict`
  - `pending_claims(limit: int) -> list[dict]` (undisposed, no brief, run_state in queued/failed, newest report_date first)
  - `get_conversation(investigation_id) -> str | None | MISSING`, `set_conversation(investigation_id, conversation_id) -> None`, `create_investigation(investigation_id) -> None`
- Constant `DISPOSITION_OUTCOMES = ("closer_look", "nothing_noteworthy", "more_information")`.

- [ ] **Step 1: Write the failing tests (in-memory store; the Postgres store runs only when `REVIEW_TEST_PG_DSN` is set)**

```python
# app/backend/tests/test_review_store.py
import os

import pytest

from backend.review.store import DISPOSITION_OUTCOMES, InMemoryReviewStore, ReviewStore

CLAIM = {
    "claim_id": "C-1", "policy_id": "P-10155", "coverage_line": "COLL",
    "loss_date": "2026-08-01", "report_date": "2026-08-05",
    "settled_amount": 24700.0, "severity_band": "severe",
}


def stores():
    yield InMemoryReviewStore()
    dsn = os.environ.get("REVIEW_TEST_PG_DSN")
    if dsn:
        import psycopg
        from backend.review.schema import ensure_schema
        conn = psycopg.connect(dsn, autocommit=True)
        conn.execute("DROP SCHEMA IF EXISTS review CASCADE")
        ensure_schema(conn, None)
        yield ReviewStore(conn)


@pytest.mark.parametrize("store", list(stores()), ids=lambda s: type(s).__name__)
def test_claim_run_is_conditional_and_full_lifecycle_promotes_once(store):
    store.upsert_routed_claim(CLAIM, routed_by="rule", routing_rule="High-severity claim reported in the last 90 days.")
    assert store.claim_run("C-1", "run-1") is True
    assert store.claim_run("C-1", "run-2") is False  # in progress -> second caller loses
    store.start_run("run-1", "C-1")
    store.update_run("run-1", current_step="branch_created", step_count=1, branch_name="projects/p/branches/run-run-1")
    assert store.get_run("run-1")["current_step"] == "branch_created"
    store.complete_run("run-1", "C-1", {"sections": {}}, anchor_date="2026-09-17", trace_id="tr-1")
    detail = store.get_claim("C-1")
    assert detail["run_state"] == "brief_ready"
    assert detail["brief"]["sections"] == {}
    assert detail["disposition"] is None
    assert store.pending_claims(10) == []


@pytest.mark.parametrize("store", list(stores()), ids=lambda s: type(s).__name__)
def test_failed_run_requeues_and_promotes_nothing(store):
    store.upsert_routed_claim(CLAIM, routed_by="on_demand", routing_rule=None)
    assert store.claim_run("C-1", "run-1")
    store.start_run("run-1", "C-1")
    store.fail_run("run-1", "C-1", "genie timed out")
    detail = store.get_claim("C-1")
    assert detail["run_state"] == "queued" and detail["brief"] is None
    assert store.get_run("run-1")["status"] == "failed"
    assert [c["claim_id"] for c in store.pending_claims(10)] == ["C-1"]


@pytest.mark.parametrize("store", list(stores()), ids=lambda s: type(s).__name__)
def test_disposition_requires_brief_and_records_who_when(store):
    store.upsert_routed_claim(CLAIM, routed_by="rule", routing_rule="r")
    with pytest.raises(LookupError):
        store.record_disposition("C-1", "closer_look", None, "dana@example.com")
    store.claim_run("C-1", "run-1"); store.start_run("run-1", "C-1")
    store.complete_run("run-1", "C-1", {"sections": {}}, anchor_date="2026-09-17", trace_id=None)
    d = store.record_disposition("C-1", "nothing_noteworthy", "renewal-driven", "dana@example.com")
    assert d["outcome"] in DISPOSITION_OUTCOMES and d["recorded_by"] == "dana@example.com" and d["recorded_at"]
    assert store.list_queue()[0]["disposition"]["outcome"] == "nothing_noteworthy"


@pytest.mark.parametrize("store", list(stores()), ids=lambda s: type(s).__name__)
def test_investigation_conversation_map(store):
    from backend.review.store import MISSING
    assert store.get_conversation("inv-1") is MISSING
    store.create_investigation("inv-1")
    assert store.get_conversation("inv-1") is None
    store.set_conversation("inv-1", "conv-9")
    assert store.get_conversation("inv-1") == "conv-9"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest app/backend/tests/test_review_store.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the schema**

```python
# app/backend/review/schema.py
"""Idempotent DDL for the review record (design spec §7.2).

Runs at app startup and at the start of the route_claims task. Working
Branches inherit the schema at fork time and are never migrated; the
stage tables are created per Run on the branch only.
"""

from __future__ import annotations

DDL: tuple[str, ...] = (
    "CREATE SCHEMA IF NOT EXISTS review",
    """CREATE TABLE IF NOT EXISTS review.routed_claim (
         claim_id text PRIMARY KEY, policy_id text NOT NULL, coverage_line text NOT NULL,
         loss_date date NOT NULL, report_date date NOT NULL, settled_amount numeric NOT NULL,
         severity_band text NOT NULL, routed_by text NOT NULL, routing_rule text,
         run_state text NOT NULL DEFAULT 'queued', active_run_id text,
         routed_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS review.run (
         run_id text PRIMARY KEY, claim_id text NOT NULL REFERENCES review.routed_claim(claim_id),
         status text NOT NULL, current_step text, step_count int NOT NULL DEFAULT 0,
         branch_name text, trace_id text, failure text,
         started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz)""",
    """CREATE TABLE IF NOT EXISTS review.brief (
         claim_id text PRIMARY KEY REFERENCES review.routed_claim(claim_id),
         run_id text NOT NULL REFERENCES review.run(run_id), anchor_date date NOT NULL,
         built_at timestamptz NOT NULL DEFAULT now(), body jsonb NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS review.disposition (
         claim_id text PRIMARY KEY REFERENCES review.routed_claim(claim_id),
         outcome text NOT NULL, note text, recorded_by text NOT NULL,
         recorded_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS review.investigation (
         investigation_id text PRIMARY KEY, conversation_id text,
         created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())""",
)

#: Branch-only working tables. Genie/warehouse rows are stored as jsonb so the
#: harness never has to mirror gold column types in Postgres.
STAGE_DDL: tuple[str, ...] = (
    "DROP TABLE IF EXISTS review.stage_timeline, review.stage_relevant_changes, review.stage_patterns, review.stage_frequency, review.stage_similar, review.run_step",
    "CREATE TABLE review.stage_timeline (n int, row jsonb NOT NULL)",
    "CREATE TABLE review.stage_relevant_changes (n int, row jsonb NOT NULL)",
    "CREATE TABLE review.stage_patterns (n int, row jsonb NOT NULL)",
    "CREATE TABLE review.stage_frequency (n int, row jsonb NOT NULL)",
    "CREATE TABLE review.stage_similar (n int, row jsonb NOT NULL)",
    """CREATE TABLE review.run_step (n serial, step text NOT NULL, tool text, sql text,
         row_count int, elapsed_ms int, payload jsonb, at timestamptz NOT NULL DEFAULT now())""",
)


def _grants(app_sp_id: str) -> tuple[str, ...]:
    role = '"' + app_sp_id.replace('"', '""') + '"'
    return (
        f"GRANT USAGE ON SCHEMA review TO {role}",
        f"GRANT ALL ON ALL TABLES IN SCHEMA review TO {role}",
        f"GRANT ALL ON ALL SEQUENCES IN SCHEMA review TO {role}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA review GRANT ALL ON TABLES TO {role}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA review GRANT ALL ON SEQUENCES TO {role}",
    )


def ensure_schema(conn, app_sp_id: str | None) -> None:
    with conn.cursor() as cur:
        for statement in DDL:
            cur.execute(statement)
        if app_sp_id:
            for statement in _grants(app_sp_id):
                try:
                    cur.execute(statement)
                except Exception:  # noqa: BLE001 - the app SP granting to itself, or role absent locally
                    conn.rollback() if not conn.autocommit else None


def ensure_stage_tables(conn) -> None:
    with conn.cursor() as cur:
        for statement in STAGE_DDL:
            cur.execute(statement)
```

- [ ] **Step 4: Implement the store**

```python
# app/backend/review/store.py
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
from typing import Any

DISPOSITION_OUTCOMES = ("closer_look", "nothing_noteworthy", "more_information")
MISSING = object()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InMemoryReviewStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
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
            if not row or row["run_state"] not in ("queued", "failed"):
                return False
            row.update(run_state="in_progress", active_run_id=run_id, updated_at=_now())
            return True

    def start_run(self, run_id: str, claim_id: str) -> None:
        self.runs[run_id] = {"run_id": run_id, "claim_id": claim_id, "status": "running", "current_step": None,
                             "step_count": 0, "branch_name": None, "trace_id": None, "failure": None,
                             "started_at": _now(), "finished_at": None}

    def update_run(self, run_id: str, *, current_step=None, step_count=None, branch_name=None) -> None:
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
        return dict(self.runs[run_id]) if run_id in self.runs else None

    def _queue_row(self, claim: dict) -> dict:
        return {**claim, "has_brief": claim["claim_id"] in self.briefs,
                "disposition": self.dispositions.get(claim["claim_id"])}

    def list_queue(self) -> list[dict]:
        rows = [self._queue_row(c) for c in self.claims.values()]
        return sorted(rows, key=lambda r: (r["report_date"], r["claim_id"]), reverse=True)

    def get_claim(self, claim_id: str) -> dict | None:
        claim = self.claims.get(claim_id)
        if not claim:
            return None
        brief = self.briefs.get(claim_id)
        run = self.runs.get(claim["active_run_id"]) if claim["active_run_id"] else None
        return {**claim, "brief": brief["body"] if brief else None,
                "brief_anchor_date": brief["anchor_date"] if brief else None,
                "brief_built_at": brief["built_at"] if brief else None,
                "disposition": self.dispositions.get(claim_id), "active_run": dict(run) if run else None}

    def record_disposition(self, claim_id, outcome, note, recorded_by) -> dict:
        if outcome not in DISPOSITION_OUTCOMES:
            raise ValueError(f"unknown outcome {outcome!r}")
        if claim_id not in self.briefs:
            raise LookupError("no Brief for this claim yet")
        row = {"claim_id": claim_id, "outcome": outcome, "note": note, "recorded_by": recorded_by, "recorded_at": _now()}
        self.dispositions[claim_id] = row
        return dict(row)

    def pending_claims(self, limit: int) -> list[dict]:
        rows = [c for c in self.claims.values()
                if c["claim_id"] not in self.briefs and c["claim_id"] not in self.dispositions
                and c["run_state"] in ("queued", "failed")]
        return sorted(rows, key=lambda r: (r["report_date"], r["claim_id"]), reverse=True)[:limit]

    def create_investigation(self, investigation_id: str) -> None:
        self.investigations[investigation_id] = None

    def get_conversation(self, investigation_id: str):
        return self.investigations.get(investigation_id, MISSING)

    def set_conversation(self, investigation_id: str, conversation_id: str | None) -> None:
        self.investigations[investigation_id] = conversation_id


class ReviewStore:
    """psycopg-backed. The connection is autocommit; multi-statement
    transitions open an explicit transaction."""

    def __init__(self, conn) -> None:
        self._conn = conn
        self._lock = threading.Lock()

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return []
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def _exec(self, sql: str, params: tuple = ()) -> int:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount

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
               WHERE claim_id = %s AND run_state IN ('queued', 'failed')""",
            (run_id, claim_id),
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
        with self._lock, self._conn.transaction(), self._conn.cursor() as cur:
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

    def fail_run(self, run_id, claim_id, failure: str) -> None:
        with self._lock, self._conn.transaction(), self._conn.cursor() as cur:
            cur.execute("UPDATE review.run SET status='failed', failure=%s, finished_at=now() WHERE run_id=%s", (failure[:500], run_id))
            cur.execute("UPDATE review.routed_claim SET run_state='queued', active_run_id=NULL, updated_at=now() WHERE claim_id=%s", (claim_id,))

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
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest app/backend/tests/test_review_store.py -q`
Expected: 4 passed (8 if `REVIEW_TEST_PG_DSN` points at a local Postgres, e.g. `docker run -e POSTGRES_PASSWORD=pw -p 5433:5432 postgres:17` and `REVIEW_TEST_PG_DSN=postgresql://postgres:pw@localhost:5433/postgres`).

- [ ] **Step 6: Commit**

```bash
git add app/backend/review/schema.py app/backend/review/store.py app/backend/tests/test_review_store.py
git commit -m "Review agent: review-record schema and store with an in-memory twin"
```

---

### Task 7: Tools — deterministic reads, the Genie tool, staging and scratch SQL

**Files:**
- Create: `app/backend/review/tools.py`
- Test: `app/backend/tests/test_review_tools.py`

**Interfaces:**
- Consumes: `backend.warehouse.run_query(client, sql, params) -> list[dict]`, `backend.genie.ask_genie(client, conversation_id, question) -> (conversation_id, GenieResult)`, `backend.config.CATALOG/SCHEMA`.
- Produces:
  - `@dataclass ToolResult(rows: list[dict], sql: str, row_count: int)`
  - `class WarehouseTools(client)` with `claim(claim_id) -> dict | None`, `sequence(policy_id, loss_date) -> ToolResult`, `relevant_changes(policy_id, claim_id) -> ToolResult`, `pattern_matches(policy_id, claim_id) -> ToolResult`, `similar(policy_id, k=5) -> ToolResult`, `anchor_date() -> str`
  - `class GenieTool(client)` with `ask(question, conversation_id=None) -> tuple[str | None, GenieResult]`
  - `stage(conn, table: str, rows: list[dict]) -> None` (writes `review.<table>` on the branch as jsonb rows)
  - `class ScratchSql(conn, max_statements=8, max_rows=50)` with `run(sql: str) -> dict` returning `{"columns": [...], "rows": [...], "row_count": n}` or `{"error": "..."}`; raises `BudgetExceeded` after the limit; rejects non-SELECT.
  - `class BudgetExceeded(RuntimeError)`.

- [ ] **Step 1: Write the failing tests**

```python
# app/backend/tests/test_review_tools.py
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest app/backend/tests/test_review_tools.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# app/backend/review/tools.py
"""The harness's tool allowlist (ADR-0018).

Deterministic reads are the app's own SQL against gold, as in queries.py;
the Genie tool is the existing conversation client; staging writes rows to
the Working Branch as jsonb; ScratchSql is the one tool the model drives,
and it only ever runs SELECTs on the branch.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from databricks.sdk import WorkspaceClient

from ..config import CATALOG, SCHEMA
from ..genie import GenieResult, ask_genie
from ..warehouse import run_query

_BRONZE = "ptm_bronze"


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class ToolResult:
    rows: list[dict]
    sql: str
    row_count: int


_CLAIM_SQL = f"SELECT * FROM {CATALOG}.{SCHEMA}.claim_event WHERE claim_id = :claim_id"

_SEQUENCE_SQL = f"""
SELECT * FROM {CATALOG}.{SCHEMA}.policy_timeline_event
WHERE policy_id = :policy_id
  AND event_date <= CAST(:loss_date AS DATE)
  AND event_date >= date_sub(CAST(:loss_date AS DATE), 365)
ORDER BY event_date
""".strip()

_RELEVANT_SQL = f"""
SELECT * FROM {CATALOG}.{SCHEMA}.policy_change_event
WHERE policy_id = :policy_id AND next_claim_id = :claim_id
  AND change_relates_to_claimed_coverage = true
ORDER BY change_date
""".strip()

_PATTERNS_SQL = f"""
SELECT * FROM {CATALOG}.{SCHEMA}.policy_pattern_match
WHERE policy_id = :policy_id AND evidence_claim_id = :claim_id
ORDER BY matched_on_date
""".strip()

_SIMILAR_SQL = f"""
SELECT * FROM {CATALOG}.{SCHEMA}.policy_similarity
WHERE policy_id = :policy_id AND rank <= :k
ORDER BY rank
""".strip()

_ANCHOR_SQL = f"SELECT CAST(anchor_date AS STRING) AS anchor_date FROM {CATALOG}.{_BRONZE}.generation_manifest LIMIT 1"


class WarehouseTools:
    def __init__(self, client: WorkspaceClient) -> None:
        self._client = client

    def _run(self, sql: str, params: dict[str, str]) -> ToolResult:
        rows = run_query(self._client, sql, params)
        return ToolResult(rows=rows, sql=sql, row_count=len(rows))

    def claim(self, claim_id: str) -> dict | None:
        rows = run_query(self._client, _CLAIM_SQL, {"claim_id": claim_id})
        return rows[0] if rows else None

    def sequence(self, policy_id: str, loss_date: str) -> ToolResult:
        return self._run(_SEQUENCE_SQL, {"policy_id": policy_id, "loss_date": str(loss_date)})

    def relevant_changes(self, policy_id: str, claim_id: str) -> ToolResult:
        return self._run(_RELEVANT_SQL, {"policy_id": policy_id, "claim_id": claim_id})

    def pattern_matches(self, policy_id: str, claim_id: str) -> ToolResult:
        return self._run(_PATTERNS_SQL, {"policy_id": policy_id, "claim_id": claim_id})

    def similar(self, policy_id: str, k: int = 5) -> ToolResult:
        return self._run(_SIMILAR_SQL, {"policy_id": policy_id, "k": str(k)})

    def anchor_date(self) -> str:
        rows = run_query(self._client, _ANCHOR_SQL)
        return str(rows[0]["anchor_date"]) if rows else ""


class GenieTool:
    def __init__(self, client: WorkspaceClient) -> None:
        self._client = client

    def ask(self, question: str, conversation_id: str | None = None) -> tuple[str | None, GenieResult]:
        return ask_genie(self._client, conversation_id, question)


def stage(conn, table: str, rows: list[dict]) -> None:
    payload = [(i, json.dumps(row, default=str)) for i, row in enumerate(rows, start=1)]
    with conn.cursor() as cur:
        cur.executemany(f"INSERT INTO review.{table} (n, row) VALUES (%s, %s::jsonb)", payload)


_SELECT_ONLY = re.compile(r"^\s*(with\b[\s\S]*?\)\s*)?select\b", re.IGNORECASE)


class ScratchSql:
    """SELECT-only, row-capped, statement-budgeted SQL on the Working Branch."""

    def __init__(self, conn, max_statements: int = 8, max_rows: int = 50) -> None:
        self._conn = conn
        self.max_statements = max_statements
        self.max_rows = max_rows
        self.statements: list[str] = []

    def run(self, sql: str) -> dict[str, Any]:
        if len(self.statements) >= self.max_statements:
            raise BudgetExceeded(f"scratch SQL budget of {self.max_statements} statements exhausted")
        self.statements.append(sql)
        if ";" in sql.strip().rstrip(";") or not _SELECT_ONLY.match(sql or ""):
            return {"error": "only a single SELECT statement is allowed"}
        try:
            with self._conn.transaction(), self._conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '10s'")
                cur.execute("SET LOCAL transaction_read_only = on")
                cur.execute(sql)
                columns = [d.name for d in (cur.description or [])]
                rows = [list(r) for r in cur.fetchmany(self.max_rows)]
        except Exception as exc:  # noqa: BLE001 - the model sees the error and may try again within budget
            return {"error": str(exc)[:300]}
        return {"columns": columns, "rows": rows, "row_count": len(rows)}
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest app/backend/tests/test_review_tools.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/backend/review/tools.py app/backend/tests/test_review_tools.py
git commit -m "Review agent: tool allowlist — deterministic reads, Genie, staging, scratch SQL"
```

---

### Task 8: Prompts and the harness

**Files:**
- Create: `app/backend/review/prompts.py`
- Create: `app/backend/review/harness.py`
- Test: `app/backend/tests/test_review_harness.py`

**Interfaces:**
- Consumes: Tasks 2–7 (`violations`, `Situation`, `detect_situation`, `window_days`, `canonical_question`, `validate_question`, `ModelClient`, `parse_json_object`, `ModelOutputError`, `WorkingBranch`, `BranchLifecycle`, `ensure_stage_tables`, `stage`, `ScratchSql`, `BudgetExceeded`, `WarehouseTools`, `GenieTool`, `ToolResult`, store methods).
- Produces:
  - `@dataclass RunDeps(store, warehouse: WarehouseTools, genie: GenieTool, model: ModelClient, branches: BranchLifecycle, connect_branch: Callable[[WorkingBranch], Any], clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep, demo_hold_seconds: int = 0, run_timeout_seconds: int = 180, tracer: Tracer | None = None)`
  - `@dataclass RunOutcome(run_id: str, claim_id: str, status: str, failure: str | None, brief: dict | None, trace_id: str | None, elapsed_seconds: float)`
  - `run_brief(claim_id: str, deps: RunDeps, run_id: str | None = None) -> RunOutcome`
  - `class Tracer(Protocol)`: `span(name, kind) -> ContextManager`, `last_trace_id() -> str | None`; `NoopTracer`, `MlflowTracer(experiment: str)`.
  - `prompts.SYSTEM`, `prompts.question_prompt(situation, context) -> str`, `prompts.follow_up_prompt(question, result_preview) -> str`, `prompts.sentence_prompt(section, staged_preview, scratch_history) -> str`.
  - `LINE_NAMES` mapping (`BI`, `PD`, `COLL`, `COMP`, `UMUIM` → human names, copied from `pipeline/transformations.py`).

- [ ] **Step 1: Write the failing tests (fakes for every dependency)**

```python
# app/backend/tests/test_review_harness.py
"""The harness owns the plan (ADR-0018): section order, budgets, the
vocabulary drop, promotion only on success, branch deletion on both paths."""

import json

import pytest

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
    assert "suspicious" in section["sentence_dropped_reason"]


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


def test_scratch_sql_budget_is_enforced_and_run_still_completes():
    store = InMemoryReviewStore(); _routed(store)
    class SqlHungryModel(ScriptedModel):
        def complete(self, system, user, *, max_tokens=800):
            if 'section "sequence"' in user:
                return json.dumps({"sql": "SELECT count(*) FROM review.stage_timeline"})
            return super().complete(system, user, max_tokens=max_tokens)
    outcome = run_brief("C-1", make_deps(store=store, model=SqlHungryModel()))
    assert outcome.status == "completed"
    seq = store.get_claim("C-1")["brief"]["sections"]["sequence"]
    assert seq["sentence"] is None and "budget" in seq["sentence_dropped_reason"]


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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest app/backend/tests/test_review_harness.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the prompts**

```python
# app/backend/review/prompts.py
"""Fixed prompts (ADR-0018). Versioned here, never assembled ad hoc.

The system prompt carries the glossary the model must use and the JSON
contracts for its three kinds of turn. Every turn returns exactly one
JSON object.
"""

from __future__ import annotations

import json

from .vocabulary import BANNED_VOCABULARY, JUDGEMENT_WORDS

PROMPT_VERSION = "2026-09-17.1"

LINE_NAMES = {
    "BI": "bodily injury liability", "PD": "property damage liability", "COLL": "collision",
    "COMP": "comprehensive", "UMUIM": "uninsured/underinsured motorist",
}

SYSTEM = f"""You assist a claims examiner by restating facts from staged data. You never judge.

Definitions (use these words exactly):
- Material Change: a policy change in one of five categories — coverage, deductible, vehicle, address, status. Premium and agent changes are Derived Changes: shown, never counted.
- Relevant Change: a coverage or deductible change on the same coverage line the claim was filed against.
- Change Timing: 'before_loss' or 'after_loss_before_report'. The latter means the change fell inside the loss-to-report gap.
- High-Severity Claim: severity band severe or catastrophic.
- Comparison Group: the population a rate is measured against. A rate is never stated without one.
- Noteworthy Pattern: a named, deterministic rule that matched. Never a score.

Rules:
- Never use any of these words: {", ".join(BANNED_VOCABULARY + JUDGEMENT_WORDS)}.
- Never characterise the policyholder. Never say what anyone intended.
- Every sentence states a fact that is present in the staged rows you are shown or that you computed with SQL over them.
- Reply with exactly one JSON object and nothing else. No prose outside the JSON.
"""

_SHAPE_TEXT = {
    "relevant_in_gap": "How often same-line coverage or deductible changes fall inside the loss-to-report gap versus before the loss, for changes with a linked claim, with both counts.",
    "relevant_before_loss": "How often a same-line limit increase within N days before a claim precedes a high-severity claim, compared with same-line increases not followed by one, with both groups and their sizes. N is the window given below.",
    "pattern_only": "How common the named pattern is among policies with high-severity claims versus policies without, with both rates and sample sizes.",
    "nothing_before": "What share of high-severity claims had no material change in the 365 days before the loss, compared with high-severity claims that did, with both counts.",
}


def question_prompt(situation: str, context: dict, rejection: str | None = None) -> str:
    retry = f"\nYour previous proposal was rejected: {rejection}. Fix that and propose again.\n" if rejection else ""
    return f"""Choose the frequency question for this claim.

Detected situation: {situation}
Required shape: {_SHAPE_TEXT[situation]}
Context: {json.dumps(context, default=str)}
{retry}
Write one natural-language question for a text-to-SQL analyst over these tables: policy_change_event, claim_event, policy_profile, policy_pattern_match. Name the coverage line by its full name. The question must ask for a comparison (use 'versus' or 'compared with') and for both groups' counts or rates.

Reply: {{"shape": "{situation}", "question": "<the question>"}}"""


def follow_up_prompt(question: str, preview: dict) -> str:
    return f"""You asked: {question}
The analyst returned: {json.dumps(preview, default=str)}

You may ask ONE narrowing follow-up in the same conversation if, and only if, the result is missing a comparison group or a sample size. Otherwise decline.

Reply: {{"follow_up": "<question>"}} or {{"follow_up": null}}"""


def sentence_prompt(section: str, preview: dict, scratch_history: list[dict], policy_id: str) -> str:
    history = ""
    if scratch_history:
        history = "\nSCRATCH RESULT(S) so far:\n" + "\n".join(json.dumps(h, default=str) for h in scratch_history)
    tables = "review.stage_timeline, review.stage_relevant_changes, review.stage_patterns, review.stage_frequency, review.stage_similar (each: n int, row jsonb — use row->>'column')"
    return f"""Write one sentence for section "{section}" of the Brief for policy {policy_id}.

Staged rows (preview): {json.dumps(preview, default=str)}
{history}
You may first run ONE SELECT over the staged tables ({tables}) to compute a fact, then write the sentence on your next turn. At most three turns.

Reply with ONE of:
{{"sql": "<single SELECT>"}}
{{"sentence": "<one factual sentence, under 40 words, no other policy ids>"}}"""
```

- [ ] **Step 4: Write the harness**

```python
# app/backend/review/harness.py
"""The Claim Review Brief harness (ADR-0017, ADR-0018).

Fixed plan: claim -> branch -> sequence -> relevant changes -> question ->
Genie -> similar -> sentences -> promote -> delete branch. The model is
consulted at exactly three points (question, follow-up, sentences) and
never touches the plan, main, or the branch lifecycle.
"""

from __future__ import annotations

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
                     __import__("json").dumps(payload or {}, default=str)),
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
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest app/backend/tests/test_review_harness.py -q`
Expected: 9 passed. If `test_timeout_fails_the_run` fails because the clock iterator is exhausted, extend the `ticks` list — every `step()` and the outcome consume one tick.

- [ ] **Step 6: Run the whole backend suite**

Run: `pytest app/backend/tests -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add app/backend/review/prompts.py app/backend/review/harness.py app/backend/tests/test_review_harness.py
git commit -m "Review agent: the harness — fixed plan, budgets, vocabulary drop, promote-or-nothing"
```

---

### Task 9: Routing rule and the runner (deps assembly, queue worker, background thread)

**Files:**
- Create: `app/backend/review/routing.py`
- Create: `app/backend/review/runner.py`
- Test: `app/backend/tests/test_review_routing.py`, `app/backend/tests/test_review_runner.py`

**Interfaces:**
- Produces (`routing.py`): `ROUTING_RULE_TEXT = "High-severity claim reported in the last 90 days."`, `ROUTING_SQL: str`, `route_claims(client, store) -> int` (rows upserted).
- Produces (`runner.py`): `build_deps(client, store, *, demo_hold_seconds=None, tracer=None) -> RunDeps` (real tools, `MlflowTracer` if `REVIEW_MLFLOW_EXPERIMENT` set and mlflow importable, else `NoopTracer`), `work_queue(deps, cap: int) -> list[RunOutcome]` (sequential), `RunRegistry` with `start(claim_id, deps) -> str | None` (returns run_id, or None if a Run is in progress for that claim), `is_running(claim_id) -> bool`, and a process-wide `registry = RunRegistry()`.

- [ ] **Step 1: Write the failing tests**

```python
# app/backend/tests/test_review_routing.py
from unittest.mock import MagicMock

import backend.review.routing as routing
from backend.review.store import InMemoryReviewStore


def test_routing_sql_encodes_the_rule():
    assert "severity_band IN ('severe', 'catastrophic')" in routing.ROUTING_SQL
    assert "date_sub(m.anchor_date, 90)" in routing.ROUTING_SQL
    assert "generation_manifest" in routing.ROUTING_SQL


def test_route_claims_upserts_each_row_as_rule_routed(monkeypatch):
    rows = [{"claim_id": "C-1", "policy_id": "P-1", "coverage_line": "COLL", "loss_date": "2026-08-01",
             "report_date": "2026-08-05", "settled_amount": "24700", "severity_band": "severe", "anchor_date": "2026-09-17"}]
    monkeypatch.setattr(routing, "run_query", lambda client, sql, params=None: rows)
    store = InMemoryReviewStore()
    assert routing.route_claims(MagicMock(), store) == 1
    row = store.list_queue()[0]
    assert row["routed_by"] == "rule" and row["routing_rule"] == routing.ROUTING_RULE_TEXT
    assert row["settled_amount"] == 24700.0
```

```python
# app/backend/tests/test_review_runner.py
import threading

from backend.review import runner
from backend.review.harness import RunOutcome
from backend.review.store import InMemoryReviewStore


def _claim(store, cid):
    store.upsert_routed_claim({"claim_id": cid, "policy_id": "P-1", "coverage_line": "COLL", "loss_date": "2026-08-01",
                               "report_date": "2026-08-05", "settled_amount": 1.0, "severity_band": "severe"}, "rule", "r")


def test_work_queue_runs_pending_claims_sequentially_up_to_cap(monkeypatch):
    store = InMemoryReviewStore()
    for cid in ("C-1", "C-2", "C-3"):
        _claim(store, cid)
    order = []
    def fake_run_brief(claim_id, deps, run_id=None):
        order.append(claim_id)
        return RunOutcome("r", claim_id, "completed", None, {}, None, 0.1)
    monkeypatch.setattr(runner, "run_brief", fake_run_brief)
    deps = runner.RunDeps(store=store, warehouse=None, genie=None, model=None, branches=None, connect_branch=None)
    outcomes = runner.work_queue(deps, cap=2)
    assert [o.claim_id for o in outcomes] == order and len(order) == 2


def test_registry_starts_one_thread_per_claim_and_reports_running(monkeypatch):
    store = InMemoryReviewStore(); _claim(store, "C-1")
    gate = threading.Event()
    def slow_run_brief(claim_id, deps, run_id=None):
        gate.wait(timeout=5)
        return RunOutcome(run_id, claim_id, "completed", None, {}, None, 0.1)
    monkeypatch.setattr(runner, "run_brief", slow_run_brief)
    deps = runner.RunDeps(store=store, warehouse=None, genie=None, model=None, branches=None, connect_branch=None)
    reg = runner.RunRegistry()
    run_id = reg.start("C-1", deps)
    assert run_id and reg.is_running("C-1")
    assert reg.start("C-1", deps) is None
    gate.set()
    reg.join("C-1", timeout=5)
    assert not reg.is_running("C-1")
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest app/backend/tests/test_review_routing.py app/backend/tests/test_review_runner.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement routing**

```python
# app/backend/review/routing.py
"""The one Routing Rule (CONTEXT.md): a High-Severity Claim whose Report
Date is Recent, measured from the dataset anchor (ADR-0006) so the queue
is stable across regenerations."""

from __future__ import annotations

from databricks.sdk import WorkspaceClient

from ..config import CATALOG, SCHEMA
from ..warehouse import run_query

ROUTING_RULE_TEXT = "High-severity claim reported in the last 90 days."

ROUTING_SQL = f"""
SELECT c.claim_id, c.policy_id, c.coverage_line, CAST(c.loss_date AS STRING) AS loss_date,
       CAST(c.report_date AS STRING) AS report_date, c.settled_amount, c.severity_band,
       CAST(m.anchor_date AS STRING) AS anchor_date
FROM {CATALOG}.{SCHEMA}.claim_event c
CROSS JOIN (SELECT anchor_date FROM {CATALOG}.ptm_bronze.generation_manifest LIMIT 1) m
WHERE c.severity_band IN ('severe', 'catastrophic')
  AND c.report_date >= date_sub(m.anchor_date, 90)
ORDER BY c.report_date DESC
""".strip()


def route_claims(client: WorkspaceClient, store) -> int:
    rows = run_query(client, ROUTING_SQL)
    for row in rows:
        store.upsert_routed_claim(
            {"claim_id": row["claim_id"], "policy_id": row["policy_id"], "coverage_line": row["coverage_line"],
             "loss_date": row["loss_date"], "report_date": row["report_date"],
             "settled_amount": float(row["settled_amount"]), "severity_band": row["severity_band"]},
            routed_by="rule", routing_rule=ROUTING_RULE_TEXT,
        )
    return len(rows)
```

- [ ] **Step 4: Implement the runner**

```python
# app/backend/review/runner.py
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
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest app/backend/tests/test_review_routing.py app/backend/tests/test_review_runner.py -q`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add app/backend/review/routing.py app/backend/review/runner.py app/backend/tests/test_review_routing.py app/backend/tests/test_review_runner.py
git commit -m "Review agent: routing rule, dependency assembly, queue worker and run registry"
```

---

### Task 10: Investigation-to-conversation map on Lakebase, with the in-memory fallback

**Files:**
- Modify: `app/backend/investigations.py`
- Create: `app/backend/review/context.py`
- Test: `app/backend/tests/test_investigations_store.py`

**Interfaces:**
- Produces (`review/context.py`): `get_review_store() -> ReviewStore | InMemoryReviewStore` (lazy singleton: `ReviewStore(connect_main(app client))` when `lakebase_configured()` else `InMemoryReviewStore()`), `set_review_store(store)` (tests), `reset_review_store()`.
- Modifies (`investigations.py`): `InvestigationStore` delegates to the review store's `create_investigation / get_conversation / set_conversation`; `get_conversation_id` raises `InvestigationNotFoundError` when the store returns `MISSING`. The module-level `store` singleton and the `_conversations` attribute used by `conftest.py` are replaced: conftest's autouse fixture calls `reset_review_store()` instead.

- [ ] **Step 1: Write the failing test**

```python
# app/backend/tests/test_investigations_store.py
import pytest

from backend.investigations import InvestigationNotFoundError, InvestigationStore
from backend.review.context import set_review_store
from backend.review.store import InMemoryReviewStore


def test_investigation_store_delegates_to_review_store():
    review = InMemoryReviewStore()
    set_review_store(review)
    store = InvestigationStore()
    inv = store.create()
    assert store.get_conversation_id(inv) is None
    store.set_conversation_id(inv, "conv-1")
    assert review.get_conversation(inv) == "conv-1"
    with pytest.raises(InvestigationNotFoundError):
        store.get_conversation_id("nope")
```

- [ ] **Step 2: Update conftest**

In `app/backend/tests/conftest.py` replace the `_reset_investigation_store` fixture with:

```python
from backend.review.context import reset_review_store, set_review_store  # noqa: E402
from backend.review.store import InMemoryReviewStore  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_review_store():
    set_review_store(InMemoryReviewStore())
    yield
    reset_review_store()
```

and delete the `from backend.investigations import store` import.

- [ ] **Step 3: Run to verify failure**

Run: `pytest app/backend/tests/test_investigations_store.py -q`
Expected: FAIL with `ModuleNotFoundError: backend.review.context`

- [ ] **Step 4: Implement**

```python
# app/backend/review/context.py
"""Process-wide review store (app identity, ADR-0019). Lakebase when
configured, in-memory otherwise so local dev and tests need no Postgres."""

from __future__ import annotations

import threading

from ..config import APP_SERVICE_PRINCIPAL_ID, lakebase_configured
from .store import InMemoryReviewStore, ReviewStore

_lock = threading.Lock()
_store = None


def get_review_store():
    global _store
    with _lock:
        if _store is None:
            if lakebase_configured():
                from ..deps import _app_client
                from .lakebase import connect_main
                from .schema import ensure_schema
                conn = connect_main(_app_client())
                ensure_schema(conn, APP_SERVICE_PRINCIPAL_ID)
                _store = ReviewStore(conn)
            else:
                _store = InMemoryReviewStore()
        return _store


def set_review_store(store) -> None:
    global _store
    with _lock:
        _store = store


def reset_review_store() -> None:
    set_review_store(None)
```

```python
# app/backend/investigations.py
"""Investigation store: the id-to-Genie-conversation mapping (ADR-0011).

Persisted in Lakebase's review.investigation when configured so an app
restart no longer forgets which conversation a tab belongs to; in-memory
otherwise (local dev, tests)."""

from __future__ import annotations

import uuid

from .review.context import get_review_store
from .review.store import MISSING


class InvestigationNotFoundError(KeyError):
    pass


class InvestigationStore:
    def create(self) -> str:
        investigation_id = str(uuid.uuid4())
        get_review_store().create_investigation(investigation_id)
        return investigation_id

    def get_conversation_id(self, investigation_id: str) -> str | None:
        value = get_review_store().get_conversation(investigation_id)
        if value is MISSING:
            raise InvestigationNotFoundError(investigation_id)
        return value

    def set_conversation_id(self, investigation_id: str, conversation_id: str | None) -> None:
        get_review_store().set_conversation(investigation_id, conversation_id)


store = InvestigationStore()
```

- [ ] **Step 5: Run the whole backend suite**

Run: `pytest app/backend/tests -q`
Expected: all pass (the message tests exercise the new path through the in-memory review store).

- [ ] **Step 6: Commit**

```bash
git add app/backend/investigations.py app/backend/review/context.py app/backend/tests/conftest.py app/backend/tests/test_investigations_store.py
git commit -m "Investigations: conversation map persisted in Lakebase with an in-memory fallback"
```

---

### Task 11: Review API

**Files:**
- Create: `app/backend/review/api.py`
- Modify: `app/backend/main.py`
- Modify: `app/backend/deps.py` (add `viewer_identity(request) -> str | None`)
- Test: `app/backend/tests/test_review_api.py`

**Interfaces:**
- Produces: `router = APIRouter(prefix="/api/review")` with the five endpoints of spec §9.1; `deps.viewer_identity(request)` returns the `x-forwarded-email` header, else `x-forwarded-preferred-username`, else `None`.
- Endpoint payloads:
  - `GET /queue` → `{"queue": [ {claim_id, policy_id, coverage_line, loss_date, report_date, settled_amount, severity_band, routed_by, routing_rule, run_state, active_run_id, has_brief, disposition} ]}`
  - `GET /claims/{claim_id}` → the store's `get_claim` dict, or 404
  - `POST /claims/{claim_id}/brief` → `{"run_id": str | None, "started": bool, "reason": str | None}`; `no_access` → `{"no_access": true}`; unknown claim on the warehouse → 404
  - `GET /runs/{run_id}` → run dict or 404
  - `POST /claims/{claim_id}/disposition` body `{"outcome": str, "note": str | null}` → disposition dict; 400 bad outcome; 409 no Brief

- [ ] **Step 1: Write the failing tests**

```python
# app/backend/tests/test_review_api.py
from unittest.mock import MagicMock

import backend.review.api as api_module
from backend.review.context import get_review_store

CLAIM = {"claim_id": "C-1", "policy_id": "P-10155", "coverage_line": "COLL", "loss_date": "2026-08-01",
         "report_date": "2026-08-05", "settled_amount": 24700.0, "severity_band": "severe"}


def _seed_brief(store):
    store.upsert_routed_claim(CLAIM, "rule", "r")
    store.claim_run("C-1", "run-1"); store.start_run("run-1", "C-1")
    store.complete_run("run-1", "C-1", {"sections": {}}, anchor_date="2026-09-17", trace_id="tr")


def test_queue_and_claim_detail(api):
    store = get_review_store(); _seed_brief(store)
    queue = api.get("/api/review/queue").json()["queue"]
    assert queue[0]["claim_id"] == "C-1" and queue[0]["has_brief"] is True
    detail = api.get("/api/review/claims/C-1").json()
    assert detail["brief"] == {"sections": {}} and detail["run_state"] == "brief_ready"
    assert api.get("/api/review/claims/nope").status_code == 404


def test_prepare_brief_upserts_on_demand_and_starts_a_run(api, mock_client, monkeypatch):
    started = {}
    monkeypatch.setattr(api_module, "lookup_claim", lambda client, claim_id: {**CLAIM, "settled_amount": "24700"})
    monkeypatch.setattr(api_module.registry, "start", lambda claim_id, deps: started.setdefault(claim_id, "run-x"))
    monkeypatch.setattr(api_module, "build_deps", lambda client, store: object())
    resp = api.post("/api/review/claims/C-1/brief")
    assert resp.status_code == 200 and resp.json() == {"run_id": "run-x", "started": True, "reason": None}
    assert get_review_store().get_claim("C-1")["routed_by"] == "on_demand"


def test_prepare_brief_reports_in_progress_without_starting_twice(api, monkeypatch):
    get_review_store().upsert_routed_claim(CLAIM, "rule", "r")
    monkeypatch.setattr(api_module.registry, "start", lambda claim_id, deps: None)
    monkeypatch.setattr(api_module.registry, "run_id_for", lambda claim_id: "run-live")
    monkeypatch.setattr(api_module, "build_deps", lambda client, store: object())
    assert api.post("/api/review/claims/C-1/brief").json() == {"run_id": "run-live", "started": False, "reason": "in_progress"}


def test_prepare_brief_no_access_and_unknown_claim(api, monkeypatch):
    from backend.warehouse import WarehousePermissionError
    def denied(client, claim_id): raise WarehousePermissionError("no")
    monkeypatch.setattr(api_module, "lookup_claim", denied)
    assert api.post("/api/review/claims/C-9/brief").json() == {"no_access": True}
    monkeypatch.setattr(api_module, "lookup_claim", lambda client, claim_id: None)
    assert api.post("/api/review/claims/C-9/brief").status_code == 404


def test_run_status_endpoint(api):
    store = get_review_store(); _seed_brief(store)
    assert api.get("/api/review/runs/run-1").json()["status"] == "completed"
    assert api.get("/api/review/runs/none").status_code == 404


def test_disposition_records_viewer_identity(api):
    store = get_review_store(); _seed_brief(store)
    resp = api.post("/api/review/claims/C-1/disposition", json={"outcome": "closer_look", "note": "see timeline"},
                    headers={"x-forwarded-email": "dana@example.com"})
    assert resp.status_code == 200 and resp.json()["recorded_by"] == "dana@example.com"
    assert api.post("/api/review/claims/C-1/disposition", json={"outcome": "bogus"}).status_code == 400
    store.upsert_routed_claim({**CLAIM, "claim_id": "C-2"}, "rule", "r")
    assert api.post("/api/review/claims/C-2/disposition", json={"outcome": "closer_look"}).status_code == 409
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest app/backend/tests/test_review_api.py -q`
Expected: FAIL with `ModuleNotFoundError: backend.review.api`

- [ ] **Step 3: Add `viewer_identity` to deps.py**

Append to `app/backend/deps.py`:

```python
def viewer_identity(request: Request) -> str | None:
    """Who the viewer is, from the headers Databricks Apps forwards; None
    locally. Used only for attribution on a Disposition (ADR-0019)."""
    return request.headers.get("x-forwarded-email") or request.headers.get("x-forwarded-preferred-username") or None
```

- [ ] **Step 4: Implement the router**

```python
# app/backend/review/api.py
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
```

- [ ] **Step 5: Wire the router and startup migration in main.py**

In `app/backend/main.py` add after the existing imports:

```python
from .review.api import router as review_router
from .review.context import get_review_store
```

after `app = FastAPI(...)`:

```python
app.include_router(review_router)


@app.on_event("startup")
def _warm_review_store() -> None:
    """Runs the idempotent migration when Lakebase is configured; a
    failure here is logged, not fatal — the investigation surface must
    keep working without the review record."""
    try:
        get_review_store()
    except Exception as exc:  # noqa: BLE001
        print(f"[startup] review store unavailable: {exc}", flush=True)
```

(The router must be included **before** the `app.mount("/", StaticFiles(...))` line, which stays last.)

- [ ] **Step 6: Run the suites**

Run: `pytest app/backend/tests -q`
Expected: all pass. Note `prepare_brief` returns a JSON-serialisable dict because `run_query` yields strings; `get_claim` on the Postgres store returns `date`/`datetime`/`Decimal` values — FastAPI serialises those.

- [ ] **Step 7: Commit**

```bash
git add app/backend/review/api.py app/backend/main.py app/backend/deps.py app/backend/tests/test_review_api.py
git commit -m "Review API: queue, claim detail, on-demand Brief, run status, Disposition"
```

---

### Task 12: Workflow tasks, bundle resources, app config

**Files:**
- Create: `workflow/route_claims_task.py`, `workflow/build_briefs_task.py`
- Modify: `databricks.yml`, `app/app.yaml`
- Test: manual deploy + `databricks bundle validate`

**Interfaces:**
- Consumes: `review.routing.route_claims`, `review.runner.build_deps / work_queue`, `review.schema.ensure_schema`, `review.lakebase.connect_main`, `review.store.ReviewStore`.
- Produces: bundle resources `postgres_projects.ptm_review`, `postgres_branches.ptm_production`, `postgres_endpoints.ptm_primary`, `postgres_databases.ptm_review_db`, `experiments.ptm_review_traces`; job tasks `route_claims`, `build_briefs`; app env vars.

- [ ] **Step 1: Write the routing task**

```python
# workflow/route_claims_task.py
"""Task 5 of ``policy_time_machine_regeneration``: route_claims.

Applies the idempotent review schema to Lakebase main, evaluates the one
Routing Rule against gold, and upserts Routed Claims. Runs as the job's
run-as user (the Lakebase project owner), so it can also grant the app
service principal the table privileges it needs (design spec §7.2).

Same ``--bundle-root`` bootstrap as generate_task.py (serverless
spark_python_task sets neither __file__ nor a script-relative sys.path).
The review package lives under app/backend, which the bundle syncs, so
``<bundle-root>/app`` is added to sys.path and ``backend.review`` imported.
"""

from __future__ import annotations

import os
import sys


def _bundle_root_from_argv() -> str:
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg == "--bundle-root" and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith("--bundle-root="):
            return arg.split("=", 1)[1]
    raise SystemExit("--bundle-root is required (the job task passes ${workspace.file_path})")


_BUNDLE_ROOT = _bundle_root_from_argv()
_APP_ROOT = os.path.join(_BUNDLE_ROOT, "app")
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

from databricks.sdk import WorkspaceClient  # noqa: E402

from backend.config import APP_SERVICE_PRINCIPAL_ID  # noqa: E402
from backend.review.lakebase import connect_main  # noqa: E402
from backend.review.routing import route_claims  # noqa: E402
from backend.review.schema import ensure_schema  # noqa: E402
from backend.review.store import ReviewStore  # noqa: E402


def main() -> int:
    client = WorkspaceClient()
    conn = connect_main(client)
    ensure_schema(conn, APP_SERVICE_PRINCIPAL_ID)
    store = ReviewStore(conn)
    count = route_claims(client, store)
    print(f"[route_claims] {count} routed claims upserted", flush=True)
    return 0


if __name__ == "__main__":
    _exit_code = main()
    if _exit_code:
        sys.exit(_exit_code)
```

- [ ] **Step 2: Write the Brief-building task**

```python
# workflow/build_briefs_task.py
"""Task 6 of ``policy_time_machine_regeneration``: build_briefs.

Works the queue sequentially through the same harness the app uses:
undisposed Routed Claims without a Brief, newest Report Date first,
capped at REVIEW_NIGHTLY_CAP (design spec §10). One Working Branch at a
time (Free Edition compute limit). Never fails the job because a Run
failed — a failed Run is re-queued and reported in the task log.
"""

from __future__ import annotations

import os
import sys


def _bundle_root_from_argv() -> str:
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg == "--bundle-root" and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith("--bundle-root="):
            return arg.split("=", 1)[1]
    raise SystemExit("--bundle-root is required (the job task passes ${workspace.file_path})")


_BUNDLE_ROOT = _bundle_root_from_argv()
_APP_ROOT = os.path.join(_BUNDLE_ROOT, "app")
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

from databricks.sdk import WorkspaceClient  # noqa: E402

from backend.config import REVIEW_NIGHTLY_CAP  # noqa: E402
from backend.review.lakebase import connect_main  # noqa: E402
from backend.review.runner import build_deps, work_queue  # noqa: E402
from backend.review.store import ReviewStore  # noqa: E402


def main() -> int:
    client = WorkspaceClient()
    store = ReviewStore(connect_main(client))
    outcomes = work_queue(build_deps(client, store, demo_hold_seconds=0), cap=REVIEW_NIGHTLY_CAP)
    completed = sum(1 for o in outcomes if o.status == "completed")
    print(f"[build_briefs] {completed}/{len(outcomes)} Runs completed", flush=True)
    return 0


if __name__ == "__main__":
    _exit_code = main()
    if _exit_code:
        sys.exit(_exit_code)
```

- [ ] **Step 3: Bundle resources**

In `databricks.yml`:

1. Add a `variables:` block at top level (after `bundle:`):

```yaml
variables:
  app_service_principal_id:
    description: Application id of the policy-time-machine app's service principal (Apps UI > app > Authorization).
    default: "5ee081ba-a745-4666-8ad2-41d3cfc674db"
  review_model_endpoint:
    description: Pay-per-token Claude endpoint enabled on this workspace's serving page.
    default: "databricks-claude-sonnet-4-5"
```

2. Add to `resources:`:

```yaml
  postgres_projects:
    ptm_review:
      project_id: policy-time-machine
      display_name: Policy Time Machine review record
      pg_version: 17
      permissions:
        - level: CAN_MANAGE
          service_principal_name: ${var.app_service_principal_id}

  postgres_branches:
    ptm_production:
      parent: ${resources.postgres_projects.ptm_review.id}
      branch_id: production
      replace_existing: true
      no_expiry: true

  postgres_endpoints:
    ptm_primary:
      parent: ${resources.postgres_branches.ptm_production.id}
      endpoint_id: primary
      endpoint_type: ENDPOINT_TYPE_READ_WRITE
      autoscaling_limit_min_cu: 0.5
      autoscaling_limit_max_cu: 1

  postgres_databases:
    ptm_review_db:
      parent: ${resources.postgres_branches.ptm_production.id}
      database_id: review

  experiments:
    ptm_review_traces:
      name: /Shared/policy-time-machine-review
      permissions:
        - level: CAN_EDIT
          service_principal_name: ${var.app_service_principal_id}
```

3. Extend the app resource:

```yaml
  apps:
    policy_time_machine_app:
      name: policy-time-machine
      description: "Policy Time Machine — investigation workbench and claim review"
      source_code_path: ./app
      user_api_scopes:
        - dashboards.genie
        - sql
      resources:
        - name: postgres
          postgres:
            branch: ${resources.postgres_branches.ptm_production.name}
            database: ${resources.postgres_databases.ptm_review_db.name}
            permission: CAN_CONNECT_AND_CREATE
```

4. Extend the job environment dependencies and append two tasks after `refresh_pipeline`:

```yaml
            dependencies:
              - "pandas>=3.0,<4"
              - "databricks-sdk>=0.89,<1"
              - "psycopg[binary]>=3.2,<4"
              - "mlflow>=3.1,<4"
```

```yaml
        - task_key: route_claims
          depends_on:
            - task_key: refresh_pipeline
          environment_key: generator_env
          spark_python_task:
            python_file: workflow/route_claims_task.py
            parameters: ["--bundle-root", "${workspace.file_path}"]
        - task_key: build_briefs
          depends_on:
            - task_key: route_claims
          environment_key: generator_env
          spark_python_task:
            python_file: workflow/build_briefs_task.py
            parameters: ["--bundle-root", "${workspace.file_path}"]
```

Both tasks need these env values; add a job-level block:

```yaml
      # Review agent configuration shared by route_claims / build_briefs.
      # (Job task env is not a spark_python_task field; the tasks read them
      # from the bundle-provided job parameters instead.)
      parameters:
        - name: LAKEBASE_PROJECT_ID
          default: policy-time-machine
        - name: APP_SERVICE_PRINCIPAL_ID
          default: ${var.app_service_principal_id}
        - name: REVIEW_MODEL_ENDPOINT
          default: ${var.review_model_endpoint}
        - name: REVIEW_MLFLOW_EXPERIMENT
          default: /Shared/policy-time-machine-review
```

and at the top of both task scripts, before the `backend` imports, copy job parameters into the environment (job parameters reach a spark_python_task as `--name value` argv pairs only if listed in `parameters`; the simpler, verified path on serverless is `dbutils.widgets`, which is unavailable in a plain Python task — so use this explicit read):

```python
import json  # noqa: E402
_PARAMS = {"LAKEBASE_PROJECT_ID": "policy-time-machine",
           "APP_SERVICE_PRINCIPAL_ID": None, "REVIEW_MODEL_ENDPOINT": None, "REVIEW_MLFLOW_EXPERIMENT": None}
for _i, _arg in enumerate(sys.argv[1:]):
    if _arg.startswith("--") and _arg[2:] in _PARAMS and _i + 2 <= len(sys.argv[1:]):
        os.environ.setdefault(_arg[2:], sys.argv[1:][_i + 1])
os.environ.setdefault("LAKEBASE_PROJECT_ID", "policy-time-machine")
```

and pass them explicitly in each task's `parameters` list:

```yaml
            parameters:
              - "--bundle-root"
              - "${workspace.file_path}"
              - "--LAKEBASE_PROJECT_ID"
              - "policy-time-machine"
              - "--APP_SERVICE_PRINCIPAL_ID"
              - "${var.app_service_principal_id}"
              - "--REVIEW_MODEL_ENDPOINT"
              - "${var.review_model_endpoint}"
              - "--REVIEW_MLFLOW_EXPERIMENT"
              - "/Shared/policy-time-machine-review"
```

(Drop the job-level `parameters:` block if the CLI rejects it; the argv path is the one the tasks rely on.)

5. App env in `app/app.yaml`, appended to `env:`:

```yaml
  - name: LAKEBASE_PROJECT_ID
    value: "policy-time-machine"
  - name: APP_SERVICE_PRINCIPAL_ID
    value: "5ee081ba-a745-4666-8ad2-41d3cfc674db"
  - name: REVIEW_MODEL_ENDPOINT
    value: "databricks-claude-sonnet-4-5"
  - name: REVIEW_MLFLOW_EXPERIMENT
    value: "/Shared/policy-time-machine-review"
  - name: REVIEW_DEMO_HOLD_SECONDS
    value: "0"
```

(`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGSSLMODE` are injected by the resource binding.)

6. The app SP needs CAN RUN on the Genie space. Add to `genie/build_space.py`'s post-create step, or run once:

```bash
databricks api patch /api/2.0/permissions/genie/01f1a5808edd1859b78359723b7c5379 --json '{"access_control_list":[{"service_principal_name":"5ee081ba-a745-4666-8ad2-41d3cfc674db","permission_level":"CAN_RUN"}]}'
```

- [ ] **Step 4: Validate and deploy**

Run: `databricks bundle validate && databricks bundle deploy`
Expected: validate passes; deploy creates the project, branch, endpoint, database and experiment, updates the app and job. If `postgres_databases` requires the endpoint to exist first, add `depends_on` per the CLI error. Record the created project's owner: it is your user, so the Workflow's run-as identity has the superuser role.

- [ ] **Step 5: Smoke the deployed pieces**

```bash
databricks bundle run policy_time_machine_regeneration --only route_claims   # if --only is unsupported, run the job and watch task 5
databricks apps deploy policy-time-machine --source-code-path "/Workspace$(databricks bundle summary -o json | python -c 'import sys,json;print(json.load(sys.stdin)["workspace"]["file_path"])')/app"
curl -s "$(databricks apps get policy-time-machine -o json | python -c 'import sys,json;print(json.load(sys.stdin)["url"])')/api/review/queue" -H "Authorization: Bearer $(databricks auth token -o json | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')" | head -c 400
```

Expected: the queue endpoint returns rule-routed claims.

- [ ] **Step 6: Commit**

```bash
git add workflow/route_claims_task.py workflow/build_briefs_task.py databricks.yml app/app.yaml
git commit -m "Bundle: Lakebase project, review experiment, routing and brief-building tasks"
```

---

### Task 13: Review view (queue, Brief panel, Run panel, Disposition) and the view toggle

**Files:**
- Modify: `app/frontend/src/api/client.js`, `app/frontend/src/api/mockData.js`
- Create: `app/frontend/src/views/ReviewView.jsx`, `app/frontend/src/views/ReviewView.css`
- Create: `app/frontend/src/components/review/QueueList.jsx`, `BriefPanel.jsx`, `RunPanel.jsx`, `DispositionForm.jsx`, `review.css`
- Modify: `app/frontend/src/App.jsx`, `app/frontend/src/components/AppHeader.jsx`, `AppHeader.css`
- Test: `app/frontend/src/views/ReviewView.test.jsx`

**Interfaces:**
- Produces (client.js): `getReviewQueue()`, `getReviewClaim(claimId)`, `prepareBrief(claimId)`, `getRun(runId)`, `recordDisposition(claimId, outcome, note)`; mock twins in `mockData.js`: `mockGetReviewQueue`, `mockGetReviewClaim`, `mockPrepareBrief`, `mockGetRun`, `mockRecordDisposition` (a module-level fake queue with one rule-routed claim carrying a complete Brief and one without).
- Produces: `<ReviewView selectedClaimId onSelectClaim onOpenAsInvestigation />`; `<QueueList rows selectedId onSelect />`; `<BriefPanel brief noAccess onOpenAsInvestigation />`; `<RunPanel runId onFinished />`; `<DispositionForm claimId disposition onRecorded />`.
- Modifies App: `view` state `'investigate' | 'review'`, `reviewClaimId` state; `AppHeader` gets `view`, `onViewChange`; header renders two buttons, `Investigate` and `Review`, with `aria-pressed`.
- UI copy (fixed): outcomes render as "Warrants a closer look", "Nothing noteworthy", "Needs more information". Run panel steps map `current_step` → copy: `branch_created` → "Working Branch created: <name>", `sequence` → "Section 1: the sequence", `relevant_changes` → "Section 2: the relevant changes", `question_chosen` → "Model chose the frequency question", `genie_answered` → "Genie answered", `genie_follow_up` → "Genie follow-up", `similar` → "Section 4: similar histories", `sentence_*` → "Sentences validated against the vocabulary", `promoted` → "Brief promoted to the review record", `demo_hold` → "Holding the branch for inspection", `branch_deleted` → "Working Branch deleted by the harness".

- [ ] **Step 1: Write the failing tests**

```jsx
// app/frontend/src/views/ReviewView.test.jsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../api/client.js', async () => {
  const mockData = await import('../api/mockData.js');
  return {
    MOCK_MODE: true,
    getTimeline: mockData.mockGetTimeline,
    getPatterns: mockData.mockGetPatterns,
    getReviewQueue: mockData.mockGetReviewQueue,
    getReviewClaim: mockData.mockGetReviewClaim,
    prepareBrief: mockData.mockPrepareBrief,
    getRun: mockData.mockGetRun,
    recordDisposition: mockData.mockRecordDisposition,
  };
});

const { default: ReviewView } = await import('./ReviewView.jsx');

describe('ReviewView (mock mode)', () => {
  it('lists the queue with the routing rule and opens a Brief with four sections', async () => {
    render(<ReviewView selectedClaimId={null} onSelectClaim={() => {}} onOpenAsInvestigation={() => {}} />);
    await waitFor(() => expect(screen.getByText('High-severity claim reported in the last 90 days.')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /C-10000001/ }));
    await waitFor(() => expect(screen.getByText('The sequence')).toBeInTheDocument());
    expect(screen.getByText('The relevant changes')).toBeInTheDocument();
    expect(screen.getByText('How common this is')).toBeInTheDocument();
    expect(screen.getByText('Similar histories')).toBeInTheDocument();
    expect(screen.queryByText(/summary/i)).not.toBeInTheDocument();
  });

  it('shows a withheld sentence and lets the reviewer record a Disposition', async () => {
    render(<ReviewView selectedClaimId="C-10000001" onSelectClaim={() => {}} onOpenAsInvestigation={() => {}} />);
    await waitFor(() => expect(screen.getByText(/sentence withheld/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('radio', { name: 'Nothing noteworthy' }));
    fireEvent.click(screen.getByRole('button', { name: 'Record disposition' }));
    await waitFor(() => expect(screen.getByText(/Recorded by/)).toBeInTheDocument());
  });

  it('starts a Run for a claim without a Brief and narrates the harness steps', async () => {
    render(<ReviewView selectedClaimId="C-10000002" onSelectClaim={() => {}} onOpenAsInvestigation={() => {}} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Prepare a Brief' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Prepare a Brief' }));
    await waitFor(() => expect(screen.getByText(/Working Branch created/)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/Working Branch deleted by the harness/)).toBeInTheDocument(), { timeout: 4000 });
  });

  it('"Open as investigation" hands the frequency question up', async () => {
    const open = vi.fn();
    render(<ReviewView selectedClaimId="C-10000001" onSelectClaim={() => {}} onOpenAsInvestigation={open} />);
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Open as investigation' }).length).toBe(4));
    fireEvent.click(screen.getAllByRole('button', { name: 'Open as investigation' })[2]);
    expect(open).toHaveBeenCalledWith(expect.stringMatching(/compared|versus/i));
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd app/frontend && npx vitest run src/views/ReviewView.test.jsx`
Expected: FAIL (module not found)

- [ ] **Step 3: Client functions and mock data**

Append to `app/frontend/src/api/client.js`:

```js
import {
  mockGetReviewQueue, mockGetReviewClaim, mockPrepareBrief, mockGetRun, mockRecordDisposition,
} from './mockData.js';

export async function getReviewQueue() {
  if (MOCK_MODE) { await delay(60); return mockGetReviewQueue(); }
  return jsonOrThrow(await fetch('/api/review/queue'));
}

export async function getReviewClaim(claimId) {
  if (MOCK_MODE) { await delay(60); return mockGetReviewClaim(claimId); }
  return jsonOrThrow(await fetch(`/api/review/claims/${encodeURIComponent(claimId)}`));
}

export async function prepareBrief(claimId) {
  if (MOCK_MODE) { await delay(40); return mockPrepareBrief(claimId); }
  return jsonOrThrow(await fetch(`/api/review/claims/${encodeURIComponent(claimId)}/brief`, { method: 'POST' }));
}

export async function getRun(runId) {
  if (MOCK_MODE) { await delay(30); return mockGetRun(runId); }
  return jsonOrThrow(await fetch(`/api/review/runs/${encodeURIComponent(runId)}`));
}

export async function recordDisposition(claimId, outcome, note) {
  if (MOCK_MODE) { await delay(40); return mockRecordDisposition(claimId, outcome, note); }
  return jsonOrThrow(await fetch(`/api/review/claims/${encodeURIComponent(claimId)}/disposition`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ outcome, note }),
  }));
}
```

(Merge the new names into the existing single `import { ... } from './mockData.js'` at the top rather than adding a second import.)

Append to `app/frontend/src/api/mockData.js`:

```js
// ---- Review record (Claim Review Brief agent) ------------------------------
const RULE = 'High-severity claim reported in the last 90 days.';

function section(title, rows, sql, extra = {}) {
  return { title, rows, sql, row_count: rows.length, sentence: null, sentence_dropped: false, ...extra };
}

const BRIEF_1 = {
  claim_id: 'C-10000001', policy_id: 'P-18492', coverage_line: 'COLL', anchor_date: '2026-09-17',
  built_at: '2026-09-17T08:00:00Z', run_id: 'run-mock1', trace_id: 'tr-mock1',
  sections: {
    sequence: section('The sequence',
      [{ event_date: '2026-05-12', event_type: 'policy_change', event_category: 'address', display_label: 'Address changed', is_material: true },
       { event_date: '2026-05-12', event_type: 'policy_change', event_category: 'coverage', coverage_line: 'COLL', display_label: 'Collision limit raised', old_value: '100000', new_value: '300000', is_material: true },
       { event_date: '2026-05-12', event_type: 'policy_change', event_category: 'premium', display_label: 'Premium recalculated', is_material: false },
       { event_date: '2026-07-14', event_type: 'claim_filed', display_label: 'Collision claim filed', amount: 24700, is_material: false }],
      'SELECT * FROM policy_timeline_event WHERE policy_id = :policy_id AND event_date <= :loss_date AND event_date >= date_sub(:loss_date, 365)',
      { material_change_count: 2, derived_change_count: 1, sentence: 'Two material changes occurred in the year before the loss, both sixty-three days before it.' }),
    relevant_changes: section('The relevant changes',
      [{ change_event_id: 'E-1', change_category: 'coverage', coverage_line: 'COLL', change_timing: 'before_loss', days_to_next_claim_loss: 63, old_value_num: 100000, new_value_num: 300000 }],
      'SELECT * FROM policy_change_event WHERE policy_id = :policy_id AND next_claim_id = :claim_id AND change_relates_to_claimed_coverage = true',
      { patterns: [{ pattern_code: 'coverage_raised_then_claimed_same_line', pattern_name: 'Coverage raised, then a claim on the same line', matched_on_date: '2026-07-14' }],
        situation: 'relevant_before_loss', sentence: 'One relevant change: the collision limit rose from 100,000 to 300,000 sixty-three days before the loss.' }),
    frequency: section('How common this is',
      [['within 90 days, high-severity claim followed', '0.085', '412'], ['increase not followed by high-severity claim', '0.058', '3610']],
      'SELECT ... GROUP BY ...',
      { shape: 'relevant_before_loss', question_source: 'model', follow_up: null, columns: ['group', 'rate', 'n'], genie_status: 'ok',
        question: 'How often does a collision limit increase within 90 days before a claim precede a high-severity claim, compared with collision increases not followed by one?',
        sentence: 'Increases followed by a high-severity claim within 90 days occur at 8.5% against 5.8% for increases not followed by one, with both groups sized.' }),
    similar: section('Similar histories',
      [{ similar_policy_id: 'P-20114', rank: 1, similarity_score: 0.91, top_reasons: 'comparable change velocity; coverage increase preceding a same-line claim' }],
      'SELECT * FROM policy_similarity WHERE policy_id = :policy_id AND rank <= 5',
      { sentence: null, sentence_dropped: true, sentence_dropped_reason: 'vocabulary: suspicious' }),
  },
};

const REVIEW_QUEUE = [
  { claim_id: 'C-10000001', policy_id: 'P-18492', coverage_line: 'COLL', loss_date: '2026-07-14', report_date: '2026-07-20', settled_amount: 24700, severity_band: 'severe',
    routed_by: 'rule', routing_rule: RULE, run_state: 'brief_ready', active_run_id: null, has_brief: true, disposition: null },
  { claim_id: 'C-10000002', policy_id: 'P-20114', coverage_line: 'COMP', loss_date: '2026-08-02', report_date: '2026-08-03', settled_amount: 61000, severity_band: 'catastrophic',
    routed_by: 'rule', routing_rule: RULE, run_state: 'queued', active_run_id: null, has_brief: false, disposition: null },
];
const REVIEW_BRIEFS = { 'C-10000001': BRIEF_1 };
const REVIEW_DISPOSITIONS = {};
const RUN_STEPS = ['branch_created', 'sequence', 'relevant_changes', 'question_chosen', 'genie_answered', 'similar', 'sentence_similar', 'promoted', 'branch_deleted'];
const RUNS = {};

export function mockGetReviewQueue() {
  return { queue: REVIEW_QUEUE.map((r) => ({ ...r, has_brief: Boolean(REVIEW_BRIEFS[r.claim_id]), disposition: REVIEW_DISPOSITIONS[r.claim_id] ?? null })) };
}

export function mockGetReviewClaim(claimId) {
  const row = REVIEW_QUEUE.find((r) => r.claim_id === claimId);
  if (!row) throw new Error('Request failed (404)');
  return { ...row, brief: REVIEW_BRIEFS[claimId] ?? null, brief_anchor_date: '2026-09-17', brief_built_at: '2026-09-17T08:00:00Z',
           disposition: REVIEW_DISPOSITIONS[claimId] ?? null, active_run: row.active_run_id ? RUNS[row.active_run_id] : null };
}

export function mockPrepareBrief(claimId) {
  const row = REVIEW_QUEUE.find((r) => r.claim_id === claimId);
  if (!row) throw new Error('Request failed (404)');
  const runId = `run-${claimId}`;
  RUNS[runId] = { run_id: runId, claim_id: claimId, status: 'running', current_step: null, step_count: 0, branch_name: `projects/policy-time-machine/branches/${runId}`, trace_id: null, failure: null };
  row.run_state = 'in_progress'; row.active_run_id = runId;
  let i = 0;
  const tick = () => {
    RUNS[runId].current_step = RUN_STEPS[i]; RUNS[runId].step_count = i + 1;
    if (RUN_STEPS[i] === 'promoted') { REVIEW_BRIEFS[claimId] = { ...BRIEF_1, claim_id: claimId, policy_id: row.policy_id }; row.run_state = 'brief_ready'; }
    if (RUN_STEPS[i] === 'branch_deleted') { RUNS[runId].status = 'completed'; row.active_run_id = null; return; }
    i += 1; setTimeout(tick, 250);
  };
  setTimeout(tick, 100);
  return { run_id: runId, started: true, reason: null };
}

export function mockGetRun(runId) {
  if (!RUNS[runId]) throw new Error('Request failed (404)');
  return { ...RUNS[runId] };
}

export function mockRecordDisposition(claimId, outcome, note) {
  REVIEW_DISPOSITIONS[claimId] = { claim_id: claimId, outcome, note, recorded_by: 'you (mock)', recorded_at: new Date().toISOString() };
  return { ...REVIEW_DISPOSITIONS[claimId] };
}
```

- [ ] **Step 4: Components**

```jsx
// app/frontend/src/components/review/QueueList.jsx
import { formatCurrency, formatEventDate } from '../../lib/format.js';
import './review.css';

const STATE_LABEL = { queued: 'Brief not yet built', in_progress: 'Run in progress', brief_ready: 'Brief ready', failed: 'Last Run failed' };
const OUTCOME_LABEL = { closer_look: 'Warrants a closer look', nothing_noteworthy: 'Nothing noteworthy', more_information: 'Needs more information' };

export default function QueueList({ rows, selectedId, onSelect }) {
  if (!rows) return <div className="queue-empty">Loading the queue…</div>;
  if (rows.length === 0) return <div className="queue-empty">No routed claims yet. The nightly Workflow routes claims; "Prepare a Brief" on a timeline routes one now.</div>;
  return (
    <ul className="queue-list">
      {rows.map((r) => (
        <li key={r.claim_id}>
          <button type="button" className={`queue-row${r.claim_id === selectedId ? ' queue-row--active' : ''}`} onClick={() => onSelect(r.claim_id)}>
            <div className="queue-row-head">
              <span className="queue-claim">{r.claim_id}</span>
              <span className="queue-policy">{r.policy_id}</span>
              <span className="queue-amount">{formatCurrency(Number(r.settled_amount))}</span>
            </div>
            <div className="queue-row-meta">
              <span className="tl-severity-badge" data-band={r.severity_band}>{r.severity_band}</span>
              <span>{r.coverage_line} · reported {formatEventDate(r.report_date)}</span>
            </div>
            <div className="queue-row-rule">{r.routed_by === 'rule' ? r.routing_rule : 'Requested from the timeline'}</div>
            <div className="queue-row-state">
              {r.disposition ? OUTCOME_LABEL[r.disposition.outcome] : STATE_LABEL[r.run_state] ?? r.run_state}
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}
```

```jsx
// app/frontend/src/components/review/RunPanel.jsx
import { useEffect, useState } from 'react';
import { getRun } from '../../api/client.js';
import './review.css';

const STEP_COPY = [
  ['branch_created', 'Working Branch created'],
  ['sequence', 'Section 1: the sequence'],
  ['relevant_changes', 'Section 2: the relevant changes'],
  ['question_chosen', 'Model chose the frequency question'],
  ['genie_answered', 'Genie answered'],
  ['genie_follow_up', 'Genie follow-up'],
  ['similar', 'Section 4: similar histories'],
  ['sentence_', 'Sentences validated against the vocabulary'],
  ['promoted', 'Brief promoted to the review record'],
  ['demo_hold', 'Holding the branch for inspection'],
  ['branch_deleted', 'Working Branch deleted by the harness'],
];

function stepIndex(step) {
  if (!step) return -1;
  return STEP_COPY.findIndex(([key]) => step.startsWith(key));
}

/** Polls one Run and narrates the harness's fixed plan. The model never
 *  appears as the actor of a lifecycle step — the harness does. */
export default function RunPanel({ runId, onFinished }) {
  const [run, setRun] = useState(null);

  useEffect(() => {
    if (!runId) return undefined;
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await getRun(runId);
        if (cancelled) return;
        setRun(next);
        if (next.status === 'running') setTimeout(poll, 1000);
        else onFinished?.(next);
      } catch {
        if (!cancelled) setTimeout(poll, 2000);
      }
    };
    poll();
    return () => { cancelled = true; };
  }, [runId, onFinished]);

  const active = stepIndex(run?.current_step);
  return (
    <div className="run-panel" aria-busy={run?.status === 'running'}>
      <div className="run-head">
        <span className="run-title">{run?.status === 'failed' ? 'Run failed' : run?.status === 'completed' ? 'Run complete' : 'The harness is working'}</span>
        {run?.branch_name && <span className="run-branch">{run.branch_name}</span>}
      </div>
      <ol className="aw-stages">
        {STEP_COPY.map(([key, label], i) => {
          const state = i < active ? 'done' : i === active ? 'active' : 'todo';
          const text = key === 'branch_created' && run?.branch_name ? `${label}: ${run.branch_name.split('/').pop()}` : label;
          return <li key={key} className={`aw-stage aw-stage--${state}`}><span className="aw-dot" aria-hidden="true" /><span className="aw-stage-label">{text}</span></li>;
        })}
      </ol>
      {run?.failure && <div className="run-failure">{run.failure}</div>}
      {run?.trace_id && <div className="run-trace">MLflow trace {run.trace_id}</div>}
    </div>
  );
}
```

```jsx
// app/frontend/src/components/review/BriefPanel.jsx
import EvidenceDrawer from '../EvidenceDrawer.jsx';
import './review.css';

const ORDER = ['sequence', 'relevant_changes', 'frequency', 'similar'];

function rowsToObjects(section) {
  if (section.columns && section.rows.length && Array.isArray(section.rows[0])) {
    return section.rows.map((r) => Object.fromEntries(section.columns.map((c, i) => [c, r[i]])));
  }
  return section.rows;
}

function SectionTable({ rows }) {
  if (!rows.length) return <div className="brief-empty">No rows.</div>;
  const cols = Object.keys(rows[0]);
  return (
    <div className="brief-table-wrap">
      <table className="brief-table">
        <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{cols.map((c) => <td key={c}>{r[c] == null ? '' : String(r[c])}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function questionFor(key, section, brief) {
  if (key === 'frequency') return section.question;
  if (key === 'similar') return `Find policies with histories similar to ${brief.policy_id}.`;
  if (key === 'relevant_changes') return `What changed before the latest claim on ${brief.policy_id}?`;
  return `What changed on policy ${brief.policy_id} during the last year?`;
}

/** Four sections, each with its sentence, its rows and its evidence.
 *  There is deliberately no summary: the weighing is the Disposition. */
export default function BriefPanel({ brief, noAccess, onOpenAsInvestigation }) {
  if (noAccess) {
    return <div className="brief-no-access">You don't have access to the policy data behind this Brief. Unity Catalog governs the source; the Brief mirrors its answer.</div>;
  }
  if (!brief) return null;
  return (
    <div className="brief-panel">
      <div className="brief-head">
        <span className="brief-title">Brief for {brief.claim_id}</span>
        <span className="brief-meta">built against the dataset as of {brief.anchor_date}</span>
      </div>
      {ORDER.map((key) => {
        const s = brief.sections[key];
        if (!s) return null;
        const rows = rowsToObjects(s);
        return (
          <section key={key} className="brief-section">
            <div className="brief-section-head">
              <h3 className="brief-section-title">{s.title}</h3>
              <button type="button" className="brief-open" onClick={() => onOpenAsInvestigation(questionFor(key, s, brief))}>Open as investigation</button>
            </div>
            {key === 'frequency' && (
              <div className="brief-question">
                <span className="brief-question-label">{s.question_source === 'model' ? 'Question the model chose' : 'Canonical question (model proposal rejected)'}</span>
                <p>{s.question}</p>
                {s.follow_up && <p className="brief-follow-up">Follow-up: {s.follow_up}</p>}
              </div>
            )}
            {key === 'relevant_changes' && s.patterns?.length > 0 && (
              <ul className="brief-patterns">{s.patterns.map((p) => <li key={p.pattern_code}>{p.pattern_name}</li>)}</ul>
            )}
            {s.sentence ? <p className="brief-sentence">{s.sentence}</p>
              : <p className="brief-sentence brief-sentence--withheld">Sentence withheld: {s.sentence_dropped_reason ?? 'vocabulary check'}</p>}
            <SectionTable rows={rows} />
            <EvidenceDrawer rowCount={s.row_count} sql={s.sql} description={s.description ?? null} />
          </section>
        );
      })}
    </div>
  );
}
```

```jsx
// app/frontend/src/components/review/DispositionForm.jsx
import { useState } from 'react';
import { recordDisposition } from '../../api/client.js';
import './review.css';

const OUTCOMES = [
  ['closer_look', 'Warrants a closer look'],
  ['nothing_noteworthy', 'Nothing noteworthy'],
  ['more_information', 'Needs more information'],
];

/** The one human act in the workflow. The agent never proposes a value. */
export default function DispositionForm({ claimId, disposition, onRecorded }) {
  const [outcome, setOutcome] = useState(disposition?.outcome ?? null);
  const [note, setNote] = useState(disposition?.note ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    if (!outcome) return;
    setBusy(true); setError(null);
    try {
      onRecorded(await recordDisposition(claimId, outcome, note.trim() || null));
    } catch (err) {
      setError(err?.message || 'Could not record the disposition.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="disposition" onSubmit={submit}>
      <div className="disposition-title">Disposition</div>
      <div className="disposition-options" role="radiogroup" aria-label="Disposition">
        {OUTCOMES.map(([value, label]) => (
          <label key={value} className="disposition-option">
            <input type="radio" name="outcome" value={value} checked={outcome === value} onChange={() => setOutcome(value)} aria-label={label} />
            {label}
          </label>
        ))}
      </div>
      <textarea className="disposition-note" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Disposition note" />
      <div className="disposition-actions">
        <button type="submit" className="ask-submit" disabled={!outcome || busy}>Record disposition</button>
        {disposition && <span className="disposition-recorded">Recorded by {disposition.recorded_by} · {new Date(disposition.recorded_at).toLocaleString()}</span>}
      </div>
      {error && <div className="app-boot-error">{error}</div>}
    </form>
  );
}
```

```jsx
// app/frontend/src/views/ReviewView.jsx
import { useCallback, useEffect, useState } from 'react';
import { getReviewQueue, getReviewClaim, prepareBrief, getTimeline, getPatterns } from '../api/client.js';
import Timeline from '../components/Timeline.jsx';
import QueueList from '../components/review/QueueList.jsx';
import BriefPanel from '../components/review/BriefPanel.jsx';
import RunPanel from '../components/review/RunPanel.jsx';
import DispositionForm from '../components/review/DispositionForm.jsx';
import './ReviewView.css';

/**
 * The review record: queue on the left, timeline + Brief on the right.
 * Separate from the investigation workbench by design (grill session
 * 2026-09-17, question 7). Access mirrors the on-behalf-of timeline read:
 * if the timeline reports no_access, so does the Brief (ADR-0019).
 */
export default function ReviewView({ selectedClaimId, onSelectClaim, onOpenAsInvestigation }) {
  const [queue, setQueue] = useState(null);
  const [detail, setDetail] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [runId, setRunId] = useState(null);
  const [error, setError] = useState(null);

  const loadQueue = useCallback(async () => {
    try { setQueue((await getReviewQueue()).queue); } catch (err) { setError(err?.message || 'Could not load the queue.'); }
  }, []);

  const loadDetail = useCallback(async (claimId) => {
    if (!claimId) { setDetail(null); setTimeline(null); return; }
    try {
      const next = await getReviewClaim(claimId);
      setDetail(next);
      if (next.active_run?.status === 'running') setRunId(next.active_run.run_id);
      const t = await getTimeline(next.policy_id);
      setTimeline(t.no_access ? { found: false, events: [], patterns: [], noAccess: true }
        : !t.found ? { found: false, events: [], patterns: [] }
          : { found: true, events: t.events, patterns: (await getPatterns(next.policy_id)).patterns ?? [] });
    } catch (err) {
      setError(err?.message || 'Could not load the claim.');
    }
  }, []);

  useEffect(() => { loadQueue(); }, [loadQueue]);
  useEffect(() => { loadDetail(selectedClaimId); }, [selectedClaimId, loadDetail]);

  const onFinished = useCallback(() => { setRunId(null); loadDetail(selectedClaimId); loadQueue(); }, [loadDetail, loadQueue, selectedClaimId]);

  async function startRun() {
    try {
      const res = await prepareBrief(selectedClaimId);
      if (res.no_access) { setTimeline({ found: false, events: [], patterns: [], noAccess: true }); return; }
      setRunId(res.run_id);
    } catch (err) {
      setError(err?.message || 'Could not start a Run.');
    }
  }

  const noAccess = Boolean(timeline?.noAccess);
  return (
    <div className="review-view">
      <aside className="review-queue">
        <div className="review-queue-head">Routed claims</div>
        <QueueList rows={queue} selectedId={selectedClaimId} onSelect={onSelectClaim} />
      </aside>
      <div className="review-detail">
        {error && <div className="app-boot-error">{error}</div>}
        {!detail && <div className="review-placeholder">Select a routed claim.</div>}
        {detail && (
          <div className="review-split">
            <div className="timeline-region">
              <Timeline policyId={detail.policy_id} data={timeline} onFindSimilar={() => {}} findSimilarBusy />
            </div>
            <div className="review-brief-region">
              {runId && <RunPanel runId={runId} onFinished={onFinished} />}
              {!runId && !detail.brief && !noAccess && (
                <div className="review-no-brief">
                  <p>No Brief yet for {detail.claim_id}.</p>
                  <button type="button" className="ask-submit" onClick={startRun}>Prepare a Brief</button>
                </div>
              )}
              {(detail.brief || noAccess) && !runId && (
                <>
                  <BriefPanel brief={detail.brief} noAccess={noAccess} onOpenAsInvestigation={onOpenAsInvestigation} />
                  {!noAccess && <DispositionForm claimId={detail.claim_id} disposition={detail.disposition}
                    onRecorded={(d) => { setDetail({ ...detail, disposition: d }); loadQueue(); }} />}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

```css
/* app/frontend/src/views/ReviewView.css */
.review-view { flex: 1; display: flex; min-height: 0; }
.review-queue { width: 320px; border-right: 1px solid var(--line); background: var(--panel); overflow-y: auto; }
.review-queue-head { padding: var(--space-2) var(--space-2) var(--space-1); font-family: var(--font-display); font-weight: 600; color: var(--ink-600); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; }
.review-detail { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.review-split { flex: 1; display: flex; min-height: 0; }
.review-brief-region { flex: 1; min-width: 0; overflow-y: auto; padding: var(--space-2) var(--space-3); }
.review-placeholder, .review-no-brief { padding: var(--space-4); color: var(--ink-600); }
```

```css
/* app/frontend/src/components/review/review.css */
.queue-list { list-style: none; margin: 0; padding: 0; }
.queue-row { width: 100%; text-align: left; background: transparent; border: 0; border-bottom: 1px solid var(--line); padding: 12px var(--space-2); cursor: pointer; font: inherit; color: inherit; }
.queue-row--active { background: var(--agent-soft); box-shadow: inset 3px 0 0 var(--agent); }
.queue-row-head { display: flex; gap: 8px; align-items: baseline; }
.queue-claim { font-family: var(--font-mono); font-weight: 600; }
.queue-policy { color: var(--ink-600); font-family: var(--font-mono); font-size: 12px; }
.queue-amount { margin-left: auto; color: var(--claim); font-weight: 600; }
.queue-row-meta, .queue-row-rule, .queue-row-state { font-size: 12px; color: var(--ink-600); margin-top: 4px; display: flex; gap: 8px; align-items: center; }
.queue-row-state { color: var(--agent-strong); font-weight: var(--w-medium); }
.queue-empty { padding: var(--space-2); color: var(--ink-600); font-size: 13px; }
.run-panel { background: var(--panel); border: 1px solid var(--agent-rail); border-radius: var(--radius-lg); padding: var(--space-2); margin-bottom: var(--space-2); }
.run-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.run-title { font-family: var(--font-display); font-weight: 600; color: var(--agent-strong); }
.run-branch, .run-trace { font-family: var(--font-mono); font-size: 12px; color: var(--ink-600); }
.run-failure { color: var(--claim); font-size: 13px; margin-top: 8px; }
.brief-panel { display: flex; flex-direction: column; gap: var(--space-2); }
.brief-head { display: flex; justify-content: space-between; align-items: baseline; }
.brief-title { font-family: var(--font-display); font-weight: 700; font-size: 18px; }
.brief-meta { font-size: 12px; color: var(--ink-300); }
.brief-section { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius-lg); padding: var(--space-2); box-shadow: var(--shadow-1); }
.brief-section-head { display: flex; justify-content: space-between; align-items: baseline; }
.brief-section-title { margin: 0; font-family: var(--font-display); font-size: 15px; }
.brief-open { background: transparent; border: 1px solid var(--agent-rail); color: var(--agent); border-radius: var(--radius-pill); padding: 4px 10px; font: inherit; font-size: 12px; cursor: pointer; }
.brief-question { background: var(--agent-soft); border-radius: var(--radius); padding: 8px 12px; margin: 8px 0; }
.brief-question-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--agent-strong); }
.brief-question p { margin: 4px 0 0; }
.brief-follow-up { color: var(--ink-600); font-size: 13px; }
.brief-sentence { font-size: 15px; margin: 8px 0; }
.brief-sentence--withheld { color: var(--ink-300); font-style: italic; }
.brief-patterns { margin: 4px 0; padding-left: 18px; font-size: 13px; }
.brief-table-wrap { overflow-x: auto; max-height: 260px; overflow-y: auto; border: 1px solid var(--line); border-radius: var(--radius); }
.brief-table { border-collapse: collapse; font-size: 12.5px; width: 100%; }
.brief-table th, .brief-table td { padding: 6px 8px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }
.brief-table th { position: sticky; top: 0; background: var(--paper); font-weight: var(--w-medium); }
.brief-empty { color: var(--ink-300); font-size: 13px; }
.brief-no-access { padding: var(--space-3); color: var(--ink-600); background: var(--panel); border-radius: var(--radius-lg); }
.disposition { margin-top: var(--space-2); background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius-lg); padding: var(--space-2); }
.disposition-title { font-family: var(--font-display); font-weight: 600; margin-bottom: 8px; }
.disposition-options { display: flex; gap: var(--space-2); flex-wrap: wrap; }
.disposition-option { display: flex; gap: 6px; align-items: center; font-size: 14px; }
.disposition-note { width: 100%; min-height: 64px; margin: 8px 0; font: inherit; border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 8px; }
.disposition-actions { display: flex; gap: var(--space-2); align-items: center; }
.disposition-recorded { font-size: 12px; color: var(--ink-600); }
```

- [ ] **Step 5: View toggle in App and AppHeader**

In `AppHeader.jsx`, add props `view` and `onViewChange` and render, inside `.brand-row` after `.brand`:

```jsx
<div className="view-toggle" role="group" aria-label="View">
  <button type="button" className="view-btn" aria-pressed={view === 'investigate'} onClick={() => onViewChange('investigate')}>Investigate</button>
  <button type="button" className="view-btn" aria-pressed={view === 'review'} onClick={() => onViewChange('review')}>Review</button>
</div>
```

and render `<TabBar …/>` only when `view === 'investigate'`. Append to `AppHeader.css`:

```css
.view-toggle { display: flex; gap: 4px; background: var(--paper); border-radius: var(--radius-pill); padding: 3px; }
.view-btn { border: 0; background: transparent; padding: 6px 14px; border-radius: var(--radius-pill); font: inherit; font-weight: var(--w-medium); color: var(--ink-600); cursor: pointer; }
.view-btn[aria-pressed="true"] { background: var(--panel); color: var(--agent-strong); box-shadow: var(--shadow-1); }
```

In `App.jsx`: add `const [view, setView] = useState('investigate'); const [reviewClaimId, setReviewClaimId] = useState(null);`, pass `view={view} onViewChange={setView}` to `AppHeader`, wrap the existing `tabs.map(...)` in `<div hidden={view !== 'review' ? false : true}>` (keep workspaces mounted), and render:

```jsx
{view === 'review' && (
  <ReviewView
    selectedClaimId={reviewClaimId}
    onSelectClaim={setReviewClaimId}
    onOpenAsInvestigation={(question) => { addTab({ seedQuestion: question }); setView('investigate'); }}
  />
)}
```

`addTab` gains an optional `{ seedQuestion }` argument stored on the tab (`{ id, label: null, seedQuestion }`); Task 14 consumes it.

- [ ] **Step 6: Run the frontend tests**

Run: `cd app/frontend && npm test`
Expected: all pass, including the four new ReviewView tests.

- [ ] **Step 7: Commit**

```bash
git add app/frontend/src
git commit -m "Review view: queue, Brief panel, harness Run panel, Disposition, view toggle"
```

---

### Task 14: "Prepare a Brief" on the timeline and seeded investigation tabs

**Files:**
- Modify: `app/frontend/src/components/Timeline.jsx`, `app/frontend/src/components/InvestigationWorkspace.jsx`, `app/frontend/src/hooks/useInvestigation.js`, `app/frontend/src/App.jsx`
- Test: `app/frontend/src/App.test.jsx` (two new cases)

**Interfaces:**
- `Timeline` gains `onPrepareBrief(claimId)`; the claim card renders a "Prepare a Brief" button when the prop is given (`event.source_id` is the claim id for `claim_filed` events, per `pipeline/transformations.py::build_policy_timeline_event`).
- `InvestigationWorkspace` gains `onPrepareBrief` and `seedQuestion`; `useInvestigation(storageKey, seedQuestion)` submits the seed once on first mount when the trail is empty.
- App: `onPrepareBrief` = `async (claimId) => { await prepareBrief(claimId); setReviewClaimId(claimId); setView('review'); }` — the Review view then finds the Run in progress via `active_run` and shows the Run panel.

- [ ] **Step 1: Write the failing tests** (append to `App.test.jsx`; extend the `vi.mock` factory with the review mock functions from Task 13)

```jsx
it('a claim card offers "Prepare a Brief" and switches to the Review view', async () => {
  render(<App />);
  await ask('What changed on P-18492 in the last year?');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Prepare a Brief' })).toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: 'Prepare a Brief' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Review' })).toHaveAttribute('aria-pressed', 'true'));
});

it('a seeded tab asks its question on mount', async () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Review' }));
  await waitFor(() => screen.getByRole('button', { name: /C-10000001/ }));
  fireEvent.click(screen.getByRole('button', { name: /C-10000001/ }));
  await waitFor(() => screen.getAllByRole('button', { name: 'Open as investigation' }));
  fireEvent.click(screen.getAllByRole('button', { name: 'Open as investigation' })[0]);
  await waitFor(() => expect(screen.getByText(/What changed on policy P-18492/)).toBeInTheDocument());
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd app/frontend && npx vitest run src/App.test.jsx`
Expected: the two new cases FAIL.

- [ ] **Step 3: Timeline claim card**

In `Timeline.jsx`, thread `onPrepareBrief` from `Timeline` → `TimelineCard` → `ClaimCard`, and inside `ClaimCard`'s `.tl-card--claim` after the note:

```jsx
{onPrepareBrief && event.source_id && (
  <button type="button" className="prepare-brief-btn" onClick={() => onPrepareBrief(event.source_id)} title="Route this claim and build its Brief">
    Prepare a Brief
  </button>
)}
```

Add to `Timeline.css`:

```css
.prepare-brief-btn { margin-top: 8px; background: var(--agent-soft); color: var(--agent-strong); border: 1px solid var(--agent-rail); border-radius: var(--radius-pill); padding: 4px 10px; font: inherit; font-size: 12px; cursor: pointer; }
```

- [ ] **Step 4: Seeded question in the hook**

In `useInvestigation.js`, change the signature to `export function useInvestigation(storageKey, seedQuestion)` and add after `submitQuestion` is defined:

```js
// A tab opened from a Brief section starts with that section's question.
// Once only, and only when there is nothing in the trail to preserve.
const seededRef = useRef(false);
useEffect(() => {
  if (seedQuestion && !seededRef.current && trail.length === 0 && !genieLoading) {
    seededRef.current = true;
    submitQuestion(seedQuestion);
  }
}, [seedQuestion, trail.length, genieLoading, submitQuestion]);
```

- [ ] **Step 5: Workspace and App wiring**

`InvestigationWorkspace({ storageKey, onLabel, onNewInvestigation, onPrepareBrief, seedQuestion })` passes `seedQuestion` to the hook and `onPrepareBrief={onPrepareBrief}` to `<Timeline>`. In `App.jsx`, pass `seedQuestion={tab.seedQuestion ?? null}` and

```jsx
onPrepareBrief={async (claimId) => {
  try { await prepareBrief(claimId); } catch { /* the Review view shows the state either way */ }
  setReviewClaimId(claimId);
  setView('review');
}}
```

(import `prepareBrief` from `./api/client.js`).

- [ ] **Step 6: Run the frontend tests and the build**

Run: `cd app/frontend && npm test && npm run build`
Expected: all pass; build succeeds (the bundle syncs `dist/`).

- [ ] **Step 7: Commit**

```bash
git add app/frontend/src
git commit -m "Timeline: Prepare a Brief; investigation tabs can be seeded from a Brief section"
```

---

### Task 15: Live checks — branch smoke test and the Brief contract

**Files:**
- Create: `ci/review/__init__.py` (empty), `ci/review/smoke_branch.py`, `ci/review/run_brief_contract.py`
- Test: these *are* the tests; they run against the workspace with the `DEFAULT` CLI profile, like `ci/genie/run_contracts.py`.

**Interfaces:**
- Consumes: `backend.review.lakebase.BranchLifecycle / connect_branch / connect_main`, `backend.review.runner.build_deps / run_brief`, `backend.review.store.ReviewStore`, `backend.review.schema.ensure_schema`, `ci.genie.config` (profile, catalog, schema, warehouse), `ci.genie.genie_client.run_warehouse_query`.
- Produces: `python -m ci.review.smoke_branch` (exit 0/1) and `python -m ci.review.run_brief_contract` (3 runs, JSON results under `ci/review/results/`).

- [ ] **Step 1: Smoke test**

```python
#!/usr/bin/env python3
"""Working Branch lifecycle smoke test: create branch + endpoint, connect,
SELECT 1, delete. Fails fast with a clear message for the two failures a
judge reproducing the bundle is most likely to hit — no Lakebase project,
or an identity without CAN MANAGE on it.

Usage: LAKEBASE_PROJECT_ID=policy-time-machine python -m ci.review.smoke_branch
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from databricks.sdk import WorkspaceClient  # noqa: E402
from databricks.sdk.errors import NotFound, PermissionDenied  # noqa: E402

from backend.review.lakebase import BranchLifecycle, connect_branch, main_branch_name  # noqa: E402
from ci.genie import config  # noqa: E402


def main() -> int:
    if not os.environ.get("LAKEBASE_PROJECT_ID"):
        print("LAKEBASE_PROJECT_ID is not set (bundle default: policy-time-machine)")
        return 1
    client = WorkspaceClient(profile=config.DATABRICKS_PROFILE)
    lifecycle = BranchLifecycle(client)
    run_id = f"smoke{int(time.time())}"
    started = time.monotonic()
    try:
        branch = lifecycle.create(run_id)
    except NotFound:
        print(f"Lakebase project not found: {main_branch_name()} — deploy the bundle first")
        return 1
    except PermissionDenied:
        print("This identity lacks CAN MANAGE on the Lakebase project — grant it in the project's permissions")
        return 1
    print(f"branch ready in {time.monotonic() - started:.1f}s: {branch.branch_name} host={branch.host}")
    try:
        with connect_branch(client, branch) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                assert cur.fetchone()[0] == 1
                cur.execute("SELECT count(*) FROM review.routed_claim")
                print(f"branch sees {cur.fetchone()[0]} routed claims inherited from main")
    finally:
        lifecycle.delete(branch)
        print(f"branch deleted; total {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Brief contract**

```python
#!/usr/bin/env python3
"""The Brief contract (design spec §11): build a Brief for the demo
policy's latest claim three times and assert the deterministic sections
against the gold tables, the frequency shape against the detected
situation, every sentence against the vocabulary, and — with one injected
Genie failure — that nothing partial reaches main.

Usage: LAKEBASE_PROJECT_ID=policy-time-machine python -m ci.review.run_brief_contract
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from databricks.sdk import WorkspaceClient  # noqa: E402

from backend.genie import GenieResult  # noqa: E402
from backend.review.harness import run_brief  # noqa: E402
from backend.review.lakebase import connect_main  # noqa: E402
from backend.review.questions import detect_situation  # noqa: E402
from backend.review.runner import build_deps  # noqa: E402
from backend.review.schema import ensure_schema  # noqa: E402
from backend.review.store import ReviewStore  # noqa: E402
from backend.review.vocabulary import violations  # noqa: E402
from ci.genie import config  # noqa: E402
from ci.genie.genie_client import run_warehouse_query  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RUNS = 3


def _q(client, sql):
    return run_warehouse_query(client, config.WAREHOUSE_ID, config.CATALOG, config.SCHEMA, sql)


def latest_claim(client, policy_id: str) -> dict:
    rows = _q(client, f"SELECT * FROM claim_event WHERE policy_id = '{policy_id}' ORDER BY report_date DESC LIMIT 1")
    if not rows:
        raise SystemExit(f"demo policy {policy_id} has no claims")
    return rows[0]


def check(brief: dict, client, claim: dict) -> list[str]:
    failures = []
    s = brief["sections"]
    if list(s) != ["sequence", "relevant_changes", "frequency", "similar"]:
        failures.append(f"section order {list(s)}")
    pid, cid = claim["policy_id"], claim["claim_id"]
    expected_seq = _q(client, f"SELECT count(*) AS n FROM policy_timeline_event WHERE policy_id='{pid}' AND event_date <= DATE'{claim['loss_date']}' AND event_date >= date_sub(DATE'{claim['loss_date']}', 365)")[0]["n"]
    if int(expected_seq) != s["sequence"]["row_count"]:
        failures.append(f"sequence rows {s['sequence']['row_count']} != {expected_seq}")
    rel = _q(client, f"SELECT change_event_id, change_timing, days_to_next_claim_loss FROM policy_change_event WHERE policy_id='{pid}' AND next_claim_id='{cid}' AND change_relates_to_claimed_coverage = true")
    if {r["change_event_id"] for r in rel} != {r["change_event_id"] for r in s["relevant_changes"]["rows"]}:
        failures.append("relevant change ids differ from policy_change_event")
    pat = _q(client, f"SELECT pattern_code FROM policy_pattern_match WHERE policy_id='{pid}' AND evidence_claim_id='{cid}'")
    expected_situation = detect_situation(rel, pat).value
    if s["relevant_changes"]["situation"] != expected_situation or s["frequency"]["shape"] != expected_situation:
        failures.append(f"situation/shape mismatch: {s['relevant_changes']['situation']}/{s['frequency']['shape']} vs {expected_situation}")
    if s["frequency"]["genie_status"] != "ok" or s["frequency"]["row_count"] == 0:
        failures.append("frequency section has no Genie rows")
    sim = _q(client, f"SELECT similar_policy_id FROM policy_similarity WHERE policy_id='{pid}' AND rank <= 5 ORDER BY rank")
    if [r["similar_policy_id"] for r in sim] != [r["similar_policy_id"] for r in s["similar"]["rows"]]:
        failures.append("neighbours differ from policy_similarity")
    for name, section in s.items():
        if section.get("sentence") and violations(section["sentence"], pid):
            failures.append(f"{name} sentence violates vocabulary: {section['sentence']!r}")
        if "summary" in section or "recommendation" in section:
            failures.append(f"{name} carries a forbidden field")
    return failures


class FailingGenie:
    def ask(self, question, conversation_id=None):
        return None, GenieResult(status="error", error="injected failure")


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    client = WorkspaceClient(profile=config.DATABRICKS_PROFILE)
    conn = connect_main(client)
    ensure_schema(conn, os.environ.get("APP_SERVICE_PRINCIPAL_ID"))
    store = ReviewStore(conn)
    manifest = run_warehouse_query(client, config.WAREHOUSE_ID, config.CATALOG, config.BRONZE_SCHEMA,
                                   "SELECT demo_policy_id FROM generation_manifest")[0]
    policy_id = manifest["demo_policy_id"] or config.DEMO_POLICY_ID
    claim = latest_claim(client, policy_id)
    contract_claim_id = claim["claim_id"]
    store.upsert_routed_claim({"claim_id": contract_claim_id, "policy_id": policy_id, "coverage_line": claim["coverage_line"],
                               "loss_date": claim["loss_date"], "report_date": claim["report_date"],
                               "settled_amount": float(claim["settled_amount"]), "severity_band": claim["severity_band"]},
                              routed_by="on_demand", routing_rule=None)
    deps = build_deps(client, store, demo_hold_seconds=0)

    records, passes = [], 0
    for i in range(1, RUNS + 1):
        started = time.monotonic()
        outcome = run_brief(contract_claim_id, deps)
        failures = [outcome.failure] if outcome.status != "completed" else check(outcome.brief, client, claim)
        passed = not failures
        passes += passed
        print(f"run {i}/{RUNS}: {'PASS' if passed else 'FAIL'} ({time.monotonic() - started:.0f}s) {failures or ''}", flush=True)
        records.append({"run": i, "passed": passed, "failures": failures, "run_id": outcome.run_id, "trace_id": outcome.trace_id,
                        "question": (outcome.brief or {}).get("sections", {}).get("frequency", {}).get("question")})
        # Reset so the next run rebuilds rather than being skipped as brief_ready.
        conn.execute("DELETE FROM review.brief WHERE claim_id = %s", (contract_claim_id,))
        conn.execute("UPDATE review.routed_claim SET run_state='queued', active_run_id=NULL WHERE claim_id = %s", (contract_claim_id,))

    # Forced failure: nothing partial on main, claim back to queued.
    failing = build_deps(client, store, demo_hold_seconds=0)
    failing.genie = FailingGenie()
    outcome = run_brief(contract_claim_id, failing)
    partial = store.get_claim(contract_claim_id)
    forced_ok = outcome.status == "failed" and partial["brief"] is None and partial["run_state"] == "queued"
    print(f"forced failure: {'PASS' if forced_ok else 'FAIL'} ({outcome.failure})", flush=True)

    summary = {"timestamp": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), "policy_id": policy_id,
               "claim_id": contract_claim_id, "passes": passes, "of": RUNS, "forced_failure_ok": forced_ok, "runs": records}
    (RESULTS_DIR / f"brief_contract_{summary['timestamp']}.json").write_text(json.dumps(summary, indent=2, default=str))
    return 0 if passes == RUNS and forced_ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run both against the workspace**

Run:
```bash
LAKEBASE_PROJECT_ID=policy-time-machine python -m ci.review.smoke_branch
LAKEBASE_PROJECT_ID=policy-time-machine REVIEW_MODEL_ENDPOINT=<pinned endpoint> python -m ci.review.run_brief_contract
```
Expected: smoke prints the branch host and deletes it within ~60 s; the contract prints three PASS lines and `forced failure: PASS`. If a sentence fails vocabulary in 1 or 2 of 3 runs, that is instruction ambiguity: tighten `prompts.SYSTEM`, never the check. If the frequency section is `empty` or `clarification` 3/3 for a shape, the canonical question for that shape needs a Genie instruction — treat it like a Genie contract failure (`docs/genie-curation.md`).

- [ ] **Step 4: Add `ci/review/results/` to `.gitignore`** (alongside the Genie results) and commit

```bash
echo "ci/review/results/" >> .gitignore
git add ci/review .gitignore
git commit -m "CI: Working Branch smoke test and the Brief contract (3/3 plus forced failure)"
```

---

### Task 16: Documentation — meetup demo spec, specs index, diagram, README notes

**Files:**
- Create: `docs/specs/13-meetup-demo-specification.md`
- Modify: `docs/specs/README.md`, `docs/diagrams/01-high-level.mmd` (and re-render via `ci/render-diagrams.sh`), `docs/specs/08-test-strategy.md` (one new layer paragraph), project `README.md` (create if absent: reproducibility notes)

- [ ] **Step 1: Write the meetup spec**

```markdown
# Meetup Demo Specification

Live, 15–20 minutes, technical audience. Product first, then four platform chapters in data-flow order, two minutes for questions. The contest script (spec 07) is untouched; this is its own document.

Rules carried over from spec 07: relative language only; contract phrasings only (spec 05 for Genie, `ci/review/run_brief_contract.py` for the Brief); the evidence panel opens at least twice; never say fraud.

Pre-flight (the day before): regenerate; run `ci/genie/run_contracts.py` (15/15 at 3/3), `ci/review/smoke_branch.py`, `ci/review/run_brief_contract.py` (3/3); set `REVIEW_DEMO_HOLD_SECONDS=20` on the app; ensure one Brief is already built for the demo policy's latest claim and one Routed Claim has none; record the four fallback clips; open the Lakebase branches page, the Workflow run page, the Genie space and a SQL editor in separate tabs; run the governance preflight from spec 07 rule 7.

## Chapter 0 — The product (3 min)
Beats 3, 4, 5 and 6 of spec 07, verbatim: cohort → timeline → multi-turn → similarity. End on the open timeline.

## Chapter 1 — The lakehouse (4 min)
Cut to the Workflow run page: generate → validate → load → refresh → route_claims → build_briefs. Open the pipeline graph; open one expectation (E18, the vocabulary rule) and say why a rule that lives only in a document drifts. Open `ptm_gold.policy_change_event` in Catalog Explorer and point at `next_claim_id`, `days_to_next_claim_loss`, `change_timing`: relationships are columns; thresholds stay with Genie.

## Chapter 2 — Genie (4 min)
Open the Genie space: the six tables, the instructions, the two trusted SQL functions. Re-ask the cohort question and open the evidence panel. Show `ci/genie/results/` for the last contract run: fifteen contracts, three of three, asserted against planted ground truth, never against SQL text.

## Chapter 3 — The agent and Lakebase (5 min)
Back in the app, click **Prepare a Brief** on the timeline's claim card. The Review view opens with the Run panel: "Working Branch created: run-…". Cut to the Lakebase branches page — the branch is there with its parent and creation time. Back to the app as sections complete; say the line: *the harness decides what happens, the model decides what to ask.* Point at the question the model chose and the shape it had to fit. When the panel says "Working Branch deleted by the harness", cut back to the branches page: gone. Open the Brief: four sections, each with its sentence, rows and SQL; one withheld sentence if the run produced one — say why that is a feature. Record a Disposition. Open the MLflow trace from the run record. Then open the queue and point at the nightly rule-routed claims with Briefs already built.

## Chapter 4 — Governance (2 min)
Spec 07 beat 9 as written (revoke USE SCHEMA), plus: switch to the Review view — the Brief panel is quiet too. Grant back. Line: Unity Catalog governs the source; the Brief mirrors its answer.

## Close (1 min) and questions (2 min)
Name the services: Unity Catalog, Lakeflow declarative pipeline, Workflows, Genie, Databricks Apps, Lakebase with branching, Foundation Model API, MLflow tracing, Asset Bundles.

## Fallbacks
Each chapter has a 30-second clip. Chapter 3's fallback is the pre-built Brief plus the clip of a branch appearing and disappearing. If the Run is slow, keep talking over the Run panel; the demo hold gives twenty seconds to catch the branch on screen.
```

- [ ] **Step 2: Specs index and test strategy**

In `docs/specs/README.md` add under **Verify and ship**: `13. [`13-meetup-demo-specification.md`](./13-meetup-demo-specification.md) — the live meetup arc; product first, then four platform chapters`, and update the ADR count sentence in **Also** to "nineteen decisions". In `docs/specs/08-test-strategy.md` append a short section "Layer five — the Claim Review Brief agent" listing: harness tests with fakes (pytest), Review view tests (vitest), the branch smoke test, and the Brief contract at 3/3 plus a forced failure, run alongside the Genie contracts before any recording.

- [ ] **Step 3: Diagram**

In `docs/diagrams/01-high-level.mmd` add inside the bundle subgraph:

```
        lakebase[("Lakebase — review record<br/>+ disposable Working Branch per Run")]
        agent["Claim Review Brief agent<br/>harness owns the plan; model owns the question"]
```

and edges `wf --> agent`, `agent --> lakebase`, `agent --> genie`, `lakebase --> app`. Re-render: `ci/render-diagrams.sh` (or let the GitHub workflow do it). Update the embedded copy in `docs/specs/09-product-charter.md` verbatim.

- [ ] **Step 4: README reproducibility notes**

Create or extend the project `README.md` with a "Review agent" section: Free Edition allows one Lakebase project per account, so a judge with an existing project must delete it first; bundle destroy soft-deletes the project for seven days and the id cannot be reused in that window, so never destroy near demo day; `REVIEW_MODEL_ENDPOINT` must name an enabled pay-per-token endpoint; the two CI scripts and how to run them.

- [ ] **Step 5: Commit**

```bash
git add docs README.md
git commit -m "Docs: meetup demo spec, test layer five, architecture diagram with the agent and Lakebase"
```

---

## Self-review

**Spec coverage.** §4 routing → Task 9 and 12; §5 Brief shape → Task 8 (`execute()` envelope, sections); §6.1 plan and §6.2 budgets → Task 8 (`MAX_*`, `run_timeout_seconds`); §6.3 shapes → Task 3 and the `frequency()` retry/canonical path; §6.4 prompts → Task 8 `prompts.py`; §6.5 scratch SQL → Task 7 `ScratchSql`; §6.6 vocabulary → Task 2 and the pipeline-equality test; §7.1 bundle → Task 12; §7.2 schema and grants → Task 6; §7.3 lifecycle → Task 5; §7.4 connections → Task 5; §8 model and tracing → Tasks 4, 8 (`MlflowTracer`), 12 (experiment resource); §9.1 API → Task 11; §9.2 view → Tasks 13, 14; §10 Workflow → Task 12; §11 testing → every task's tests plus Task 15; §12 meetup → Task 16; investigation map (§9.1 last paragraph) → Task 10.

**Known verification points for the executor** (not placeholders, but facts to confirm on first contact with the workspace): `mlflow.get_last_active_trace_id()` name in the installed mlflow (fallback: `mlflow.get_last_active_trace().info.trace_id`); whether `postgres_databases` in the bundle needs an explicit endpoint dependency; whether job-task argv parameters arrive as `--NAME value` pairs on serverless (Task 12 step 3 item 4 reads them that way and falls back to defaults); the exact `x-forwarded-email` header name on Databricks Apps (Task 11 reads two candidates).

**Type consistency.** `RunDeps` fields match between Tasks 8, 9, 11, 15; `ReviewStore`/`InMemoryReviewStore` method names match their uses in Tasks 8–11 and 15; `WorkingBranch` fields match Tasks 5, 8; `GenieResult` fields (`status`, `columns` as `[{"name"}]`, `rows`, `generated_sql`, `description`, `error`) match `backend/genie.py`.
