# Machine Learning Plan

What the modelling part of the project predicts, how it is judged, and what it may use. Written **before** the training-set EDA and any modelling, so results can't shape the rules they are judged by (steps 1–4 of the data science lifecycle). Changes after this point are logged at the end with a date and a reason.

## 1. Objective

Give sellers an expected asking price for a used iPhone, and tell buyers whether a listing's price is below, in line with, or above comparable listings. Users are private people on Tori, so predictions must be explainable in plain words.

## 2. Task and target

- **Task:** supervised regression.
- **Target:** `price_eur`, the **asking** price on Tori. Tori never shows sale prices, so every result is about what sellers ask.
- **Unit of analysis:** one listing. Copies of the same ad (`relisting_group`) are always kept together when splitting.

Whether to train on a transformed target (e.g. log price) is decided in the EDA (step 15), not assumed here.

## 3. Metrics and success criteria

| Metric | Role | Why |
|---|---|---|
| **RMSLE** | Primary: model selection | Error on the log scale, i.e. relative error. Prices run from 6 € to 2,299 €; a 50 € miss matters more on a 60 € phone than on a 1,000 € one |
| **MAE (€)** | Reported | The number users understand: "typically off by X €" |
| **Median % error** | Reported | Typical relative miss, robust to a few extreme listings |
| **Interval coverage** | For the price ranges | Share of true prices inside the stated range; should match the stated level (e.g. 80%) |

**Baseline to beat:** median asking price of the same model and storage (falling back to the same model). This is what a careful user could do by hand on Tori.

**Success bar (proposed, to be agreed by the group before modelling):**

1. The final model's **test-set RMSLE is at least 10% lower** than the baseline's test-set RMSLE.
2. Its **test-set MAE is lower** than the baseline's.
3. Its 80% price ranges cover **75–85%** of test listings, overall and for each seller type.

If the bar is not met, that is reported as a finding, not hidden.

## 4. Constraints

### Inputs must be available when a user asks for a price

The app asks the user for a phone's details **before** it is listed. Only information a user can give at that moment may be a model input.

| Candidate input | Allowed? | How the user gives it |
|---|---|---|
| `exact_model` and what follows from it (`release_year`, product line) | Yes | Dropdown |
| `storage_gb` | Yes | Dropdown |
| `condition` | Yes | Dropdown (Tori's 5 levels) |
| `battery_pct` | Yes, optional | Number, may be left empty |
| `seller_type` | Yes | Private / retailer |
| `region` | Yes | Dropdown |
| `mentions_damage`, `mentions_warranty`, `mentions_box`, `mentions_receipt` | Yes | Checkboxes ("has damage", "warranty left", …) |
| `shipping_available` | Yes | Checkbox |
| `listing_age_days`, `published_at` | **No** | Always 0 for a new ad; older ads are partly the ones priced too high to sell |
| `title`, `description` (raw text) | **No** | Used only in preprocessing to extract the features above; free-text inputs would let wording move the price |
| `model_group` | **No** | Follows from `exact_model` |
| `municipality` | **No** | 159 values for 2,007 listings; `region` covers location |

Which allowed inputs the models actually use is decided by the feature check (step 22), on the training set.

### Evaluation

- A **test set of 20%**, grouped by `relisting_group`, is set aside before the EDA (step 9) and used **once**, for the final model.
- All decisions (EDA findings, features, tuning, model choice) use the training set only, with 5-fold `GroupKFold`.
- All preprocessing that learns from data (imputation, scaling, encoding) sits inside scikit-learn pipelines.

### Fairness and privacy

- Error and interval coverage are checked by **region** and **seller type**.
- No personal data is used; the collection rules in [data-collection-notes.md](data-collection-notes.md) apply.

## 5. Deviations from the project canvas

| Canvas | Now | Why |
|---|---|---|
| Phones and furniture | iPhones only | See README, "Scope" |
| TF-IDF on title and description as inputs | Text only used to extract features | App inputs must be structured (section 4) |
| Listing age as an input | Not an input | Not available for a new ad (section 4) |
| Median baseline, Ridge, Random Forest | Median baseline, linear regression, decision tree, random forest, SVR, gradient boosting | Wider comparison of model families, all tuned the same way |

## Change log

- 27 Sep: plan written.
