# Model Handover: Using the Final Model in the App

Everything the Flask app needs from the model is in two functions in `priced_right/final_model.py`. The app never needs to touch features, pipelines or scikit-learn directly.

What the model is, how well it works and where it's weak: [model-card.md](model-card.md).

## 1. Setup

The trained model is committed as `models/final_model.joblib`. Use the project environment (Python 3.13, `requirements-lock.txt`), because a saved model only loads with the scikit-learn version it was saved with.

If the file is missing, or loading fails after a library update, rebuild it (about 5 seconds):

```bash
python -m priced_right.final_model
```

## 2. `options()`: values for the dropdowns

```python
from priced_right.final_model import options

options()
# {
#   "exact_model": ["iPhone 3", "iPhone 4", ..., "iPhone 17 Pro Max", "iPhone Air", "iPhone 17e"],   # oldest first
#   "storage_gb": [16, 32, 64, 128, 256, 512, 1024],
#   "condition": {"Vaatii korjausta": "needs repair", "Kohtalainen": "fair", "Hyvä": "good",
#                 "Kuin uusi": "like new", "Uusi": "new"},
#   "seller_type": ["private", "retailer"],
# }
```

Build the dropdowns from these lists, so the app only offers values the model knows. For condition, show the English label and send Tori's Finnish value (the key).

## 3. `predict()`: the estimate

```python
from priced_right.final_model import predict

# Seller mode: what should I ask?
predict(exact_model="iPhone 13", storage_gb=128, condition="Hyvä", seller_type="private", mentions_damage=False)
# {"price": 214, "low": 158, "high": 291, "range_level": 0.8, "launch_period": "2020-22", "disclaimer": "..."}

# Buyer mode: is this listing's price fair?
predict(exact_model="iPhone 13", storage_gb=128, condition="Hyvä", seller_type="private", mentions_damage=False,
        asking_price=250)
# {..., "asking_price": 250, "difference": 0.166, "label": "in line"}
```

### Inputs

| Argument | Required | Values | Form field |
|:--|:--|:--|:--|
| `exact_model` | yes | one of `options()["exact_model"]` | dropdown |
| `storage_gb` | no | one of `options()["storage_gb"]`, or `None` if unknown | dropdown with an "I don't know" option |
| `condition` | no | a key of `options()["condition"]`, or `None` | dropdown with English labels |
| `seller_type` | no (default `"private"`) | `"private"` or `"retailer"` | radio buttons |
| `mentions_damage` | no (default `False`) | `True` if the phone has cracks or other damage | checkbox |
| `asking_price` | buyer mode only | a positive number of euros | number field |

Invalid values raise `ValueError` with a message saying what's wrong. Show that message instead of crashing.

### Outputs

| Key | Meaning |
|:--|:--|
| `price` | Expected asking price in euros: a typical price for comparable listings |
| `low`, `high` | The 80% range: about 4 in 5 comparable listings ask a price in this range |
| `launch_period` | Why a range may be wide: ranges are much wider for phones launched in 2016 or earlier |
| `disclaimer` | Text the app must show next to every estimate |
| `difference` | Buyer mode: how far the listing's price is from `price` (0.166 = 16.6% above) |
| `label` | Buyer mode: `"below"`, `"in line"` or `"above"`: whether the price is outside or inside the 80% range |

## 4. Wording the app should use

- Always show the disclaimer: *"Estimates are based on asking prices of similar iPhone listings on Tori.fi, not on what phones actually sold for."*
- Say **"expected asking price"**, never "value" or "worth".
- Show the range, not only the single price.
- Buyer mode: "**above** comparable listings" means *unusual*, not *wrong* or *a scam* (project canvas).
- For phones launched in 2016 or earlier, and for phones under about 100 €, say that estimates are rough: these are where the model is least accurate (model card, section 5).

## 5. Checking it works

```bash
pytest tests/test_final_model.py
```

The tests cover both modes, the labels, optional inputs and the error messages.
