"""Spec section 5.5: no product surface and no agent may be able to name the truth.

The application, the pipeline and the documents that define the Genie space must
never mention the truth table, its schema or its column."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ("claim_fraud_truth", "ptm_eval", "is_fraud")
GUARDED_DIRS = ("app/backend", "app/frontend/src", "pipeline")
GUARDED_FILES = ("app/app.yaml", "docs/genie-curation.md", "docs/specs/03-genie-knowledge.md")
SUFFIXES = {".py", ".js", ".jsx", ".json", ".yaml", ".yml", ".md", ".sql", ".css"}


def _offenders():
    paths = [ROOT / f for f in GUARDED_FILES if (ROOT / f).exists()]
    for directory in GUARDED_DIRS:
        paths += [p for p in (ROOT / directory).rglob("*")
                  if p.is_file() and p.suffix in SUFFIXES
                  and "node_modules" not in p.parts and ".venv" not in p.parts]
    for path in paths:
        text = path.read_text(errors="ignore")
        for term in FORBIDDEN:
            if term in text:
                yield f"{path.relative_to(ROOT)}: {term}"


def test_the_truth_is_never_named_where_the_product_or_genie_can_see_it():
    assert not list(_offenders())
