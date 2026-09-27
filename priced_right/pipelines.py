"""The baseline and one pipeline per candidate model (lifecycle steps 19-21).

Each pipeline is preprocessing + model in one scikit-learn object, so everything learned from
data (fill-in medians, scaling, which categories exist) is fitted on the training part only:
inside every cross-validation fold, and later on the full training set.

Preprocessing differs by model, because models need their inputs in different forms. That keeps
the comparison fair: every model gets the same information.

| Model              | Scale numbers? | Drop one dummy column? | Why                                         |
|--------------------|----------------|------------------------|---------------------------------------------|
| Linear regression  | yes            | yes                    | comparable coefficients; avoids the dummy variable trap |
| Decision tree      | no             | no                     | splits on thresholds, units don't matter    |
| Random forest      | no             | no                     | same as a tree                              |
| SVR                | yes            | no                     | distance-based: unscaled inputs would dominate |
| Gradient boosting  | no             | no                     | tree-based                                  |

All models predict log1p(price) (features.target).
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVR
from sklearn.tree import DecisionTreeRegressor

from priced_right import features

SEED = 42

# Categories with fewer training listings than this share one "infrequent" column
# (e.g. iPhone 5c, Keski-Pohjanmaa), so a value seen only a couple of times can't get
# a coefficient or a split of its own.
MIN_CATEGORY_SIZE = 5


class MedianBaseline(RegressorMixin, BaseEstimator):
    """Median log price of the most specific group seen in training: (model, storage), then model, then overall.

    What a careful user could do by hand on Tori; the model to beat (docs/ml-plan.md).
    """

    def __init__(self, levels: Sequence[Sequence[str]] = (("exact_model", "storage_log2"), ("exact_model",))):
        self.levels = levels

    def fit(self, X: pd.DataFrame, y: np.ndarray):
        frame = X.assign(_y=y)
        self.medians_ = [frame.groupby(list(keys))["_y"].median().to_dict() for keys in self.levels]
        self.overall_ = float(np.median(y))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        preds = []
        for _, row in X.iterrows():
            value = self.overall_
            for keys, medians in zip(self.levels, self.medians_, strict=True):
                key = row[keys[0]] if len(keys) == 1 else tuple(row[k] for k in keys)
                if key in medians:
                    value = medians[key]
                    break
            preds.append(value)
        return np.array(preds)


# name -> (model with sensible default settings, scale numbers?, drop one dummy column?)
# Settings are tuned in the modelling step (step 23); these defaults are only a starting point.
MODELS = {
    "Linear regression": (LinearRegression(), True, True),
    "Decision tree": (DecisionTreeRegressor(max_depth=8, min_samples_leaf=5, random_state=SEED), False, False),
    "Random forest": (RandomForestRegressor(n_estimators=300, max_features=0.5, min_samples_leaf=3,
                                            n_jobs=-1, random_state=SEED), False, False),
    "SVR": (SVR(C=10.0), True, False),
    "Gradient boosting": (HistGradientBoostingRegressor(random_state=SEED), False, False),
}


def preprocessor(columns: Sequence[str], scale: bool, drop_first: bool) -> ColumnTransformer:
    """Encode each input by its type (features.CATEGORICAL / NUMERIC / FLAGS).

    - categories: one 0/1 column per value; rare values share one column; values never seen in
      training (e.g. a new iPhone) go to that shared column instead of crashing
    - numbers: missing values filled with the training median, plus a was-missing 0/1 column; scaled if asked
    - flags: already 0/1, passed through
    """
    unknown = [c for c in columns if c not in features.CATEGORICAL | features.NUMERIC | features.FLAGS]
    if unknown:
        raise ValueError(f"no encoding defined for {unknown}")
    categorical = [c for c in columns if c in features.CATEGORICAL]
    numeric = [c for c in columns if c in features.NUMERIC]
    flags = [c for c in columns if c in features.FLAGS]

    parts = []
    if categorical:
        encoder = OneHotEncoder(drop="first" if drop_first else None, handle_unknown="infrequent_if_exist",
                                min_frequency=MIN_CATEGORY_SIZE, sparse_output=False)
        parts.append(("categorical", encoder, categorical))
    if numeric:
        steps = [SimpleImputer(strategy="median", add_indicator=True)] + ([StandardScaler()] if scale else [])
        parts.append(("numeric", make_pipeline(*steps), numeric))
    if flags:
        parts.append(("flags", "passthrough", flags))
    return ColumnTransformer(parts)


def build(name: str, columns: Sequence[str], **params) -> Pipeline:
    """Preprocessing + model, e.g. build("SVR", ["release_year", "tier", "storage_log2"], C=3.0).

    `params` override the model's default settings (used by tuning).
    """
    estimator, scale, drop_first = MODELS[name]
    return Pipeline([
        ("prep", preprocessor(columns, scale, drop_first)),
        ("model", clone(estimator).set_params(**params)),
    ])


def baseline() -> MedianBaseline:
    """The median baseline. It uses exact_model and storage_log2 from features.build(), whatever the other models use."""
    return MedianBaseline()
