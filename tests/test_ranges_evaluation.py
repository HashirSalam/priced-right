import json
import sys

import numpy as np
import pandas as pd
import pytest

from priced_right import final_evaluation, ranges
from priced_right.models import TUNED_PATH
from priced_right.split import load_train


@pytest.fixture(scope="module")
def train():
    return load_train()


# ---------------------------------------------------------------- price ranges

def test_conformal_quantile_uses_the_finite_sample_rank():
    errors = np.arange(1, 11)  # 10 errors: rank ceil(11 * 0.8) = 9
    assert ranges.conformal_quantile(errors, 0.8) == 9
    assert ranges.conformal_quantile(np.array([0.5]), 0.8) == 0.5  # never beyond the largest error


def test_launch_periods():
    years = pd.Series([2008, 2016, 2017, 2019, 2020, 2022, 2023, 2026])
    assert list(ranges.launch_period(years)) == [
        "2016 or earlier", "2016 or earlier", "2017-19", "2017-19", "2020-22", "2020-22", "2023 or later", "2023 or later"]


def test_price_range_contains_the_prediction(train):
    tuned = json.loads(TUNED_PATH.read_text(encoding="utf-8"))
    spec = tuned["models"][tuned["final_model"]]
    sample = train.sample(400, random_state=0)
    price_range = ranges.PriceRange(tuned["final_model"], spec["columns"], spec["params"]).fit(sample)
    out = price_range.predict(sample.head(50))
    assert (out["low"] < out["price"]).all() and (out["price"] < out["high"]).all()
    assert set(price_range.half_widths_) <= set(ranges.PERIOD_LABELS)
    assert (out["factor"] > 1).all()


# ---------------------------------------------------------------- final evaluation

def test_bootstrap_is_reproducible_and_scores_both_models():
    test = pd.DataFrame({"relisting_group": [0, 0, 1, 2, 3, 4]})
    y = np.log1p(np.array([100, 100, 200, 300, 400, 500.0]))
    first = final_evaluation.bootstrap(test, y, y + 0.1, y + 0.3, n=50)
    second = final_evaluation.bootstrap(test, y, y + 0.1, y + 0.3, n=50)
    assert first.equals(second) and len(first) == 50
    assert np.allclose(first["improvement"], 1 - first["rmsle"] / first["baseline_rmsle"])


def test_refuses_to_run_twice(tmp_path, monkeypatch):
    existing = tmp_path / "test_results.json"
    existing.write_text("{}")
    monkeypatch.setattr(final_evaluation, "RESULTS_PATH", existing)
    monkeypatch.setattr(final_evaluation, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["final_evaluation"])
    with pytest.raises(SystemExit, match="already exists"):
        final_evaluation.main()


def test_committed_test_results_are_complete():
    results = json.loads(final_evaluation.RESULTS_PATH.read_text(encoding="utf-8"))
    assert results["n_test"] > 0 and 0 <= results["coverage"] <= 1
    assert set(results["model_scores"]) == {"rmsle", "mae_eur", "median_ape"}
    assert len(results["checks"]) >= 4
