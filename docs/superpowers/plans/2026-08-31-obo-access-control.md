# On-Behalf-Of-User Access Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every data-touching request (Genie, evidence re-runs, timeline/similar/patterns) executes as the viewing user via the Databricks Apps forwarded token, so a viewer without Unity Catalog grants on `ptm_gold` sees a quiet "no access" state instead of data.

**Architecture:** Databricks Apps injects `x-forwarded-access-token` when the app declares `user_api_scopes`. `deps.get_client` becomes a per-request dependency that builds a `WorkspaceClient` from that token, falling back to the cached app-identity client (local dev, tests). Permission-denied errors from Genie or the warehouse map to a new `no_access` result status; the frontend renders it as a quiet governance state, never an error. Spec: `docs/superpowers/specs/2026-08-31-obo-access-control-design.md`.

**Tech Stack:** FastAPI, databricks-sdk (0.40-compatible patterns), React + Vite, pytest, vitest.

## Global Constraints

- Never use the words fraud/suspicious/red flag/anomaly in any user-facing copy (CONTEXT.md approved vocabulary).
- Competition-simple: no new dependencies, no new services, smallest change that enforces for real.
- `genie.py` never raises (module docstring contract) — every new path still collapses to a `GenieResult`.
- The no-access copy is fixed and friendly; raw grant/SQL error text never reaches the UI.
- Demo spec language stays relative ("before recording", never absolute dates) — spec 07 header rule.
- Backend tests: `pytest app/backend/tests -v` from the repo root (conftest fixes `sys.path`). Frontend tests: `cd app/frontend && npm test`.

---

### Task 1: Permission-denied detection (`access.py`)

**Files:**
- Create: `app/backend/access.py`
- Test: `app/backend/tests/test_access.py`

**Interfaces:**
- Produces: `NO_ACCESS_MESSAGE: str` and `is_permission_denied(error: BaseException | str | None) -> bool`, imported by Tasks 2–4.

- [ ] **Step 1: Write the failing tests**

```python
# app/backend/tests/test_access.py
"""Permission-denied detection: platform error types and error-code
markers only — a generic failure must never masquerade as no_access."""

from databricks.sdk.errors import PermissionDenied

from backend.access import NO_ACCESS_MESSAGE, is_permission_denied


def test_sdk_permission_denied_exception_is_detected():
    assert is_permission_denied(PermissionDenied("nope")) is True


def test_error_code_markers_are_detected_in_text():
    assert is_permission_denied("[INSUFFICIENT_PERMISSIONS] Insufficient privileges: ...") is True
    assert is_permission_denied("PERMISSION_DENIED: User does not have SELECT") is True
    assert is_permission_denied(Exception("status 403: PERMISSION_DENIED on table")) is True


def test_ordinary_failures_are_not_no_access():
    assert is_permission_denied("warehouse unreachable") is False
    assert is_permission_denied(Exception("timed out waiting for the warehouse statement")) is False
    assert is_permission_denied(None) is False


def test_message_is_fixed_and_friendly():
    assert "access" in NO_ACCESS_MESSAGE
    assert "PERMISSION_DENIED" not in NO_ACCESS_MESSAGE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/backend/tests/test_access.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.access'`

- [ ] **Step 3: Write the implementation**

```python
# app/backend/access.py
"""Shared permission-denied detection (OBO access control).

With on-behalf-of-user auth, a viewer without Unity Catalog grants
surfaces as permission errors from two directions: Genie message
failures and warehouse statement failures. Both funnel through
`is_permission_denied` so they collapse to one `no_access` state
carrying `NO_ACCESS_MESSAGE` — never the raw grant error text.

Detection matches the platform's error types and error codes, not
loose prose: the SDK's `PermissionDenied`, or the documented
`PERMISSION_DENIED` / `INSUFFICIENT_PERMISSIONS` codes embedded in
error text (statement failures arrive as text via `ServiceError`).
"""

from __future__ import annotations

from databricks.sdk.errors import PermissionDenied

NO_ACCESS_MESSAGE = (
    "You don't have access to the policy data behind this workbench. "
    "Ask your workspace admin for access to the gold tables."
)

_ERROR_CODE_MARKERS = ("PERMISSION_DENIED", "INSUFFICIENT_PERMISSIONS")


def is_permission_denied(error: BaseException | str | None) -> bool:
    if error is None:
        return False
    if isinstance(error, PermissionDenied):
        return True
    text = str(error).upper()
    return any(marker in text for marker in _ERROR_CODE_MARKERS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest app/backend/tests/test_access.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/backend/access.py app/backend/tests/test_access.py
git commit -m "OBO access control: shared permission-denied detection"
```

