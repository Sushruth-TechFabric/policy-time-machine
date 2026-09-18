from backend.review.questions import (
    Situation,
    canonical_question,
    detect_situation,
    validate_question,
    window_days,
)

GAP = {"change_timing": "after_loss_before_report", "days_to_next_claim_loss": -3}
BEFORE = {"change_timing": "before_loss", "days_to_next_claim_loss": 63}
PATTERN = {"pattern_code": "rapid_change_cluster", "pattern_name": "Rapid change cluster"}


def test_detect_situation_precedence():
    assert detect_situation([GAP, BEFORE], [PATTERN]) == Situation.RELEVANT_IN_GAP
    assert detect_situation([BEFORE], [PATTERN]) == Situation.RELEVANT_BEFORE_LOSS
    assert detect_situation([], [PATTERN]) == Situation.PATTERN_ONLY
    assert detect_situation([], []) == Situation.NOTHING_BEFORE


def test_window_days_buckets_up_to_30_60_90():
    assert window_days([{"days_to_next_claim_loss": 12}]) == 30
    assert window_days([{"days_to_next_claim_loss": 63}]) == 90
    assert window_days([{"days_to_next_claim_loss": 45}, {"days_to_next_claim_loss": 5}]) == 30
    assert window_days([]) == 90


def test_canonical_questions_are_comparisons_and_clean():
    for situation in Situation:
        q = canonical_question(
            situation, coverage_line="COLL", line_name="collision", window=60,
            pattern_name="Rapid change cluster",
        )
        assert any(word in q.lower() for word in ("versus", "compared", "against"))
        assert "fraud" not in q.lower()


def test_validate_question_accepts_matching_shape():
    proposal = {"shape": "relevant_before_loss",
                "question": "How often does a collision limit increase within 90 days before a claim precede a high-severity claim, compared with increases not followed by one?"}
    assert validate_question(Situation.RELEVANT_BEFORE_LOSS, proposal) is None


def test_validate_question_rejects_wrong_shape_missing_comparison_and_banned_terms():
    assert "shape" in validate_question(Situation.NOTHING_BEFORE, {"shape": "pattern_only", "question": "x versus y"})
    assert "comparison" in validate_question(Situation.NOTHING_BEFORE, {"shape": "nothing_before", "question": "How many claims had no change?"})
    assert "vocabulary" in validate_question(Situation.NOTHING_BEFORE, {"shape": "nothing_before", "question": "Suspicious claims versus others?"})
    assert "question" in validate_question(Situation.NOTHING_BEFORE, {"shape": "nothing_before"})
