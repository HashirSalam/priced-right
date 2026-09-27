import json

import numpy as np
import pandas as pd
import pytest

from priced_right import evaluate, features, models, pipelines
from priced_right.split import load_train


@pytest.fixture(scope="module")
def train():
    return load_train()


# ---------------------------------------------------------------- scoring

def test_scores():
    y = np.log1p(np.array([100.0, 200.0]))
    s = evaluate.scores(y, np.log1p(np.array([110.0, 180.0])))
    assert s["mae_eur"] == pytest.approx(15.0)
    assert s["median_ape"] == pytest.approx(0.1)
    assert evaluate.scores(y, y)["rmsle"] == 0


def test_folds_keep_relisting_groups_together(train):
    for fit, held_out in evaluate.cv_splitter().split(train, groups=train["relisting_group"]):
        assert not set(train["relisting_group"].iloc[fit]) & set(train["relisting_group"].iloc[held_out])


def test_folds_are_the_same_every_time(train):
    first = [list(t) for _, t in evaluate.cv_splitter().split(train, groups=train["relisting_group"])]
    second = [list(t) for _, t in evaluate.cv_splitter().split(train, groups=train["relisting_group"])]
    assert first == second


def test_cross_validate_and_summarize(train):
    X, y = features.build(train), features.target(train)
    folds = evaluate.cross_validate(pipelines.baseline(), X, y, train["relisting_group"])
    assert len(folds) == evaluate.N_SPLITS
    summary = evaluate.summarize(folds)
    assert summary["rmsle_se"] == pytest.approx(folds["rmsle"].std() / np.sqrt(evaluate.N_SPLITS))


# ---------------------------------------------------------------- feature check and choice

@pytest.mark.parametrize("phone", list(models.PHONE))
@pytest.mark.parametrize("condition", list(models.CONDITION))
def test_alternative_encodings_are_never_combined(phone, condition):
    columns = models.inputs(phone, condition, list(features.GROUPS))
    assert not ({"exact_model"} & set(columns) and {"release_year", "tier"} & set(columns))
    assert not ({"condition_rank"} & set(columns) and {"condition_level"} & set(columns))


def test_inputs_can_leave_out_the_phone_model_or_condition():
    assert models.inputs(None, None, ["storage"]) == ["storage_log2"]


def test_one_standard_error_rule_prefers_the_simpler_model():
    results = pd.DataFrame({
        "model": list(pipelines.MODELS),
        "rmsle_mean": [0.40, 0.35, 0.293, 0.30, 0.290],  # linear, tree, forest, SVR, boosting
        "rmsle_se": [0.01, 0.01, 0.005, 0.005, 0.005],
    })
    chosen, threshold = models.choose(results)
    assert threshold == pytest.approx(0.295)
    assert chosen == "Random forest"  # within one SE of boosting, and easier to explain


def test_grid_edges():
    assert models.grid_edges("SVR", {"C": 300.0, "gamma": 0.01, "epsilon": 0.05}) == ["C"]
    assert models.grid_edges("Random forest", {"max_features": 1.0, "min_samples_leaf": 1, "max_depth": None}) == []


def test_grids_only_name_real_model_settings():
    for name, grid in models.GRIDS.items():
        settings = pipelines.MODELS[name][0].get_params()
        assert all(key.removeprefix("model__") in settings for key in grid)
    assert list(models.SIMPLICITY_ORDER) == sorted(pipelines.MODELS, key=models.SIMPLICITY_ORDER.index)


# ---------------------------------------------------------------- committed results

def test_committed_selection_is_consistent():
    selection = json.loads(models.SELECTION_PATH.read_text(encoding="utf-8"))
    tuned = json.loads(models.TUNED_PATH.read_text(encoding="utf-8"))
    assert set(selection["models"]) == set(pipelines.MODELS)
    assert tuned["final_model"] in pipelines.MODELS
    for name, choice in selection["models"].items():
        assert tuned["models"][name]["columns"] == choice["columns"]
        assert choice["columns"] == models.inputs(choice["phone"], choice["condition"], selection["kept_groups"])
