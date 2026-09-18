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


import ast


def test_detector_surface_may_name_fraud_but_not_a_person():
    assert violations("This claim has a 0.82 probability of fraud.", surface="detector") == []
    assert violations("Likely fraud on this claim.", surface="detector") == []   # 'likely' is allowed here
    assert "person as subject" in violations("The policyholder committed fraud.", surface="detector")
    assert violations("It predicts fraud.", surface="detector") == ["predicts"]
    assert violations("Adele Ashcroft's claim.", surface="detector",
                      person_names=("Adele Ashcroft",)) == ["person name"]


def test_detector_surface_still_rejects_another_policy_id():
    assert violations("Same shape as P-20114.", own_policy_id="P-10155",
                      surface="detector") == ["policy id P-20114"]


def test_ci_copy_of_the_banned_list_matches():
    """ci/genie/ground_truth.py imports the Databricks SDK, so read it with ast."""
    path = Path(__file__).resolve().parents[3] / "ci" / "genie" / "ground_truth.py"
    tree = ast.parse(path.read_text())
    values = [
        ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "BANNED_VOCABULARY" for t in node.targets)
    ]
    assert values and tuple(values[0]) == tuple(BANNED_VOCABULARY)
