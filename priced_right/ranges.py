"""Expected price plus an 80% price range (lifecycle step 27, docs/ml-plan.md section 7).

The range comes from held-out errors: the model's out-of-fold errors on the training data,
computed separately for each launch period, because old phones are much harder to price
than new ones (notebooks/3.0-aa-error-analysis.ipynb). This is conformal prediction with one
calibration group per period ("Mondrian" conformal prediction).

    price_range = PriceRange("Gradient boosting", columns, params).fit(train_df)
    price_range.predict(df)   # -> price, low, high (euros), launch_period, factor
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import clone

from priced_right import evaluate, features, pipelines

LEVEL = 0.8
PERIOD_BINS = [0, 2016, 2019, 2022, 9999]
PERIOD_LABELS = ["2016 or earlier", "2017-19", "2020-22", "2023 or later"]


def launch_period(release_year: pd.Series) -> pd.Series:
    return pd.cut(release_year, PERIOD_BINS, labels=PERIOD_LABELS).astype(str)


def conformal_quantile(errors: np.ndarray, level: float = LEVEL) -> float:
    """The ceil((n + 1) * level)-th smallest error: the finite-sample-corrected quantile that
    makes a new, similar error fall below it with probability of at least `level`."""
    errors = np.sort(np.asarray(errors, dtype=float))
    rank = int(np.ceil((len(errors) + 1) * level))
    return float(errors[min(rank, len(errors)) - 1])


class PriceRange:
    """The final model plus per-launch-period range widths, fitted on one dataset."""

    def __init__(self, name: str, columns: list[str], params: dict, level: float = LEVEL):
        self.name, self.columns, self.params, self.level = name, list(columns), dict(params), level

    def fit(self, df: pd.DataFrame) -> PriceRange:
        X, y, groups = features.build(df), features.target(df), df["relisting_group"]
        model = pipelines.build(self.name, self.columns, **self.params)
        # Held-out errors: each listing predicted by a model trained on the other folds
        errors = np.abs(y - evaluate.out_of_fold_predictions(model, X, y, groups))
        periods = launch_period(df["release_year"])
        self.half_widths_ = {p: conformal_quantile(errors[(periods == p).to_numpy()], self.level)
                             for p in PERIOD_LABELS if (periods == p).any()}
        self.calibration_sizes_ = periods.value_counts().to_dict()
        self.model_ = clone(model).fit(X, y)
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Expected price and range in euros. `factor`: the range is price / factor to price x factor."""
        log_price = self.model_.predict(features.build(df))
        periods = launch_period(df["release_year"])
        half = periods.map(self.half_widths_).to_numpy(dtype=float)
        return pd.DataFrame({
            "price": features.to_price(log_price),
            "low": features.to_price(log_price - half),
            "high": features.to_price(log_price + half),
            "launch_period": periods.to_numpy(),
            "factor": np.exp(half),
        }, index=df.index)
