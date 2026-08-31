from backend.policy_ids import detect_policy_ids, resolve_timeline_policy_id


def test_single_match_opens_timeline():
    ids = detect_policy_ids("What changed on P-18492 last year?")
    assert ids == ["P-18492"]
    assert resolve_timeline_policy_id(ids) == "P-18492"


def test_several_matches_suppress_timeline():
    ids = detect_policy_ids("Compare P-18492 and P-20114.")
    assert ids == ["P-18492", "P-20114"]
    assert resolve_timeline_policy_id(ids) is None


def test_zero_matches_suppress_timeline():
    ids = detect_policy_ids("Which patterns are most common?")
    assert ids == []
    assert resolve_timeline_policy_id(ids) is None


def test_case_insensitive_and_normalised_to_upper():
    ids = detect_policy_ids("what changed on p-18492 recently")
    assert ids == ["P-18492"]


def test_word_boundaries_exclude_claim_and_endorsement_ids():
    # A policy id embedded in a longer identifier must not match
    # (ADR-0007: the pattern is lexically reserved).
    ids = detect_policy_ids("Claim CLM-002317 relates to endorsement END-00418302.")
    assert ids == []


def test_embedded_digits_without_word_boundary_do_not_match():
    ids = detect_policy_ids("See GROUP-12345 for details.")
    assert ids == []


def test_dedupe_preserves_first_seen_order():
    ids = detect_policy_ids("P-20114 mentioned again as p-20114, then P-18492.")
    assert ids == ["P-20114", "P-18492"]


def test_rejects_wrong_digit_counts():
    ids = detect_policy_ids("P-1849 and P-184922 are not valid policy ids.")
    assert ids == []
