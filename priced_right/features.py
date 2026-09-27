"""Target and model inputs (lifecycle steps 15-18), following the decisions in notebooks/2.0-aa-eda.ipynb.

- Target: models are trained on log1p(price) and predictions converted back with expm1 (EDA section 2).
- Inputs: only what a user can give the app before posting an ad (docs/ml-plan.md, section 4).
  `build()` returns every candidate input; the feature check (step 22) decides which ones each model uses.

Nothing here is learned from the data: no medians, no scaling. Filling missing values, scaling and
encoding happen inside each model's pipeline (priced_right/pipelines.py), fitted on training data only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- target (step 15)


def target(df: pd.DataFrame) -> np.ndarray:
    """log1p(price): prices are right-skewed (skewness 1.57 -> -0.46) and inputs move them by a percentage."""
    return np.log1p(df["price_eur"].to_numpy(dtype=float))


def to_price(log_price: np.ndarray) -> np.ndarray:
    """Model output back to euros. On the log scale this is a typical (median-like) price, not a mean."""
    return np.expm1(log_price)


# ---------------------------------------------------------------- inputs (steps 16-18)

# Tori's condition levels, worst to best. EDA 4.3: ordered, but unevenly spaced.
CONDITION_ORDER = ["Vaatii korjausta", "Kohtalainen", "Hyvä", "Kuin uusi", "Uusi"]

# Battery bands (EDA 4.5): the drop is below 80%, the premium at 90-100%.
# "not mentioned" is its own band (EDA 6): those ads price like typical ones.
BATTERY_BINS = [0, 79, 89, 100]
BATTERY_LABELS = ["under 80%", "80-89%", "90-100%"]
BATTERY_UNKNOWN = "not mentioned"

# How each candidate input is encoded in the pipelines
CATEGORICAL = {"exact_model", "tier", "condition_level", "battery_band", "seller_type", "region"}
NUMERIC = {"release_year", "storage_log2", "condition_rank"}  # may be missing: filled inside the pipeline
FLAGS = {"mentions_damage", "mentions_warranty", "mentions_box", "mentions_receipt", "shipping_available"}

# Two alternative descriptions of the phone model (EDA 4.1, 5). A model gets one of them, never both:
# release_year and tier are fully determined by exact_model.
MODEL_AS_NAME = ["exact_model"]
MODEL_AS_YEAR_AND_TIER = ["release_year", "tier"]

# Two alternative encodings of condition (EDA 4.3): a rank keeps the order; one column per level
# lets a linear model learn the uneven steps.
CONDITION_AS_RANK = ["condition_rank"]
CONDITION_AS_LEVELS = ["condition_level"]

# The other candidate inputs, in groups the feature check can leave out one at a time
GROUPS = {
    "storage": ["storage_log2"],
    "seller type": ["seller_type"],
    "damage mentioned": ["mentions_damage"],
    "battery": ["battery_band"],
    "region": ["region"],
    "warranty mentioned": ["mentions_warranty"],
    "box mentioned": ["mentions_box"],
    "receipt mentioned": ["mentions_receipt"],
    "shipping offered": ["shipping_available"],
}


def tier(model: str) -> str:
    """Product line of a model name from preprocess.parse_model.

    X and XS were the premium phones of their year, so they count as Pro, and the XS Max as Pro Max.
    """
    if model.startswith("iPhone SE"):
        return "SE"
    if model == "iPhone Air":
        return "Air"
    if model.endswith("Pro Max") or model == "iPhone XS Max":
        return "Pro Max"
    if model.endswith("Pro") or model in ("iPhone X", "iPhone XS"):
        return "Pro"
    for line in ("Plus", "Mini"):
        if model.endswith(line):
            return line
    number = model.split()[1]
    if number.endswith("e") and number[:-1].isdigit():
        return "e"  # iPhone 16e, 17e
    return "base"


def battery_band(pct: pd.Series) -> pd.Series:
    bands = pd.cut(pct, bins=BATTERY_BINS, labels=BATTERY_LABELS).astype(object)
    return bands.where(pct.notna(), BATTERY_UNKNOWN)


def build(df: pd.DataFrame) -> pd.DataFrame:
    """Every candidate model input for each listing, from the cleaned data (same row order and index)."""
    rank = {level: i for i, level in enumerate(CONDITION_ORDER)}
    return pd.DataFrame({
        "exact_model": df["exact_model"].astype(object),
        "release_year": df["release_year"].astype(float),
        "tier": df["exact_model"].map(tier).astype(object),
        "storage_log2": np.log2(df["storage_gb"].astype(float)),  # 64 -> 6, 128 -> 7: each doubling one step
        "condition_rank": df["condition"].map(rank).astype(float),  # 0 needs repair ... 4 new; missing stays NaN
        "condition_level": df["condition"].astype(object).where(df["condition"].notna(), "missing"),
        "battery_band": battery_band(df["battery_pct"].astype(float)),
        "seller_type": df["seller_type"].astype(object),
        "region": df["region"].astype(object),
        **{flag: df[flag].astype(float) for flag in sorted(FLAGS)},
    }, index=df.index)
