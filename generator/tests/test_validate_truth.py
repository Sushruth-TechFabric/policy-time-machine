import datetime as dt

import numpy as np
import pytest

from generator import truth, validate as validation, validate_truth
from generator.__main__ import main as generator_main


def test_auc_handles_ties_and_perfect_separation():
    assert validate_truth.auc(np.array([3.0, 2.0, 1.0, 0.0]), np.array([1, 1, 0, 0])) == 1.0
    assert validate_truth.auc(np.array([1.0, 1.0, 1.0, 1.0]), np.array([1, 0, 1, 0])) == 0.5


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("raw")
    anchor = dt.datetime.now(dt.timezone.utc).date().isoformat()
    assert generator_main(["--seed", "42", "--anchor-date", anchor, "--out", str(out)]) == 0
    return out


def test_every_detection_check_passes_on_a_fresh_build(generated):
    report, measurements = validation.run(generated)
    detection = [c for c in report.checks if c.name.startswith("detection:")]
    assert len(detection) >= 7
    failed = [f"{c.name}: {c.detail}" for c in detection if not c.passed]
    assert not failed, "\n".join(failed)
    low, high = validate_truth.AUC_BAND
    assert low <= measurements["detection"]["reference_auc"] <= high
    assert validate_truth.summary_lines(measurements)


def test_a_relabelled_truth_fails_validation(generated, tmp_path):
    table = truth.load(truth.default_dir(generated)).copy()
    table["is_fraud"] = table["population"].eq("C")     # label exactly the controls
    broken = tmp_path / "eval"
    broken.mkdir()
    table.to_parquet(broken / f"{truth.TABLE}.parquet")
    report, _ = validation.run(generated, truth_dir=broken)
    failed = {c.name for c in report.checks if not c.passed}
    assert "detection: declared rates are exact" in failed


def test_other_seeds_also_pass(tmp_path):
    for seed in (7, 1234):
        out = tmp_path / str(seed)
        anchor = dt.datetime.now(dt.timezone.utc).date().isoformat()
        generator_main(["--seed", str(seed), "--anchor-date", anchor, "--out", str(out)])
        report, _ = validation.run(out)
        failed = [c.name for c in report.checks if c.name.startswith("detection:") and not c.passed]
        assert not failed, f"seed {seed}: {failed}"
