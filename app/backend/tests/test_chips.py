import json

from backend.chips import CHIPS_PATH, chips_for_context, load_chip_bank

REQUIRED_CONTEXTS = {
    "investigation_start",
    "timeline_open",
    "similarity_view",
    "cohort_on_screen",
}

# Task brief + ADR-0014 / 03-genie-knowledge.md §7 banned vocabulary.
BANNED_TERMS = [
    "fraud",
    "fraudulent",
    "suspicious",
    "red flag",
    "anomaly",
    "risk",
    "scheme",
    "deceptive",
    "guilty",
    "predicts",
    "causes",
    "leads to",
]


def test_chips_json_is_valid_json():
    with CHIPS_PATH.open(encoding="utf-8") as f:
        bank = json.load(f)
    assert isinstance(bank, dict) and bank


def test_required_contexts_present():
    bank = load_chip_bank()
    missing = REQUIRED_CONTEXTS - bank.keys()
    assert not missing, f"missing required chip contexts: {missing}"


def test_every_chip_is_a_non_empty_string():
    bank = load_chip_bank()
    for context, chip_list in bank.items():
        assert isinstance(chip_list, list) and chip_list, f"{context} has no chips"
        for chip in chip_list:
            assert isinstance(chip, str), f"non-string chip in {context}: {chip!r}"
            assert chip.strip(), f"empty/whitespace chip in {context}"


def test_every_context_has_three_to_five_chips():
    bank = load_chip_bank()
    for context, chip_list in bank.items():
        assert 3 <= len(chip_list) <= 5, f"{context} has {len(chip_list)} chips, expected 3-5"


def test_chips_are_complete_sentences_not_fragments():
    # A crude but effective fragment check: every chip authored as a
    # complete, context-free question (ADR-0011) reads as a full
    # sentence — capitalised, and ending with '.' or '?'.
    bank = load_chip_bank()
    for context, chip_list in bank.items():
        for chip in chip_list:
            assert chip[0].isupper(), f"chip does not start capitalised in {context}: {chip!r}"
            assert chip.rstrip()[-1] in ".?", f"chip is not a complete sentence in {context}: {chip!r}"


def test_no_banned_vocabulary_anywhere_in_the_bank():
    bank = load_chip_bank()
    for context, chip_list in bank.items():
        for chip in chip_list:
            lowered = chip.lower()
            for term in BANNED_TERMS:
                assert term not in lowered, f"banned term {term!r} found in chip {chip!r} ({context})"


def test_chips_for_context_helper():
    assert chips_for_context("investigation_start")
    assert chips_for_context("not-a-real-context") == []