---

### Task 2: Warehouse raises `WarehousePermissionError`

**Files:**
- Modify: `app/backend/warehouse.py:25-63`
- Test: `app/backend/tests/test_warehouse_no_access.py`

**Interfaces:**
- Consumes: `is_permission_denied`, `NO_ACCESS_MESSAGE` from `backend.access` (Task 1).
- Produces: `class WarehousePermissionError(WarehouseError)` — raised by `run_query` on permission-denied; Tasks 3 and 4 catch it. Ordinary failures still raise plain `WarehouseError`, so existing `except WarehouseError` sites keep working (subclass).

- [ ] **Step 1: Write the failing tests**

```python
# app/backend/tests/test_warehouse_no_access.py
"""Permission-denied from the warehouse becomes WarehousePermissionError,
whether it arrives as a raised SDK exception or a FAILED statement status."""

from types import SimpleNamespace

import pytest
from databricks.sdk.errors import PermissionDenied
from databricks.sdk.service.sql import StatementState

from backend.warehouse import WarehouseError, WarehousePermissionError, run_query


def test_sdk_permission_denied_exception_maps(mock_client):
    mock_client.statement_execution.execute_statement.side_effect = PermissionDenied("nope")
    with pytest.raises(WarehousePermissionError):
        run_query(mock_client, "SELECT 1")


def test_failed_statement_with_insufficient_permissions_maps(mock_client):
    mock_client.statement_execution.execute_statement.return_value = SimpleNamespace(
        status=SimpleNamespace(
            state=StatementState.FAILED,
            error=SimpleNamespace(
                error_code="INSUFFICIENT_PERMISSIONS",
                message="Insufficient privileges: user does not have SELECT",
            ),
        ),
        manifest=None,
        result=None,
        statement_id="stmt-1",
    )
    with pytest.raises(WarehousePermissionError):
        run_query(mock_client, "SELECT 1")


def test_ordinary_failure_still_plain_warehouse_error(mock_client):
    mock_client.statement_execution.execute_statement.side_effect = Exception("warehouse unreachable")
    with pytest.raises(WarehouseError) as excinfo:
        run_query(mock_client, "SELECT 1")
    assert not isinstance(excinfo.value, WarehousePermissionError)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/backend/tests/test_warehouse_no_access.py -v`
Expected: FAIL with `ImportError: cannot import name 'WarehousePermissionError'`

- [ ] **Step 3: Implement**

In `app/backend/warehouse.py`, add to the imports:

```python
from .access import NO_ACCESS_MESSAGE, is_permission_denied
```

Add directly below the `WarehouseError` class:

```python
class WarehousePermissionError(WarehouseError):
    """The viewer lacks Unity Catalog access to the curated tables.

    A governance fact, not a fault — callers render a no-access state
    rather than an error (OBO access control design, 2026-08-31).
    """
```

Replace the `except` block of `run_query` (currently lines 54–57):

```python
    except WarehouseError:
        raise
    except Exception as exc:  # noqa: BLE001 - surfaced as a clean error upstream
        if is_permission_denied(exc):
            raise WarehousePermissionError(NO_ACCESS_MESSAGE) from exc
        raise WarehouseError(str(exc)) from exc
```

Replace the failed-status block (currently lines 59–63):

```python
    status = getattr(response, "status", None)
    if status is None or status.state != StatementState.SUCCEEDED:
        error = getattr(status, "error", None) if status else None
        message = getattr(error, "message", None) or f"statement did not succeed: {status}"
        code_and_message = f"{getattr(error, 'error_code', '') or ''} {message}"
        if is_permission_denied(code_and_message):
            raise WarehousePermissionError(NO_ACCESS_MESSAGE)
        raise WarehouseError(message)
```

