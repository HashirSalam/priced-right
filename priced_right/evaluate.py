"""How every model is scored: the same grouped 5-fold cross-validation on the training set.

GroupKFold keeps all copies of an ad (same `relisting_group`) in one fold, so a model is never
scored on an ad it saw in training. Models predict log1p(price); scores compare prices in euros
and on the log scale (docs/ml-plan.md, section 3).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.model_selection import GroupKFold

from priced_right.features import to_price

N_SPLITS = 5
SEED = 42


def scores(y_true_log: np.ndarray, y_pred_log: np.ndarray) -> dict:
    """RMSLE (error on the log scale), mean absolute error in €, and median absolute percentage error."""
    true, pred = to_price(y_true_log), to_price(y_pred_log)
    return {
        "rmsle": float(np.sqrt(np.mean((y_pred_log - y_true_log) ** 2))),
        "mae_eur": float(np.mean(np.abs(pred - true))),
        "median_ape": float(np.median(np.abs(pred - true) / true)),
    }


def cv_splitter() -> GroupKFold:
    """The folds used for the feature check, tuning and comparison, so all scores are comparable."""
    return GroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)


def cross_validate(model, X: pd.DataFrame, y: np.ndarray, groups: pd.Series) -> pd.DataFrame:
    """One row of scores per fold. The model is cloned and refitted on each training fold."""
    rows = []
    for fold, (train, test) in enumerate(cv_splitter().split(X, groups=groups)):
        fitted = clone(model).fit(X.iloc[train], y[train])
        rows.append({"fold": fold, **scores(y[test], fitted.predict(X.iloc[test]))})
    return pd.DataFrame(rows)


def summarize(folds: pd.DataFrame) -> dict:
    """Mean, standard deviation and standard error (std / sqrt(folds)) of each score."""
    out = {}
    for metric in ("rmsle", "mae_eur", "median_ape"):
        out[f"{metric}_mean"] = float(folds[metric].mean())
        out[f"{metric}_std"] = float(folds[metric].std())
    out["rmsle_se"] = out["rmsle_std"] / np.sqrt(len(folds))
    return out


def out_of_fold_predictions(model, X: pd.DataFrame, y: np.ndarray, groups: pd.Series) -> np.ndarray:
    """Predicted log price for every row, from the fold that held it out (for error analysis)."""
    pred = np.empty(len(X))
    for train, test in cv_splitter().split(X, groups=groups):
        pred[test] = clone(model).fit(X.iloc[train], y[train]).predict(X.iloc[test])
    return pred
