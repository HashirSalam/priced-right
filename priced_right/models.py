"""Baseline and first learned model, compared with grouped cross-validation.

    uv run python -m priced_right.models    # writes docs/results.md

Both models take the cleaned DataFrame and predict log1p(price).
"""
from __future__ import annotations

import json
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from priced_right import evaluate
from priced_right.preprocess import PROCESSED_DIR, REPO_ROOT, strip_prices

CATEGORICAL = ["exact_model", "model_group", "storage_gb", "condition", "seller_type", "region"]
# release_year is left out: it follows from exact_model, and the feature check showed no loss without it (24 Sep)
NUMERIC = ["battery_pct", "listing_age_days"]
FLAGS = ["mentions_warranty", "mentions_receipt", "mentions_box", "mentions_damage", "shipping_available"]
RESULTS_PATH = REPO_ROOT / "docs" / "results.md"


class MedianBaseline(RegressorMixin, BaseEstimator):
    """Median log price of the most specific seen group, e.g. (model, storage), then model, then overall."""

    def __init__(self, levels: Sequence[Sequence[str]] = (("exact_model", "storage_gb"), ("exact_model",))):
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


def _text_for_tfidf(text: str) -> str:
    """Lowercase and remove prices: 10% of ads repeat their own price in the text."""
    return strip_prices(text).lower()


def _as_category(X):
    return X.astype("string").fillna("missing")


def _as_float(X):
    return X.astype(float)


def _tfidf() -> TfidfVectorizer:
    return TfidfVectorizer(preprocessor=_text_for_tfidf, ngram_range=(1, 2), min_df=2, sublinear_tf=True)


def ridge_model(alpha: float = 1.0, categorical: Sequence[str] = CATEGORICAL, numeric: Sequence[str] = NUMERIC,
                flags: Sequence[str] = FLAGS, text: bool = True) -> Pipeline:
    """TF-IDF on title and description (prices removed) plus one-hot and scaled fields, then Ridge regression.

    The column arguments let the feature check (ablation) leave one group out at a time.
    """
    parts = [("title", _tfidf(), "title"), ("description", _tfidf(), "description")] if text else []
    if categorical:
        parts.append(("categorical", make_pipeline(FunctionTransformer(_as_category), OneHotEncoder(handle_unknown="ignore")), list(categorical)))
    if numeric:
        parts.append(("numeric", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()), list(numeric)))
    if flags:
        parts.append(("flags", FunctionTransformer(_as_float), list(flags)))
    return make_pipeline(ColumnTransformer(parts), Ridge(alpha=alpha))


def _without(columns: Sequence[str], *removed: str) -> list:
    return [c for c in columns if c not in removed]


MENTIONS = ["mentions_warranty", "mentions_receipt", "mentions_box", "mentions_damage"]
# Feature check: Ridge re-scored with one feature group left out. Worse without it = the group helps.
ABLATIONS = {
    "text (title + description)": dict(text=False),
    "exact_model": dict(categorical=_without(CATEGORICAL, "exact_model")),
    "storage_gb": dict(categorical=_without(CATEGORICAL, "storage_gb")),
    "condition": dict(categorical=_without(CATEGORICAL, "condition")),
    "seller_type": dict(categorical=_without(CATEGORICAL, "seller_type")),
    "region": dict(categorical=_without(CATEGORICAL, "region")),
    "model_group": dict(categorical=_without(CATEGORICAL, "model_group")),
    "battery_pct": dict(numeric=_without(NUMERIC, "battery_pct")),
    "listing_age_days": dict(numeric=_without(NUMERIC, "listing_age_days")),
    "the 4 mention flags": dict(flags=_without(FLAGS, *MENTIONS)),
    "shipping_available": dict(flags=_without(FLAGS, "shipping_available")),
}


def ablation(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-validated Ridge scores with each feature group removed, compared with all features."""
    full = evaluate.cross_validate(ridge_model(), df)
    rows = [{"removed": "nothing (all features)", "rmsle": full.rmsle.mean(), "mae_eur": full.mae_eur.mean(), "change": 0.0}]
    for name, kwargs in ABLATIONS.items():
        folds = evaluate.cross_validate(ridge_model(**kwargs), df)
        rows.append({"removed": name, "rmsle": folds.rmsle.mean(), "mae_eur": folds.mae_eur.mean(),
                     "change": folds.rmsle.mean() - full.rmsle.mean()})
    return pd.DataFrame(rows)


CANDIDATES = {
    "Overall median": MedianBaseline(levels=()),
    "Median by model + storage": MedianBaseline(),
    "Ridge (text + fields)": ridge_model(),
}


def main() -> None:
    df = evaluate.load_clean()
    rows = []
    for name, model in CANDIDATES.items():
        folds = evaluate.cross_validate(model, df)
        rows.append({"model": name, **{f"{m}_{stat}": getattr(folds[m], stat)() for m in ("rmsle", "mae_eur", "median_ape") for stat in ("mean", "std")}})
        print(f"{name:28} RMSLE {folds.rmsle.mean():.3f} ± {folds.rmsle.std():.3f} | MAE {folds.mae_eur.mean():.0f} € | median error {folds.median_ape.mean():.0%}")
    features = ablation(df)
    for r in features.itertuples():
        print(f"  without {r.removed:28} RMSLE {r.rmsle:.3f} ({r.change:+.3f})")
    RESULTS_PATH.write_text(render_results(pd.DataFrame(rows), json.loads((PROCESSED_DIR / "cleaning_log.json").read_text()), len(df), features))
    print(f"wrote {RESULTS_PATH.relative_to(REPO_ROOT)}")


def render_results(results: pd.DataFrame, cleaning: dict, n_rows: int, features: pd.DataFrame) -> str:
    lines = [
        "# Results",
        "",
        "Generated by `uv run python -m priced_right.models`; do not edit by hand.",
        "",
        "## Data",
        "",
        f"Source run `{cleaning['source_run']}`, cleaned by `priced_right/preprocess.py`:",
        "",
        "| Step | Removed | Rows left |",
        "|---|---|---|",
        *[f"| {s['step']} | {s['removed']} | {s['rows']} |" for s in cleaning["steps"]],
        "",
        f"{cleaning['distinct_models']} distinct models. Coverage: storage {cleaning['coverage']['storage_gb']:.0%}, "
        f"battery % {cleaning['coverage']['battery_pct']:.0%}, condition {cleaning['coverage']['condition']:.0%}.",
        "",
        "## Models",
        "",
        f"{evaluate.N_SPLITS}-fold GroupKFold on {n_rows} listings (copies of an ad stay in one fold), seed {evaluate.SEED}. "
        "Trained on log1p(price); mean ± std over folds.",
        "",
        "| Model | RMSLE | MAE (€) | Median % error |",
        "|---|---|---|---|",
        *[f"| {r.model} | {r.rmsle_mean:.3f} ± {r.rmsle_std:.3f} | {r.mae_eur_mean:.0f} ± {r.mae_eur_std:.0f} | "
          f"{r.median_ape_mean:.1%} ± {r.median_ape_std:.1%} |" for r in results.itertuples()],
        "",
        "## Which features earn their place",
        "",
        "Ridge re-scored with one feature group left out (same folds). A positive change means the model is worse "
        "without that group, so the group helps; around ±0.002 is noise.",
        "",
        "| Left out | RMSLE | Change | MAE (€) |",
        "|---|---|---|---|",
        *[f"| {r.removed} | {r.rmsle:.3f} | {r.change:+.3f} | {r.mae_eur:.1f} |"
          for r in features.sort_values("change", ascending=False).itertuples()],
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
