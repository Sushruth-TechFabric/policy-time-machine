"""Unity Catalog comments — spec 02 §9 and ADR-0013.

Comments are semantic-layer content, not documentation: Genie reads them as
context. They are authored in one place so that comments and the Genie
instruction set can never disagree.
"""

from __future__ import annotations

import re

import pytest

import transformations as T
import uc_comments as UC


# --- The single authored source -------------------------------------------

def test_every_column_of_every_curated_table_has_a_comment():
    for table, schema in T.SCHEMAS.items():
        documented = set(UC.COMMENTS[table]) - {None}
        assert documented == {name for name, _ in schema}, table


def test_every_table_has_a_table_comment():
    for table in T.SCHEMAS:
        assert UC.COMMENTS[table][None]


def test_comments_are_authored_prose_not_column_names():
    """Genie reads these as context, so each must be a sentence. A comment may
    open with a lowercase column name it is describing, but not merely restate
    the column name it is attached to."""
    known_columns = {name for schema in T.SCHEMAS.values() for name, _ in schema}
    for table, columns in UC.COMMENTS.items():
        for column, text in columns.items():
            assert len(text.split()) >= 3, f"{table}.{column}"
            opener = text.split()[0].rstrip(".,:")
            assert text[0].isupper() or opener in known_columns, \
                f"{table}.{column}: {text!r}"
            assert opener != column, f"{table}.{column} restates its own name"
            assert text.rstrip().endswith((".", ")")), f"{table}.{column}: {text!r}"


# --- The five definitions spec 02 §9 requires verbatim ---------------------

@pytest.mark.parametrize("key", sorted(UC.VERBATIM, key=lambda k: (k[0], k[1] or "")))
def test_counterintuitive_definitions_appear_verbatim(key):
    table, column = key
    assert UC.VERBATIM[key] in UC.COMMENTS[table][column]


def test_the_five_verbatim_definitions_are_the_ones_the_spec_names():
    assert set(UC.VERBATIM) == {
        ("policy_change_event", "next_claim_id"),
        ("policy_change_event", "days_to_next_claim_loss"),
        ("policy_change_event", "change_timing"),
        ("claim_event", "severity_band"),
        ("policy_timeline_event", None),
    }


def test_next_claim_id_comment_says_report_not_loss():
    text = UC.COMMENTS["policy_change_event"]["next_claim_id"]
    assert "reported at or after this change" in text
    assert "Not the next claim by loss date" in text
    assert "Many changes may share one claim" in text


def test_change_timing_comment_tells_genie_not_to_read_the_sign():
    """The product's single most important instruction, mirrored in the comment
    Genie actually reads (ADR-0004)."""
    assert "Use this rather than interpreting the sign" in UC.COMMENTS[
        "policy_change_event"]["change_timing"]
    assert "Filter with `change_timing`, not with the sign" in UC.COMMENTS[
        "policy_change_event"]["days_to_next_claim_loss"]


def test_timeline_table_comment_forbids_aggregation():
    assert "Do not aggregate" in UC.COMMENTS["policy_timeline_event"][None]


def test_high_severity_is_defined_in_the_comment_not_left_to_genie():
    assert "High-severity means `severe` or `catastrophic`" in UC.COMMENTS[
        "claim_event"]["severity_band"]


# --- E18 applies to comments too ------------------------------------------

def test_no_comment_uses_banned_vocabulary():
    for table, columns in UC.COMMENTS.items():
        for column, text in columns.items():
            assert T.vocabulary_violations(text) == [], f"{table}.{column}: {text!r}"


def test_pattern_comments_frame_a_match_as_an_investigation_candidate():
    text = UC.COMMENTS["policy_pattern_match"][None]
    assert "investigation candidate" in text
    assert "never a score" in text or "never a judgment" in text


# --- Rendering -------------------------------------------------------------

def test_render_emits_one_statement_per_table_and_column():
    statements = list(UC.render_statements())
    expected = len(T.SCHEMAS) + sum(len(s) for s in T.SCHEMAS.values())
    assert len(statements) == expected


def test_rendered_statements_are_terminated_and_qualified():
    for statement in UC.render_statements("workspace", "policy_time_machine"):
        assert statement.endswith(";")
        assert "`workspace`.`policy_time_machine`." in statement
        assert statement.startswith(("COMMENT ON TABLE", "COMMENT ON COLUMN"))


def test_catalog_and_schema_are_parameterised():
    statements = list(UC.render_statements("main", "ptm_dev"))
    assert all("`main`.`ptm_dev`." in s for s in statements)


def test_apostrophes_are_escaped_for_sql():
    """The timeline table comment contains an apostrophe in "one policy's
    history"; unescaped, it would truncate the DDL statement."""
    script = UC.render_script()
    assert "one policy''s history" in script
    assert re.search(r"(?<!')'(?!')", script)  # ordinary delimiters still present
    for statement in UC.render_statements():
        body = statement.split(" IS ", 1)[-1] if " IS " in statement else \
            statement.split(" COMMENT ", 1)[-1]
        assert body.startswith("'") and body.endswith("';")
        assert body[1:-2].count("'") % 2 == 0


def test_reserved_words_are_backtick_quoted():
    statements = [s for s in UC.render_statements() if "policy_similarity" in s]
    assert any(".`rank` IS " in s for s in statements)


def test_script_carries_a_generated_from_header():
    script = UC.render_script()
    assert "do not edit by hand" in script
    assert "uc_comments.py" in script


def test_main_prints_the_script(capsys):
    assert UC.main([]) == 0
    out = capsys.readouterr().out
    assert "COMMENT ON TABLE" in out
    assert out.count(";") >= len(T.SCHEMAS)


def test_the_authored_source_is_reusable_by_the_genie_instruction_build():
    """P4 renders instructions from this same dict rather than restating it, so
    comments and instructions cannot disagree (ADR-0013)."""
    assert isinstance(UC.COMMENTS, dict)
    assert set(UC.COMMENTS) == set(T.SCHEMAS)
    assert UC.COMMENTS["policy_similarity"][None].count("similar") >= 2
