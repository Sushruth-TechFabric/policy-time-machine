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
    # One row: the anchor the gold tables were generated from (ADR-0006). The
    # routing pass writes it; the app reads it here because it is granted gold
    # only, and the anchor's source is the bronze generation manifest.
    """CREATE TABLE IF NOT EXISTS review.dataset (
         singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
         anchor_date date NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now())""",
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
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(statement)
            except Exception:  # noqa: BLE001 - the app SP granting to itself, or role absent locally
                pass


def ensure_stage_tables(conn) -> None:
    with conn.cursor() as cur:
        for statement in STAGE_DDL:
            cur.execute(statement)