- [ ] **Step 4: Run the whole backend suite**

Run: `pytest app/backend/tests -v`
Expected: all pass (new tests plus the existing suite — `test_timeline_survives_warehouse_exception_with_a_clean_error` must still pass).

- [ ] **Step 5: Commit**

```bash
git add app/backend/warehouse.py app/backend/tests/test_warehouse_no_access.py
git commit -m "OBO access control: warehouse permission errors get their own type"
```

---

### Task 3: Genie maps permission-denied to `no_access`

**Files:**
- Modify: `app/backend/genie.py:29-183`
- Test: `app/backend/tests/test_genie_no_access.py`

**Interfaces:**
- Consumes: `is_permission_denied`, `NO_ACCESS_MESSAGE` (Task 1); `WarehousePermissionError` (Task 2).
- Produces: `GenieResult.status` gains the value `"no_access"` (alongside `ok | empty | error | clarification`), with `error = NO_ACCESS_MESSAGE`. The frontend (Task 5) keys off this exact status string.

- [ ] **Step 1: Write the failing tests**

```python
# app/backend/tests/test_genie_no_access.py
"""Every Genie path that can carry a permission error collapses to
status "no_access" with the fixed message — never raw grant text."""

from types import SimpleNamespace

from databricks.sdk.errors import PermissionDenied

from backend.access import NO_ACCESS_MESSAGE
from backend.genie import ask_genie


def test_permission_denied_exception_becomes_no_access(mock_client):
    mock_client.genie.start_conversation_and_wait.side_effect = PermissionDenied("nope")
    _, result = ask_genie(mock_client, None, "show changes")
    assert result.status == "no_access"
    assert result.error == NO_ACCESS_MESSAGE


def test_failed_message_with_permission_marker_becomes_no_access(mock_client):
    mock_client.genie.start_conversation_and_wait.return_value = SimpleNamespace(
        status="FAILED",
        error=SimpleNamespace(error="PERMISSION_DENIED: cannot read ptm_gold", message=None),
        attachments=[],
        conversation_id="c-1",
    )
    _, result = ask_genie(mock_client, None, "show changes")
    assert result.status == "no_access"
    assert result.error == NO_ACCESS_MESSAGE


def test_ordinary_genie_failure_stays_error(mock_client):
    mock_client.genie.start_conversation_and_wait.side_effect = Exception("genie is down")
    _, result = ask_genie(mock_client, None, "show changes")
    assert result.status == "error"
    assert "genie is down" in result.error
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/backend/tests/test_genie_no_access.py -v`
Expected: the first two FAIL (`assert 'error' == 'no_access'`), the third passes.

- [ ] **Step 3: Implement**

In `app/backend/genie.py`, add to the imports:

```python
from .access import NO_ACCESS_MESSAGE, is_permission_denied
```

Update the `GenieResult.status` comment to `# "ok" | "empty" | "error" | "clarification" | "no_access"`.

Add a helper below `GenieResult`:

```python
def _no_access_result() -> GenieResult:
    return GenieResult(status="no_access", error=NO_ACCESS_MESSAGE)
```

In `ask_genie`, replace the `except` block (currently lines 79–80):

```python
    except Exception as exc:  # noqa: BLE001 - any Genie exception/timeout -> structured result
        if is_permission_denied(exc):
            return conversation_id, _no_access_result()
        return conversation_id, GenieResult(status="error", error=str(exc))
```

In `_interpret_message`, extend the failure-status branch (currently lines 94–101) — after computing `error_text`, before the `return`:

```python
        if is_permission_denied(error_text):
            return _no_access_result()
        return GenieResult(status="error", error=str(error_text))
```

In the result-fetch `except` block (currently lines 137–143), first line inside:

```python
        if is_permission_denied(exc):
            return _no_access_result()
```

In the warehouse re-run fallback (currently lines 156–170), the bare `except Exception: pass` must not swallow a permission error. Replace the fallback's try/except with:

