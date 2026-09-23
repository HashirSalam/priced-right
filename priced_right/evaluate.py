"""Score every model the same way: grouped 5-fold cross-validation on log price.

GroupKFold keeps all copies of an ad (same `relisting_group`) on one side of each
split, so a model is never tested on an ad it saw in training. Models are fitted
on log1p(price) and scored on the back-transformed prices.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.model_selection import GroupKFold

from priced_right.preprocess import PROCESSED_DIR

N_SPLITS = 5
SEED = 42


def load_clean() -> pd.DataFrame:
    return pd.read_csv(PROCESSED_DIR / "iphones_clean.csv", dtype={"listing_id": str})


def target(df: pd.DataFrame) -> np.ndarray:
    return np.log1p(df["price_eur"].to_numpy(dtype=float))


def scores(y_true_log: np.ndarray, y_pred_log: np.ndarray) -> dict:
    """RMSLE, mean absolute error in €, and median absolute percentage error."""
    true, pred = np.expm1(y_true_log), np.expm1(y_pred_log)
    return {
        "rmsle": float(np.sqrt(np.mean((y_pred_log - y_true_log) ** 2))),
        "mae_eur": float(np.mean(np.abs(pred - true))),
        "median_ape": float(np.median(np.abs(pred - true) / true)),
    }


def folds(df: pd.DataFrame, n_splits: int = N_SPLITS, seed: int = SEED) -> list:
    splitter = GroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    return list(splitter.split(df, groups=df["relisting_group"]))


def cross_validate(model, df: pd.DataFrame, n_splits: int = N_SPLITS, seed: int = SEED) -> pd.DataFrame:
    """One row of scores per fold. The model is cloned and refitted on each training split."""
    y = target(df)
    rows = []
    for fold, (train, test) in enumerate(folds(df, n_splits, seed)):
        fitted = clone(model).fit(df.iloc[train], y[train])
        rows.append({"fold": fold, **scores(y[test], fitted.predict(df.iloc[test]))})
    return pd.DataFrame(rows)


def out_of_fold_predictions(model, df: pd.DataFrame, n_splits: int = N_SPLITS, seed: int = SEED) -> np.ndarray:
    """Predicted log price for every row from the fold that held it out (for error analysis by group)."""
    y = target(df)
    pred = np.empty(len(df))
    for train, test in folds(df, n_splits, seed):
        pred[test] = clone(model).fit(df.iloc[train], y[train]).predict(df.iloc[test])
    return pred
