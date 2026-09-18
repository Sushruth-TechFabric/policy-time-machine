"""The runtime vocabulary check mirrors pipeline expectation E18 for text
the pipeline cannot see (model-generated sentences)."""

import importlib.util
from pathlib import Path

import pytest

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
    try:
        spec.loader.exec_module(module)
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"pipeline module not importable here: {exc}")
    assert tuple(BANNED_VOCABULARY) == tuple(module.BANNED_VOCABULARY)
