"""The declared primary/foreign keys on the six gold tables (docs/genie-curation.md §3).

Keys are informational (NOT ENFORCED) Unity Catalog constraints, declared in
the pipeline's table definitions so Genie can read the join graph from UC
metadata rather than from text instructions. The declarations and the DDL
renderer live in ``transformations.py`` beside ``SCHEMAS`` so keys and columns
cannot drift apart.
"""

import re

import pytest

import transformations as T


ALL_TABLES = tuple(T.SCHEMAS)


def test_every_gold_table_declares_keys():
    assert set(T.GOLD_KEYS) == set(T.SCHEMAS)


def test_primary_key_columns_exist_in_their_schema():
    for table, keys in T.GOLD_KEYS.items():
        columns = {name for name, _ in T.SCHEMAS[table]}
        assert keys.primary_key, f"{table} has no primary key"
        for col in keys.primary_key:
            assert col in columns, f"{table} PK column {col} not in schema"


def test_foreign_keys_reference_the_parent_primary_key():
    for table, keys in T.GOLD_KEYS.items():
        for fk in keys.foreign_keys:
            assert fk.references_table in T.GOLD_KEYS, (
                f"{table} FK {fk.name} references unknown table {fk.references_table}")
            parent_pk = T.GOLD_KEYS[fk.references_table].primary_key
            assert fk.references_columns == parent_pk, (
                f"{table} FK {fk.name} must reference {fk.references_table}'s "
                f"declared PK {parent_pk}, got {fk.references_columns}")
            columns = {name for name, _ in T.SCHEMAS[table]}
            for col in fk.columns:
                assert col in columns, f"{table} FK column {col} not in schema"


def test_every_child_table_references_policy_profile():
    for table in ALL_TABLES:
        if table == "policy_profile":
            continue
        refs = {fk.references_table for fk in T.GOLD_KEYS[table].foreign_keys}
        assert "policy_profile" in refs, f"{table} should reference policy_profile"


@pytest.mark.parametrize("table", ALL_TABLES)
def test_ddl_lists_every_column_in_declared_order(table):
    ddl = T.constrained_schema_ddl(table, "workspace", "ptm_gold")
    positions = []
    for name, _ in T.SCHEMAS[table]:
        m = re.search(rf"\b{name}\b", ddl)
        assert m, f"{table} DDL is missing column {name}"
        positions.append(m.start())
    assert positions == sorted(positions), f"{table} DDL columns out of order"


@pytest.mark.parametrize("table", ALL_TABLES)
def test_ddl_marks_primary_key_columns_not_null(table):
    ddl = T.constrained_schema_ddl(table, "workspace", "ptm_gold")
    for col in T.GOLD_KEYS[table].primary_key:
        kind = dict(T.SCHEMAS[table])[col]
        ddl_type = T.DDL_TYPES[kind]
        assert f"{col} {ddl_type} NOT NULL" in ddl, (
            f"{table} PK column {col} must be NOT NULL in DDL")


def test_ddl_declares_pk_and_fully_qualified_fk_constraints():
    ddl = T.constrained_schema_ddl("policy_change_event", "workspace", "ptm_gold")
    assert "CONSTRAINT pk_policy_change_event PRIMARY KEY (change_event_id)" in ddl
    assert re.search(
        r"CONSTRAINT fk_policy_change_event_policy_id FOREIGN KEY \(policy_id\)\s+"
        r"REFERENCES workspace\.ptm_gold\.policy_profile \(policy_id\)", ddl)
    assert re.search(
        r"CONSTRAINT fk_policy_change_event_next_claim_id FOREIGN KEY \(next_claim_id\)\s+"
        r"REFERENCES workspace\.ptm_gold\.claim_event \(claim_id\)", ddl)


def test_composite_primary_keys_on_match_and_similarity():
    assert T.GOLD_KEYS["policy_pattern_match"].primary_key == ("policy_id", "pattern_code")
    assert T.GOLD_KEYS["policy_similarity"].primary_key == ("policy_id", "rank")
    ddl = T.constrained_schema_ddl("policy_similarity", "workspace", "ptm_gold")
    assert "CONSTRAINT pk_policy_similarity PRIMARY KEY (policy_id, rank)" in ddl


def test_ddl_types_cover_every_declared_kind():
    kinds = {kind for schema in T.SCHEMAS.values() for _, kind in schema}
    assert kinds <= set(T.DDL_TYPES)


def test_pipeline_orders_fk_children_after_their_parents():
    """A FOREIGN KEY declaration fails at flow time unless the referenced
    table's PRIMARY KEY already exists (UC_REFERENTIAL_CONSTRAINT_DOES_NOT_EXIST,
    observed on update 0e5bf0). The gold flows share no data dependencies —
    they build driver-side — so each child flow must carry an explicit
    dlt.read() of every table its FKs reference to force creation order."""
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent / "dlt_pipeline.py").read_text()
    for table, keys in T.GOLD_KEYS.items():
        parents = {fk.references_table for fk in keys.foreign_keys}
        if not parents:
            continue
        start = source.index(f'    name="{table}",')
        body = source[start:start + 1200]
        for parent in parents:
            assert f'dlt.read("{parent}")' in body, (
                f"{table} declares an FK to {parent} but its flow does not "
                f'dlt.read("{parent}") to order creation after the parent')
