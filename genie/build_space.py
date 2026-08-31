"""Genie space content — the single authored source for task P4.

Mirrors the pattern in ``pipeline/uc_comments.py``: content is authored once,
here, as Python data; ``instructions.md`` and ``examples.sql`` under this
directory are *rendered* from it for human review and diffing, and
``serialized_space()`` renders the same data into the JSON shape the Genie
REST API expects. Nothing here may disagree with ``docs/specs/03-genie-knowledge.md``
(the content this module loads) or with ``pipeline/uc_comments.py`` (the UC
comments Genie also reads) — the two render from one source per ADR-0013.

Usage
-----
    python build_space.py render          # write instructions.md + examples.sql
    python build_space.py show            # print the serialized_space JSON
    python build_space.py create          # POST a new space, print its id
    python build_space.py update SPACE_ID # PUT (full replace) an existing space

``create`` / ``update`` shell out to the ``databricks`` CLI (profile DEFAULT)
so this script has no SDK/network dependency beyond the CLI already used to
set up the workspace.
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path


def _stable_id(seed: str) -> str:
    """A deterministic lowercase 32-hex id, the shape the Genie export proto
    requires (rejects anything else, e.g. 'ptm-sample-01'). Deterministic
    (uuid5 off a fixed namespace) so re-running `show`/`create`/`update`
    against the same content produces the same ids rather than new ones
    each time."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"policy-time-machine-genie:{seed}").hex

# Reuse the pipeline's own banned/approved vocabulary list (spec 03 §7,
# ADR-0014) so a term added to one list can't silently drift from the other.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from transformations import APPROVED_VOCABULARY, vocabulary_violations  # noqa: E402

CATALOG = "workspace"
SCHEMA = "ptm_gold"
WAREHOUSE_ID = "e39eb96b7df5ab0f"

TITLE = "Policy Time Machine"

# Exactly six curated tables (ADR-0002, 0009, 0010). Never the SCD Type 2
# source tables, never scenario_assignment or generation_manifest — exposing
# a correct and a plausible-wrong path is the failure mode ADR-0002 exists to
# prevent.
TABLES: tuple[str, ...] = (
    "policy_change_event",
    "claim_event",
    "policy_profile",
    "policy_timeline_event",
    "policy_pattern_match",
    "policy_similarity",
)

DESCRIPTION = (
    "An investigation tool for exploring how insurance policies changed over "
    "time and how those changes relate to claims. Ask about policy changes, "
    "claims, policies as a population, one policy's story, historical "
    "patterns, or similar histories, across six curated tables. "
    "The dataset is synthetic. Investigation-worthy patterns are "
    "deliberately seeded at declared, documented effect sizes — the product "
    "demonstrates how historical patterns are surfaced and investigated, "
    "not that policy changes predict claims."
)

# ---------------------------------------------------------------------------
# General instructions — spec 03 §1, §2, §3, §4, §6, §7.
# Each block becomes one text_instructions entry. Order matches the spec.
# ---------------------------------------------------------------------------