```python
        try:
            from .warehouse import WarehousePermissionError, run_query

            fetched = run_query(client, generated_sql)
            if fetched and isinstance(fetched[0], dict):
                columns = [{"name": name} for name in fetched[0].keys()]
                rows = [list(r.values()) for r in fetched]
        except WarehousePermissionError:
            return _no_access_result()
        except Exception:  # noqa: BLE001 - genuinely-empty stays "empty"
            pass
```

- [ ] **Step 4: Run the whole backend suite**

Run: `pytest app/backend/tests -v`
Expected: all pass (existing `test_messages.py` untouched by the new branches).

- [ ] **Step 5: Commit**

```bash
git add app/backend/genie.py app/backend/tests/test_genie_no_access.py
git commit -m "OBO access control: Genie permission errors collapse to no_access"
```

---

### Task 4: Per-request viewer client + deterministic endpoints

**Files:**
- Modify: `app/backend/deps.py`
- Modify: `app/backend/main.py:69-100`
- Test: `app/backend/tests/test_deps.py`, extend `app/backend/tests/test_timeline_independence.py`

**Interfaces:**
- Consumes: `WarehousePermissionError` (Task 2).
- Produces: `get_client(request: Request) -> WorkspaceClient` (same dependency name — `conftest.py`'s `app.dependency_overrides[get_client]` keeps working). Timeline no-access payload `{"found": False, "events": [], "no_access": True}`; similar `{"neighbours": [], "no_access": True}`; patterns `{"patterns": [], "no_access": True}` — Task 5 keys off `no_access`.

- [ ] **Step 1: Write the failing tests**

```python
# app/backend/tests/test_deps.py
"""OBO wiring: forwarded token -> viewer-scoped client; no header ->
the cached app-identity client (local dev and the whole test suite)."""

from unittest.mock import MagicMock

from backend import deps


def _request_with_headers(headers: dict[str, str]):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


def test_forwarded_token_builds_viewer_client(monkeypatch):
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return MagicMock(name="viewer-client", config=MagicMock(host="https://x"))

    monkeypatch.setattr(deps, "WorkspaceClient", fake_client)
    deps._app_client.cache_clear()

    deps.get_client(_request_with_headers({"x-forwarded-access-token": "tok-123"}))

    assert captured["token"] == "tok-123"
    assert captured["auth_type"] == "pat"


def test_no_header_returns_cached_app_client(monkeypatch):
    app_client = MagicMock(name="app-client")
    monkeypatch.setattr(deps, "WorkspaceClient", lambda **kwargs: app_client)
    deps._app_client.cache_clear()

    first = deps.get_client(_request_with_headers({}))
    second = deps.get_client(_request_with_headers({}))

    assert first is app_client and second is app_client
```

And append to `app/backend/tests/test_timeline_independence.py`:

```python
def test_timeline_no_access_is_a_state_not_an_error(api, mock_client):
    from databricks.sdk.errors import PermissionDenied

    mock_client.statement_execution.execute_statement.side_effect = PermissionDenied("nope")

    resp = api.get("/api/policies/P-18492/timeline")

    assert resp.status_code == 200
    assert resp.json() == {"found": False, "events": [], "no_access": True}


def test_similar_and_patterns_no_access_payloads(api, mock_client):
    from databricks.sdk.errors import PermissionDenied

    mock_client.statement_execution.execute_statement.side_effect = PermissionDenied("nope")

    assert api.get("/api/policies/P-18492/similar").json() == {"neighbours": [], "no_access": True}
    assert api.get("/api/policies/P-18492/patterns").json() == {"patterns": [], "no_access": True}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/backend/tests/test_deps.py app/backend/tests/test_timeline_independence.py -v`
Expected: `test_deps` FAILs (`AttributeError: module 'backend.deps' has no attribute '_app_client'` / `get_client() takes 0 positional arguments`); the two new endpoint tests FAIL with 502.

- [ ] **Step 3: Implement `deps.py`** (full replacement — the module is 17 lines)

```python
"""FastAPI dependency wiring for the Databricks SDK client.

On-behalf-of-user auth: inside Databricks Apps, the platform forwards
the viewer's downscoped OAuth token as `x-forwarded-access-token`
(declared via the app's `user_api_scopes`). When present, every SDK
call this request makes — Genie, evidence re-runs, deterministic
queries — executes as the viewer, so Unity Catalog grants are the
single enforcement point. Without the header (local dev, tests), the
cached app-identity client is used, and tests override `get_client`
via `app.dependency_overrides` exactly as before.
"""

from functools import lru_cache

from databricks.sdk import WorkspaceClient
from fastapi import Request


@lru_cache(maxsize=1)
def _app_client() -> WorkspaceClient:
    return WorkspaceClient()


def get_client(request: Request) -> WorkspaceClient:
    token = request.headers.get("x-forwarded-access-token")
    if not token:
        return _app_client()
    return WorkspaceClient(host=_app_client().config.host, token=token, auth_type="pat")
```

- [ ] **Step 4: Implement the endpoint changes in `main.py`**

Add `WarehousePermissionError` to the warehouse import:

```python
from .warehouse import WarehouseError, WarehousePermissionError
```

Replace the three deterministic endpoints and `_run_deterministic`:

```python
@app.get("/api/policies/{policy_id}/timeline")
def policy_timeline(policy_id: str, client: WorkspaceClient = Depends(get_client)) -> dict:
    try:
        events = _run_deterministic(get_timeline, client, policy_id)
    except WarehousePermissionError:
        return {"found": False, "events": [], "no_access": True}
    return {"found": len(events) > 0, "events": events}


@app.get("/api/policies/{policy_id}/similar")
def policy_similar(policy_id: str, client: WorkspaceClient = Depends(get_client)) -> dict:
    try:
        neighbours = _run_deterministic(get_similar, client, policy_id)
    except WarehousePermissionError:
        return {"neighbours": [], "no_access": True}
    return {"neighbours": neighbours}


@app.get("/api/policies/{policy_id}/patterns")
def policy_patterns(policy_id: str, client: WorkspaceClient = Depends(get_client)) -> dict:
    try:
        patterns = _run_deterministic(get_patterns, client, policy_id)
    except WarehousePermissionError:
        return {"patterns": [], "no_access": True}
    return {"patterns": patterns}
```

```python
def _run_deterministic(fn, client: WorkspaceClient, policy_id: str) -> list[dict[str, Any]]:
    """Run a deterministic warehouse read. No access propagates as its
    own state for the endpoint to shape; any other failure becomes a
    clean HTTP error instead of a crash (VERIFY: timeline may 502
    locally without tables — that's fine, it must not take the process
    down).
    """
    try:
        return fn(client, policy_id)
    except WarehousePermissionError:
        raise
    except WarehouseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

- [ ] **Step 5: Run the whole backend suite**

Run: `pytest app/backend/tests -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/backend/deps.py app/backend/main.py app/backend/tests/test_deps.py app/backend/tests/test_timeline_independence.py
git commit -m "OBO access control: viewer-token client per request; no_access endpoint payloads"
```

---

### Task 5: Frontend no-access states

**Files:**
- Modify: `app/frontend/src/components/ResultPanel.jsx:148` (insert before the `error` branch)
- Modify: `app/frontend/src/components/ResultPanel.css` (one selector)
- Modify: `app/frontend/src/hooks/useInvestigation.js:74-77`
- Modify: `app/frontend/src/components/Timeline.jsx:115-126`
- Test: `app/frontend/src/components/ResultPanel.test.jsx`

**Interfaces:**
- Consumes: `genie.status === 'no_access'` (Task 3); `no_access: true` on timeline payloads (Task 4).
- Produces: nothing downstream — leaf task.

- [ ] **Step 1: Write the failing test**

```jsx
// app/frontend/src/components/ResultPanel.test.jsx
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import ResultPanel from './ResultPanel.jsx';

describe('ResultPanel no_access state', () => {
  it('renders the quiet governance copy, not an error', () => {
    const node = {
      question: 'Show policies where coverage increased',
      genie: { status: 'no_access', columns: [], rows: [], error: 'You don’t have access…' },
    };
    render(<ResultPanel node={node} loading={false} onPolicyClick={() => {}} />);

    expect(screen.getByText(/don't have access to this data/i)).toBeInTheDocument();
    expect(screen.getByText(/workspace admin/i)).toBeInTheDocument();
    expect(screen.queryByText(/could not answer/i)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd app/frontend && npx vitest run src/components/ResultPanel.test.jsx`
Expected: FAIL — "don't have access" not found (the `error`-status branch does not render, so the panel falls through to the empty state).

- [ ] **Step 3: Implement**

In `ResultPanel.jsx`, insert **above** the `genie.status === 'error'` branch:

```jsx
  if (genie.status === 'no_access') {
    return (
      <div className="result-panel">
        <div className="answer-card">
          <QuestionHeader question={question} />
          <div className="result-message result-message--no-access">
            <p className="result-message-title">You don't have access to this data.</p>
            <p>The policy tables behind this workbench are governed by Unity Catalog, and your account doesn't currently hold access to them.</p>
            <p className="result-message-hint">Ask your workspace admin for access to the gold tables.</p>
          </div>
        </div>
      </div>
    );
  }
```

In `ResultPanel.css`, duplicate the existing `.result-message--clarification` rule block as `.result-message--no-access` with identical property values (quiet, non-error styling) — copy the block verbatim and change only the selector.

In `useInvestigation.js`, replace the snapshot shaping (lines 74–77):

```js
      const timeline = await getTimeline(policyId);
      const result = timeline.no_access
        ? { found: false, events: [], patterns: [], noAccess: true }
        : !timeline.found
          ? { found: false, events: [], patterns: [] }
          : { found: true, events: timeline.events, patterns: (await getPatterns(policyId)).patterns ?? [] };
```

In `Timeline.jsx`, insert a `noAccess` branch above the not-found branch, and exclude it from not-found:

```jsx
      {data && data.noAccess && (
        <div className="timeline-not-found">
          You don't have access to this policy's history.
          <div className="timeline-not-found-sub">The gold tables are governed by Unity Catalog — ask your workspace admin for access.</div>
        </div>
      )}

      {data && !data.noAccess && data.found === false && (
```

(The `data.found === false` branch keeps its existing body; only its condition gains `!data.noAccess`.)

- [ ] **Step 4: Run the frontend suite**

Run: `cd app/frontend && npm test`
Expected: all pass, including the existing `App.test.jsx` smoke tests.

- [ ] **Step 5: Build the bundle to catch JSX slips**

Run: `cd app/frontend && npm run build`
Expected: clean build.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/components/ResultPanel.jsx app/frontend/src/components/ResultPanel.css app/frontend/src/components/ResultPanel.test.jsx app/frontend/src/hooks/useInvestigation.js app/frontend/src/components/Timeline.jsx
git commit -m "OBO access control: quiet no-access states for answers and timelines"
```

---

### Task 6: Scopes, deployment verification, demo beat

**Files:**
- Modify: `databricks.yml` (apps resource)
- Modify: `docs/specs/07-demo-specification.md`

**Interfaces:**
- Consumes: everything above deployed together.
- Produces: the recorded-demo runbook; no code consumers.

- [ ] **Step 1: Declare the scopes in the bundle**

In `databricks.yml`, add to the `policy_time_machine_app` resource (sibling of `source_code_path`):

```yaml
      user_api_scopes:
        - dashboards.genie
        - sql
```

- [ ] **Step 2: Validate and deploy**

Run: `databricks bundle validate` then `databricks bundle deploy`
Expected: success. If the API rejects a scope name, the error lists the allowed values — the Genie scope appears as either `dashboards.genie` or `genie` depending on platform version; use whichever the error names, and correct the spec file to match. The requirement is fixed: the Genie conversation API and SQL statement execution must run as the viewer.

- [ ] **Step 3: Verify OBO end-to-end (granted user)**

Open the deployed app in the browser, ask any contract question (e.g. QC-03 phrasing), and confirm results still return. In the app's **Authorization** tab in the workspace UI, confirm the two user API scopes are listed. First visit will show a consent prompt — accept it; note this for the recording (consent must be done *before* recording, or it appears on camera).

- [ ] **Step 4: Preflight the revoke demo (single account)**

Run in a SQL editor, in order, verifying each step:

```sql
-- Who owns what. The demo user must NOT end up the effective owner of the data path.
DESCRIBE SCHEMA EXTENDED workspace.ptm_gold;
DESCRIBE CATALOG EXTENDED workspace;

-- 1. Transfer schema ownership to the app's service principal
--    (find its application id under the app's details page):
ALTER SCHEMA workspace.ptm_gold OWNER TO `<app-service-principal-application-id>`;

-- 2. Give yourself an explicit, revocable grant:
GRANT USE SCHEMA, SELECT ON SCHEMA workspace.ptm_gold TO `sushruth.aeluguri@techfabric.com`;

-- 3. Rehearse the revoke:
REVOKE SELECT ON SCHEMA workspace.ptm_gold FROM `sushruth.aeluguri@techfabric.com`;
-- Verify it bites (must FAIL with INSUFFICIENT_PERMISSIONS):
SELECT * FROM workspace.ptm_gold.policy_summary LIMIT 1;
-- 4. Refresh the app: every panel must show the no-access state.
-- 5. Restore:
GRANT SELECT ON SCHEMA workspace.ptm_gold TO `sushruth.aeluguri@techfabric.com`;
```

If step 3's verification query still returns rows, you hold access through another path — most likely ownership of the `workspace` catalog (a catalog owner cannot be locked out by a schema-level revoke). In that case transfer the catalog's ownership to the app service principal for the recording window and back afterwards; if the platform refuses catalog ownership transfer, record the beat using a Genie question only after also revoking at the table level, and note which path worked in the demo spec.

(Use the actual gold table name from the Genie space if `policy_summary` is not one of the six — any of the six works.)

- [ ] **Step 5: Add the demo beat to spec 07**

Insert between section 8 ("Beat seven — parallel investigations") and section 9 ("Close"), renumbering the later sections (9 Close → becomes the beat after this one; update the two section numbers below it):

```markdown
## 9. Beat eight — governance (25s)

Before recording: ownership of the gold schema sits with the app's service principal, the demo account holds an explicit `GRANT SELECT`, and the one-time OBO consent prompt has already been accepted (rehearsal rule 7).

In a SQL editor tab, run the prepared `REVOKE SELECT` on the gold schema. Switch back to the app and refresh. Ask one question; open the timeline.

> Same screen, same questions — no data. The app asks Genie and the warehouse **as you**, and Unity Catalog just said no. Access isn't an app feature that can drift out of sync with governance; it *is* governance. Revoke a grant and every path — answers, timelines, evidence — goes quiet together.

Run the prepared `GRANT SELECT` back, refresh, ask the same question — results return. Keep the SQL editor visible for both statements; the enforcement being outside the app is the point of the beat.
```

And append to the rehearsal rules:

```markdown
7. **The governance beat is pre-flighted.** Ownership transfer, the explicit grant, and the OBO consent prompt all happen before recording; the revoke/grant statements sit ready in a SQL editor tab. Verify the revoke actually bites (a direct `SELECT` must fail) before the camera rolls.
```

- [ ] **Step 6: Update the close beat's platform line**

In spec 07's Close section, extend the Databricks-native sentence to name the new capability — replace "served by a Databricks App," with "served by a Databricks App that acts on behalf of the signed-in user so Unity Catalog governs every query,".

- [ ] **Step 7: Commit**

```bash
git add databricks.yml docs/specs/07-demo-specification.md
git commit -m "OBO access control: user API scopes in the bundle; governance beat in the demo spec"
```

---

## Self-review notes

- Spec coverage: scopes (Task 6), per-request client (Task 4), `no_access` mapping for Genie exception/failure-status/result-fetch/re-run paths (Task 3), warehouse both failure shapes (Task 2), deterministic endpoints (Task 4), frontend both surfaces (Task 5), demo beat + runbook incl. ownership caveat (Task 6), tests per spec's Testing section (Tasks 1–5). Data curation: spec says none — no task, by design.
- `conftest.py` needs no change: `get_client` keeps its name and stays overridable; the new `Request` parameter only affects the real dependency path.
- Status-string consistency: `"no_access"` (backend JSON) vs `noAccess` (frontend camelCase after shaping) — deliberate, matches the existing `timeline_policy_id` → `timelinePolicyId` convention in `useInvestigation.js`.
