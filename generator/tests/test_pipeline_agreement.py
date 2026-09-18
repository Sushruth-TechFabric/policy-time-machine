"""The label is allocated on generator.behaviour; the detector reads the pipeline's
claim_context. If the two derivations disagree, the planted signal is not the
signal an agent can see."""

import datetime as dt
import importlib.util
from pathlib import Path

import pytest

from generator import build
from generator.behaviour import claim_flags


def _transformations():
    path = Path(__file__).resolve().parents[2] / "pipeline" / "transformations.py"
    spec = importlib.util.spec_from_file_location("ptm_transformations", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"pipeline module not importable here: {exc}")
    return module


def test_behaviour_facts_agree_with_claim_context():
    T = _transformations()
    frames = build(42, dt.datetime.now(dt.timezone.utc).date())
    context = T.build_claim_context(
        frames["claim"], frames["policy_history"], frames["vehicle"], frames["claim_note"]
    ).set_index("claim_id")
    facts = claim_flags(frames).set_index("claim_id")
    assert set(context.index) == set(facts.index)
    context = context.loc[facts.index]
    assert (context["policy_age_at_loss_days"].astype(int) == facts["policy_age_at_loss_days"]).all()
    assert (context["reinstated_within_30d_before_loss"].astype(bool) == facts["recent_reinstatement"]).all()
    assert (context["vehicle_added_within_30d_before_loss"].astype(bool) == facts["new_vehicle"]).all()
    assert (context["note_text"] == frames["claim_note"].set_index("claim_id")["note_text"]).all()