INSTRUCTION_BLOCKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Scope",
        (
            "This space has exactly six tables: policy_change_event, "
            "claim_event, policy_profile, policy_timeline_event, "
            "policy_pattern_match, policy_similarity. There is no source "
            "history table and no scenario table in this space — do not "
            "assume one exists or invent a join to one.",
        ),
    ),
    (
        "Routing rules — one line each, tells you which table a question belongs to",
        (
            "What changed, and when, and what followed -> policy_change_event.",
            "Claims: counting, averaging, ranking by amount or severity -> claim_event.",
            "Policies as a population: how many changes, how often, which patterns -> policy_profile.",
            "One policy's story in chronological order -> policy_timeline_event.",
            "Which patterns exist, how common they are, which policies match -> policy_pattern_match.",
            "\"Similar\", \"looks like\", \"histories like\", \"policies like this one\" -> policy_similarity.",
            "Never aggregate policy_timeline_event. It mixes grains; counts and sums over it are wrong. Use it only to list one policy's events.",
            "Never compute similarity from raw columns. Similarity exists only in policy_similarity.",
            "Never derive a pattern definition ad hoc. Patterns exist only in policy_pattern_match and the policy_profile flags.",
        ),
    ),
    (
        "The critical instruction — within N days before a claim is always two filters, never one",
        (
            "\"Within N days before a claim\" is always two filters, never one.",
            "days_to_next_claim_loss is signed. Negative values mean the change happened after the loss, in the window before it was reported. A bare days_to_next_claim_loss <= 30 therefore silently includes those changes and returns a wrong cohort.",
            "Always write both filters together: WHERE change_timing = 'before_loss' AND days_to_next_claim_loss <= 30",
            "A bare threshold filter on days_to_next_claim_loss, without change_timing = 'before_loss', is always wrong.",
        ),
    ),
    (
        "Defined terms — use these definitions, never improvise",
        (
            "high-severity claim means severity_band IN ('severe','catastrophic').",
            "material change means is_material = true.",
            "next claim / subsequent claim means the claim in next_claim_id — next by report date, not by loss date.",
            "recent means within the last 90 days, unless the user gives a window. Compute it at query time from last_material_change_date, never read from a stored day-count.",
            "near the limit means at_or_near_limit = true, i.e. utilisation >= 90%.",
            "rapid change cluster means the rapid_change_cluster pattern; do not recompute it, read pattern_rapid_change_cluster on policy_profile or policy_pattern_match.",
            "similar means a row in policy_similarity; top 20 only.",
        ),
    ),
    (
        "Stated limits — surface these rather than improvising around them",
        (
            "Similarity returns at most 20 neighbours. A request for more returns 20 with the limit stated.",
            "Similarity is directional. A being similar to B does not mean B is similar to A.",
            "similarity_score is not comparable across datasets.",
            "Claim amounts are single settled figures. There is no claim development history.",
            "Only personal auto is in scope.",
        ),
    ),
    (
        "Comparison questions — always return both groups",
        (
            "A question comparing a group against the rest (e.g. recent changers versus everyone else) must return both groups with their sample sizes (n). A single group's rate is never returned alone.",
        ),
    ),
    (
        "Approved vocabulary — governs every answer, every label, every explanation",
        (
            "Use only: " + ", ".join(APPROVED_VOCABULARY) + ".",
            "Never use: fraud, fraudulent, suspicious, scheme, deceptive, guilty, risk score, predicts, causes, leads to, increases the risk of, anomaly, anomalous, red flag.",
            "Never make an assertion about a person or claim intent. A policy matching a pattern is an investigation candidate and nothing more.",
            "The dataset is synthetic. Investigation-worthy patterns are deliberately seeded at declared, documented effect sizes — describe the product as surfacing and letting a user investigate historical patterns, never as predicting or causing claims.",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Example SQL library — spec 03 §5. Each maps to one of the demo's example
# questions and is written as a complete, standalone query (never a
# fragment), matching how chips are authored per ADR-0011.
# ---------------------------------------------------------------------------

EXAMPLE_QUERIES: tuple[tuple[str, str], ...] = (
    (
        "Show policies where coverage increased within 30 days before a claim",
        """SELECT policy_id, change_date, coverage_line, old_value_num, new_value_num,
       days_to_next_claim_loss, next_claim_amount, next_claim_severity
FROM policy_change_event
WHERE change_category = 'coverage'
  AND change_direction = 'increase'
  AND change_timing = 'before_loss'
  AND days_to_next_claim_loss <= 30
ORDER BY days_to_next_claim_loss""",
    ),
    (
        "Show policies where coverage increased within 30 days before a claim, on the line later claimed against",
        """SELECT policy_id, change_date, coverage_line, old_value_num, new_value_num,
       days_to_next_claim_loss, next_claim_amount, next_claim_severity
FROM policy_change_event
WHERE change_category = 'coverage'
  AND change_direction = 'increase'
  AND change_timing = 'before_loss'
  AND days_to_next_claim_loss <= 30
  AND change_relates_to_claimed_coverage = true
ORDER BY days_to_next_claim_loss""",
    ),
    (
        "What changed on a policy in the last year",
        """SELECT event_date, event_type, event_category, display_label,
       old_value, new_value, amount
FROM policy_timeline_event
WHERE policy_id = 'P-18492'
  AND event_date >= CURRENT_DATE - INTERVAL 1 YEAR
ORDER BY event_date""",
    ),
    (
        "Which material changes most often precede high-severity claims",
        """SELECT change_category,
       COUNT(*) AS change_count,
       COUNT(DISTINCT next_claim_id) AS claim_count
FROM policy_change_event
WHERE is_material = true
  AND change_timing = 'before_loss'
  AND days_to_next_claim_loss <= 60
  AND next_claim_severity IN ('severe','catastrophic')
GROUP BY change_category
ORDER BY claim_count DESC""",
    ),
    (
        "Vehicle and address changed within 60 days of each other",
        """SELECT policy_id, change_date, nearest_address_change_offset_days
FROM policy_change_event
WHERE change_category = 'vehicle'
  AND ABS(nearest_address_change_offset_days) <= 60""",
    ),
    (
        "Changes made after the loss but before it was reported",
        """SELECT policy_id, change_date, change_category, days_to_next_claim_loss
FROM policy_change_event
WHERE change_timing = 'after_loss_before_report'""",
    ),
    (
        "Claims near a recently raised limit",
        """SELECT c.claim_id, c.policy_id, c.settled_amount, c.severity_band,
       c.limit_utilization_pct
FROM claim_event c
JOIN policy_pattern_match p
  ON p.policy_id = c.policy_id
 AND p.pattern_code = 'claim_near_new_limit'
WHERE c.at_or_near_limit = true""",
    ),
    (
        "Recent changers versus everyone else — both groups, always",
        """SELECT CASE WHEN last_material_change_date >= CURRENT_DATE - INTERVAL 90 DAY
            THEN 'recent material change'
            ELSE 'no recent material change' END AS comparison_group,
       COUNT(*) AS policies,
       AVG(claims_per_year) AS claims_per_year
FROM policy_profile
GROUP BY 1""",
    ),
    (
        "Similar histories to a policy",
        """SELECT s.rank, s.similar_policy_id, s.similarity_score, s.top_reasons,
       p.material_change_count, p.claim_count, p.noteworthy_pattern_count
FROM policy_similarity s
JOIN policy_profile p ON p.policy_id = s.similar_policy_id
WHERE s.policy_id = 'P-18492'
ORDER BY s.rank""",
    ),
    (
        "Which patterns are most common",
        """SELECT pattern_name, COUNT(DISTINCT policy_id) AS policies
FROM policy_pattern_match
GROUP BY pattern_name
ORDER BY policies DESC""",
    ),
    (
        "Policies with nothing noteworthy",
        """SELECT policy_id FROM policy_profile WHERE noteworthy_pattern_count = 0""",
    ),
)

# A handful of curated starter prompts shown in the Genie UI before the user
# types anything (config.sample_questions). A subset of EXAMPLE_QUERIES plus
# one referencing the demo policy P-10155.
SAMPLE_QUESTIONS: tuple[str, ...] = (
    "Show policies where coverage increased within 30 days before a claim",
    "What changed before the latest claim on P-10155?",
    "Which material changes most often precede high-severity claims?",
    "Show me histories similar to P-10155",
    "Which patterns are most common?",
)


# ---------------------------------------------------------------------------
# Vocabulary self-check — E18 applies to Genie's own instructions too.
# ---------------------------------------------------------------------------

#: The vocabulary check (E18) forbids banned terms appearing in user-facing
#: output. The instruction that *tells Genie the banned list* necessarily
#: names those terms, same as spec 03 §7 itself and BANNED_VOCABULARY's own
#: definition in transformations.py — so lines carrying this marker are the
#: one deliberate, reviewed exemption, not a loophole for anything else.
_VOCAB_LISTING_MARKER = "Never use:"


def _validate() -> None:
    if set(TABLES) != {
        "policy_change_event", "claim_event", "policy_profile",
        "policy_timeline_event", "policy_pattern_match", "policy_similarity",
    } or len(TABLES) != 6:
        raise AssertionError(f"expected exactly the six curated tables, got {TABLES}")
    for label, lines in INSTRUCTION_BLOCKS:
        for line in lines:
            if line.startswith(_VOCAB_LISTING_MARKER):
                continue
            violations = vocabulary_violations(line)
            if violations:
                raise AssertionError(f"instruction block {label!r} uses banned vocabulary: {violations}")
    for question, sql in EXAMPLE_QUERIES:
        violations = vocabulary_violations(question) + vocabulary_violations(sql)
        if violations:
            raise AssertionError(f"example {question!r} uses banned vocabulary: {violations}")
    for q in SAMPLE_QUESTIONS:
        violations = vocabulary_violations(q)
        if violations:
            raise AssertionError(f"sample question {q!r} uses banned vocabulary: {violations}")
    violations = vocabulary_violations(DESCRIPTION)
    if violations:
        raise AssertionError(f"description uses banned vocabulary: {violations}")


_validate()


# ---------------------------------------------------------------------------
# Rendering — human-readable files (analogous to uc_comments.py's DDL render)
# ---------------------------------------------------------------------------

def render_instructions_md() -> str:
    lines = [
        "<!-- Rendered from genie/build_space.py; do not edit by hand. -->",
        "<!-- Source content: docs/specs/03-genie-knowledge.md. -->",
        "",
        f"# Genie general instructions — {TITLE}",
        "",
        "## Description",
        "",
        DESCRIPTION,
        "",
    ]
    for title, block_lines in INSTRUCTION_BLOCKS:
        lines.append(f"## {title}")
        lines.append("")
        for line in block_lines:
            lines.append(f"* {line}")
        lines.append("")
    return "\n".join(lines) + "\n"


def render_examples_sql() -> str:
    lines = [
        "-- Genie curated example SQL library.",
        "-- Rendered from genie/build_space.py; do not edit by hand.",
        "-- Source content: docs/specs/03-genie-knowledge.md §5.",
        "",
    ]
    for question, sql in EXAMPLE_QUERIES:
        lines.append(f"-- Q: {question}")
        lines.append(sql.rstrip() + ";")
        lines.append("")
    return "\n".join(lines) + "\n"


def _content_lines(text: str) -> list[str]:
    """Split into the ``[\"line1\\n\", \"line2\\n\", ...]`` shape the Genie
    space serialization format uses (observed on an existing space export)."""
    parts = text.split("\n")
    return [p + "\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _all_instructions_text() -> str:
    parts = []
    for title, block_lines in INSTRUCTION_BLOCKS:
        parts.append(f"{title}:")
        parts.extend(f"* {line}" for line in block_lines)
        parts.append("")
    return "\n".join(parts).rstrip("\n")


def serialized_space() -> str:
    space = {
        "version": 2,
        "config": {
            # API requires sorting by id.
            "sample_questions": sorted(
                (
                    {"id": _stable_id(f"sample-{i:02d}"), "question": _content_lines(q)}
                    for i, q in enumerate(SAMPLE_QUESTIONS, start=1)
                ),
                key=lambda d: d["id"],
            ),
        },
        "data_sources": {
            # API requires tables sorted by identifier.
            "tables": [
                {"identifier": f"{CATALOG}.{SCHEMA}.{table}"}
                for table in sorted(TABLES)
            ],
        },
        "instructions": {
            # API allows at most one text_instructions item, so all blocks
            # are concatenated into a single instruction document.
            "text_instructions": [
                {
                    "id": _stable_id("instructions"),
                    "content": _content_lines(_all_instructions_text()),
                }
            ],
            # API requires sorting by id.
            "example_question_sqls": sorted(
                (
                    {
                        "id": _stable_id(f"example-{i:02d}"),
                        "question": _content_lines(question),
                        "sql": _content_lines(sql),
                    }
                    for i, (question, sql) in enumerate(EXAMPLE_QUERIES, start=1)
                ),
                key=lambda d: d["id"],
            ),
        },
    }
    return json.dumps(space, indent=2)


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    return proc.stdout


def _databricks_cli() -> str:
    home = Path.home()
    candidate = home / ".local" / "bin" / "databricks"
    return str(candidate) if candidate.exists() else "databricks"


def cmd_render() -> None:
    here = Path(__file__).resolve().parent
    (here / "instructions.md").write_text(render_instructions_md())
    (here / "examples.sql").write_text(render_examples_sql())
    print(f"wrote {here / 'instructions.md'}")
    print(f"wrote {here / 'examples.sql'}")


def cmd_show() -> None:
    print(serialized_space())


def cmd_create() -> None:
    body = {
        "warehouse_id": WAREHOUSE_ID,
        "serialized_space": serialized_space(),
        "title": TITLE,
        "description": DESCRIPTION,
    }
    payload_path = Path(__file__).resolve().parent / ".create_space_payload.json"
    payload_path.write_text(json.dumps(body))
    out = _run([_databricks_cli(), "api", "post", "/api/2.0/genie/spaces",
                "--json", f"@{payload_path}"])
    print(out)


def cmd_update(space_id: str) -> None:
    body = {
        "warehouse_id": WAREHOUSE_ID,
        "serialized_space": serialized_space(),
        "title": TITLE,
        "description": DESCRIPTION,
    }
    payload_path = Path(__file__).resolve().parent / ".update_space_payload.json"
    payload_path.write_text(json.dumps(body))
    out = _run([_databricks_cli(), "api", "patch", f"/api/2.0/genie/spaces/{space_id}",
                "--json", f"@{payload_path}"])
    print(out)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "render":
        cmd_render()
    elif cmd == "show":
        cmd_show()
    elif cmd == "create":
        cmd_create()
    elif cmd == "update":
        if not rest:
            print("usage: build_space.py update SPACE_ID")
            return 1
        cmd_update(rest[0])
    else:
        print(f"unknown command: {cmd}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
