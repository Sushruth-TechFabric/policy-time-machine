"""ADR-0020: one banned list, two surfaces. The default surface is today's rule."""

import pytest

import transformations as T


def test_the_list_is_the_union_and_has_todays_members():
    assert T.BANNED_VOCABULARY == T.ACCUSATORY_TERMS + T.ALWAYS_BANNED
    assert set(T.BANNED_VOCABULARY) == {
        "fraud", "fraudulent", "suspicious", "scheme", "deceptive", "guilty",
        "risk score", "predicts", "causes", "leads to", "increases the risk of",
        "anomaly", "anomalous", "red flag",
    }
    assert "guilty" in T.ALWAYS_BANNED and "fraud" in T.ACCUSATORY_TERMS


@pytest.mark.parametrize("text", [
    "This looks suspicious.", "A red flag.", "It predicts a claim.", "Risk  score is high",
])
def test_the_default_surface_is_the_investigation_surface(text):
    assert T.vocabulary_violations(text) == T.vocabulary_violations(text, surface="investigation")
    assert T.vocabulary_violations(text)


def test_the_detector_surface_may_name_fraud_about_a_claim():
    assert T.vocabulary_violations(
        "This claim has a 0.82 probability of fraud.", surface="detector") == []
    assert T.vocabulary_violations(
        "Likely fraudulent claim; the note gives no location.", surface="detector") == []


def test_the_detector_surface_still_bans_causal_and_verdict_words():
    assert T.vocabulary_violations("A coverage raise predicts fraud.", surface="detector") == ["predicts"]
    assert T.vocabulary_violations("The claim is guilty.", surface="detector") == ["guilty"]


@pytest.mark.parametrize("text", [
    "The policyholder committed fraud.",
    "The insured is suspicious.",
    "A fraudulent claimant filed this.",
    "The driver staged the collision.",
])
def test_the_detector_surface_never_makes_a_person_the_subject(text):
    assert "person as subject" in T.vocabulary_violations(text, surface="detector")


def test_the_detector_surface_rejects_a_customer_name():
    found = T.vocabulary_violations(
        "Adele Ashcroft's claim is likely fraud.", surface="detector",
        person_names=("Adele Ashcroft",))
    assert found == ["person name"]


def test_an_unknown_surface_is_an_error():
    with pytest.raises(ValueError):
        T.vocabulary_violations("anything", surface="marketing")
