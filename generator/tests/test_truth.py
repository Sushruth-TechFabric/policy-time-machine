import datetime as dt

import pytest

from generator import build, truth
from generator.allocation import exact_count
from generator.behaviour import FLAGS, claim_flags

SEED = 42


@pytest.fixture(scope="module")
def frames():
    return build(SEED, dt.datetime.now(dt.timezone.utc).date())


@pytest.fixture(scope="module")
def labelled(frames):
    return frames[truth.TABLE]


def test_one_truth_row_and_one_note_per_claim(frames, labelled):
    ids = list(frames["claim"]["claim_id"])
    assert list(labelled["claim_id"]) == ids
    assert list(frames["claim_note"]["claim_id"]) == ids
    assert list(labelled.columns) == ["claim_id", "is_fraud", "population"]
    assert set(labelled["population"]) == {"S", "C", "background"}


def test_rates_are_exact_in_every_population(labelled):
    by = labelled.groupby("population")["is_fraud"].agg(["sum", "size"])
    assert by.loc["C", "sum"] == 0
    assert by.loc["S", "sum"] == exact_count(truth.S_RATE, int(by.loc["S", "size"]))
    assert by.loc["background", "sum"] == exact_count(
        truth.BACKGROUND_RATE, int(by.loc["background", "size"]))


def test_control_policies_never_carry_the_label(frames, labelled):
    assignment = frames["scenario_assignment"]
    control = set(assignment.loc[assignment["scenario_id"].str.startswith("C"), "policy_id"])
    on_control = frames["claim"]["policy_id"].isin(control).to_numpy()
    assert not labelled.loc[on_control, "is_fraud"].any()
    assert set(labelled.loc[on_control, "population"]) == {"C"}


def test_early_tenure_raises_the_background_rate(frames, labelled):
    """The one flag common enough to measure; the rarer two expect one or two
    labelled claims each, so only the stratum check in validate_truth binds them."""
    merged = labelled.merge(claim_flags(frames), on="claim_id")
    background = merged[merged["population"] == "background"]
    on, off = background[background["early_tenure"]], background[~background["early_tenure"]]
    assert on["is_fraud"].mean() > 2 * off["is_fraud"].mean()


def test_the_truth_is_owned_by_the_seed_not_the_anchor(frames):
    earlier = build(SEED, dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=400))
    assert frames[truth.TABLE].equals(earlier[truth.TABLE])
    assert frames["claim_note"].equals(earlier["claim_note"])
    other = build(SEED + 1, dt.datetime.now(dt.timezone.utc).date())
    fraud_ids = set(frames[truth.TABLE].loc[frames[truth.TABLE]["is_fraud"], "claim_id"])
    other_fraud_ids = set(other[truth.TABLE].loc[other[truth.TABLE]["is_fraud"], "claim_id"])
    assert fraud_ids != other_fraud_ids
    rebuild = build(SEED, dt.datetime.now(dt.timezone.utc).date())
    assert frames[truth.TABLE].equals(rebuild[truth.TABLE])
    assert frames["claim_note"].equals(rebuild["claim_note"])


def test_write_keeps_the_truth_out_of_the_source_directory(frames, tmp_path):
    from generator.emit import write
    out = tmp_path / "raw"
    write(frames, out, dt.datetime.now(dt.timezone.utc).date())
    path = truth.write(frames, truth.default_dir(out))
    assert path == out / "eval" / f"{truth.TABLE}.parquet" and path.exists()
    assert (out / "claim_note.parquet").exists()
    assert not (out / f"{truth.TABLE}.parquet").exists()
