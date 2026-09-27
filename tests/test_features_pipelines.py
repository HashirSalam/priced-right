import numpy as np
import pandas as pd
import pytest

from priced_right import features, pipelines
from priced_right.split import load_train

ALL_INPUTS = sorted(features.CATEGORICAL | features.NUMERIC | features.FLAGS)


@pytest.fixture(scope="module")
def train():
    return load_train()


@pytest.fixture(scope="module")
def sample(train):
    return train.sample(300, random_state=0)


# ---------------------------------------------------------------- target

def test_target_round_trip():
    df = pd.DataFrame({"price_eur": [6, 250, 2299]})
    assert np.allclose(features.to_price(features.target(df)), [6, 250, 2299])


# ---------------------------------------------------------------- inputs

@pytest.mark.parametrize("model, expected", [
    ("iPhone 13", "base"), ("iPhone XR", "base"), ("iPhone 6s", "base"), ("iPhone 5c", "base"),
    ("iPhone 15 Pro", "Pro"), ("iPhone X", "Pro"), ("iPhone XS", "Pro"),
    ("iPhone 15 Pro Max", "Pro Max"), ("iPhone XS Max", "Pro Max"),
    ("iPhone 14 Plus", "Plus"), ("iPhone 6s Plus", "Plus"), ("iPhone 12 Mini", "Mini"),
    ("iPhone 16e", "e"), ("iPhone 17e", "e"), ("iPhone Air", "Air"),
    ("iPhone SE", "SE"), ("iPhone SE (3rd gen)", "SE"),
])
def test_tier(model, expected):
    assert features.tier(model) == expected


def test_battery_bands_keep_not_mentioned_as_its_own_band():
    bands = features.battery_band(pd.Series([None, 54, 79, 80, 89, 90, 100], dtype=float))
    assert list(bands) == ["not mentioned", "under 80%", "under 80%", "80-89%", "80-89%", "90-100%", "90-100%"]


def test_build_gives_every_candidate_input_and_nothing_else(train):
    X = features.build(train)
    assert sorted(X.columns) == ALL_INPUTS
    assert X.index.equals(train.index)
    # not allowed as inputs (docs/ml-plan.md, section 4)
    assert not {"listing_age_days", "published_at", "title", "description", "model_group",
                "municipality", "price_eur"} & set(X.columns)


def test_build_encodings(train):
    X = features.build(train)
    assert X.loc[train["storage_gb"] == 128, "storage_log2"].eq(7).all()
    assert X["condition_rank"].dropna().isin([0, 1, 2, 3, 4]).all()
    assert X.loc[train["condition"] == "Uusi", "condition_rank"].eq(4).all()
    assert X.loc[train["condition"].isna(), "condition_level"].eq("missing").all()
    assert X["battery_band"].notna().all()
    assert set(X["tier"]) <= {"base", "Pro", "Pro Max", "Plus", "Mini", "e", "SE", "Air"}


def test_year_and_tier_are_determined_by_the_model_name(train):
    X = features.build(train)
    assert X.groupby("exact_model")[["release_year", "tier"]].nunique().max().max() == 1


# ---------------------------------------------------------------- pipelines

def test_scaling_and_dropped_dummies_only_where_the_model_needs_them():
    for name, (_, scale, drop_first) in pipelines.MODELS.items():
        assert scale == (name in ("Linear regression", "SVR"))
        assert drop_first == (name == "Linear regression")


@pytest.mark.parametrize("name", list(pipelines.MODELS))
@pytest.mark.parametrize("model_as", [features.MODEL_AS_NAME, features.MODEL_AS_YEAR_AND_TIER])
@pytest.mark.parametrize("condition_as", [features.CONDITION_AS_RANK, features.CONDITION_AS_LEVELS])
def test_every_pipeline_fits_and_predicts(sample, name, model_as, condition_as):
    columns = model_as + condition_as + [c for group in features.GROUPS.values() for c in group]
    X, y = features.build(sample), features.target(sample)
    pred = pipelines.build(name, columns).fit(X, y).predict(X)
    assert pred.shape == (len(sample),) and np.isfinite(pred).all()


def test_fill_in_values_are_learned_from_training_rows_only(train):
    """The median used for missing storage comes from the rows the pipeline was fitted on, not all data."""
    X, y = features.build(train), features.target(train)
    fit_rows = X["release_year"] < 2020  # a subset with a clearly different storage median
    pipe = pipelines.build("Linear regression", ["release_year", "storage_log2"]).fit(X[fit_rows], y[fit_rows])
    imputer = pipe.named_steps["prep"].named_transformers_["numeric"].named_steps["simpleimputer"]
    assert imputer.statistics_[1] == X.loc[fit_rows, "storage_log2"].median()
    assert imputer.statistics_[1] != X["storage_log2"].median()


@pytest.mark.filterwarnings("ignore:Found unknown categories")  # expected: that's what this test feeds in
@pytest.mark.parametrize("name", list(pipelines.MODELS))
def test_unseen_values_dont_crash_predictions(sample, name):
    columns = features.MODEL_AS_NAME + ["tier", "seller_type", "region", "storage_log2"]
    pipe = pipelines.build(name, columns).fit(features.build(sample), features.target(sample))
    new = features.build(sample.head(1)).assign(exact_model="iPhone 18", tier="Ultra", region="Ahvenanmaa")
    assert np.isfinite(pipe.predict(new)).all()


def test_unknown_input_is_rejected():
    with pytest.raises(ValueError, match="listing_age_days"):
        pipelines.preprocessor(["storage_log2", "listing_age_days"], scale=False, drop_first=False)


def test_baseline_falls_back_to_less_specific_groups():
    X = pd.DataFrame({"exact_model": ["a", "a", "b"], "storage_log2": [6.0, 7.0, 6.0]})
    baseline = pipelines.baseline().fit(X, np.array([1.0, 3.0, 5.0]))
    new = pd.DataFrame({"exact_model": ["a", "a", "c"], "storage_log2": [7.0, 9.0, 6.0]})
    assert list(baseline.predict(new)) == [3.0, 2.0, 3.0]  # (model, storage), model only, overall
