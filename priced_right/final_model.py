"""The final model, retrained on all listings, and the interface the app uses (lifecycle step 29).

    python -m priced_right.final_model    # retrain on all 2,007 listings -> models/final_model.joblib

The test score is already recorded (docs/test-results.md), so the chosen model (models/tuned.json)
is retrained on training + test data with the same inputs and settings, and its price ranges are
recomputed from all the data. Nothing is re-tuned.

The app only needs two functions (docs/model-handover.md):

    from priced_right.final_model import options, predict
    options()      # valid values for the app's dropdowns
    predict(exact_model="iPhone 13", storage_gb=128, condition="Hyvä", seller_type="private",
            mentions_damage=False, asking_price=250)
"""
from __future__ import annotations

import json
import math
from functools import lru_cache

import joblib
import pandas as pd
import sklearn

from priced_right.features import CONDITION_ORDER
from priced_right.models import MODELS_DIR, TUNED_PATH
from priced_right.preprocess import REPO_ROOT, load_clean, model_info
from priced_right.ranges import LEVEL, PriceRange

FINAL_MODEL_PATH = MODELS_DIR / "final_model.joblib"

CONDITION_ENGLISH = {"Vaatii korjausta": "needs repair", "Kohtalainen": "fair", "Hyvä": "good",
                     "Kuin uusi": "like new", "Uusi": "new"}
SELLER_TYPES = ["private", "retailer"]
# Every size preprocessing accepts (preprocess._STORAGE_GB), so any phone in the training data can be priced
STORAGE_SIZES_GB = [8, 16, 32, 64, 128, 256, 512, 1024, 2048]
DISCLAIMER = ("Estimates are based on asking prices of similar iPhone listings on Tori.fi, "
              "not on what phones actually sold for.")


# ---------------------------------------------------------------- retraining

def train_final() -> dict:
    """Retrain the chosen model and its price ranges on every cleaned listing; return the saved bundle."""
    tuned = json.loads(TUNED_PATH.read_text(encoding="utf-8"))
    name = tuned["final_model"]
    spec = tuned["models"][name]
    data = load_clean()
    price_range = PriceRange(name, spec["columns"], spec["params"]).fit(data)
    models = (data.drop_duplicates("exact_model").sort_values(["release_year", "exact_model"])["exact_model"].tolist())
    return {
        "price_range": price_range,
        "model": name,
        "inputs": spec["columns"],
        "settings": spec["params"],
        "n_listings": len(data),
        "data_collected_at": str(data["collected_at"].iloc[0]),
        "sklearn_version": sklearn.__version__,
        "range_factors": {p: math.exp(h) for p, h in price_range.half_widths_.items()},
        "exact_models": models,
    }


@lru_cache(maxsize=1)
def load() -> dict:
    """The saved bundle (loaded once per process)."""
    if not FINAL_MODEL_PATH.exists():
        raise FileNotFoundError(f"{FINAL_MODEL_PATH.relative_to(REPO_ROOT)} is missing: "
                                "run `python -m priced_right.final_model`")
    return joblib.load(FINAL_MODEL_PATH)


# ---------------------------------------------------------------- interface for the app

def options() -> dict:
    """Valid values for the app's inputs. Conditions and seller types map Tori's value to an English label."""
    return {
        "exact_model": load()["exact_models"],
        "storage_gb": STORAGE_SIZES_GB,
        "condition": dict(CONDITION_ENGLISH),
        "seller_type": SELLER_TYPES,
    }


def predict(exact_model: str, storage_gb: int | None = None, condition: str | None = None,
            seller_type: str = "private", mentions_damage: bool = False,
            asking_price: float | None = None) -> dict:
    """Expected asking price and 80% range; with `asking_price`, also how it compares (buyer mode).

    - exact_model: one of options()["exact_model"], e.g. "iPhone 13 Pro"
    - storage_gb: e.g. 128; None if unknown
    - condition: Tori's level, e.g. "Hyvä" (see options()["condition"]); None if not given
    - seller_type: "private" or "retailer"
    - mentions_damage: True if the phone has cracks or other damage
    - asking_price: a listing's price in euros (buyer mode); None in seller mode

    Returns euros rounded to whole numbers. `label` is "below", "in line" or "above": outside or
    inside the 80% range of comparable listings. Raises ValueError for invalid input.
    """
    bundle = load()
    if exact_model not in bundle["exact_models"]:
        raise ValueError(f"unknown model {exact_model!r}; choose one of options()['exact_model']")
    if storage_gb is not None and storage_gb not in STORAGE_SIZES_GB:
        raise ValueError(f"storage_gb must be one of {STORAGE_SIZES_GB} or None")
    if condition is not None and condition not in CONDITION_ORDER:
        raise ValueError(f"condition must be one of {CONDITION_ORDER} or None")
    if seller_type not in SELLER_TYPES:
        raise ValueError(f"seller_type must be one of {SELLER_TYPES}")
    if asking_price is not None and not asking_price > 0:
        raise ValueError("asking_price must be a positive number of euros")

    listing = pd.DataFrame([{
        "exact_model": exact_model,
        "release_year": model_info(exact_model)[0],
        "storage_gb": storage_gb,
        "condition": condition,
        "seller_type": seller_type,
        "mentions_damage": bool(mentions_damage),
        # Not used by the final model (dropped in the feature check); filled so the inputs can be built
        "battery_pct": None, "region": None, "mentions_warranty": False, "mentions_box": False,
        "mentions_receipt": False, "shipping_available": False,
    }])
    for column in ("storage_gb", "battery_pct"):
        listing[column] = listing[column].astype(float)
    row = bundle["price_range"].predict(listing).iloc[0]

    result = {
        "price": round(float(row["price"])),
        "low": round(float(row["low"])),
        "high": round(float(row["high"])),
        "range_level": LEVEL,
        "launch_period": row["launch_period"],
        "disclaimer": DISCLAIMER,
    }
    if asking_price is not None:
        result["asking_price"] = asking_price
        result["difference"] = round(asking_price / float(row["price"]) - 1, 3)
        result["label"] = ("below" if asking_price < row["low"] else "above" if asking_price > row["high"] else "in line")
    return result


# ---------------------------------------------------------------- command line

def main() -> None:
    bundle = train_final()
    MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump(bundle, FINAL_MODEL_PATH, compress=3)
    load.cache_clear()
    print(f"{bundle['model']} retrained on {bundle['n_listings']} listings (scikit-learn {bundle['sklearn_version']})")
    print("80% range factors: " + ", ".join(f"{p} ×/÷ {f:.2f}" for p, f in bundle["range_factors"].items()))
    example = predict("iPhone 13", 128, "Hyvä", "private", False, asking_price=250)
    print(f"example, iPhone 13 128 GB, good, private, asking 250 €: {example['price']} € "
          f"(range {example['low']}–{example['high']} €) -> {example['label']}")
    print(f"wrote {FINAL_MODEL_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
