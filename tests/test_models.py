import numpy as np
import pandas as pd

from priced_right import evaluate
from priced_right.models import MedianBaseline, ridge_model


def test_median_baseline_falls_back_from_storage_to_model_to_overall():
    train = pd.DataFrame({"exact_model": ["A", "A", "A", "B"], "storage_gb": [64, 64, 128, 64]})
    y = np.array([1.0, 3.0, 10.0, 20.0])
    model = MedianBaseline().fit(train, y)
    test = pd.DataFrame({"exact_model": ["A", "A", "C"], "storage_gb": [64, 256, 64]})
    # (A, 64) seen -> median 2; (A, 256) unseen -> model A median 3; C unseen -> overall median 6.5
    assert model.predict(test).tolist() == [2.0, 3.0, 6.5]


def test_scores_are_zero_for_perfect_predictions():
    y = np.log1p(np.array([100.0, 250.0]))
    assert evaluate.scores(y, y) == {"rmsle": 0.0, "mae_eur": 0.0, "median_ape": 0.0}


def test_folds_keep_relisting_groups_together():
    df = pd.DataFrame({"relisting_group": [0, 0, 1, 1, 2, 3, 4, 5, 6, 7]})
    for train, test in evaluate.folds(df, n_splits=5):
        assert not set(df.relisting_group.iloc[train]) & set(df.relisting_group.iloc[test])


def test_models_run_on_the_cleaned_data():
    df = evaluate.load_clean().sample(400, random_state=0)
    for model in (MedianBaseline(), ridge_model()):
        results = evaluate.cross_validate(model, df, n_splits=3)
        assert len(results) == 3 and results.rmsle.between(0, 2).all()
