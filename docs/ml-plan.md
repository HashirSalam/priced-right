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

## 6. Model selection rules

Fixed before the feature check and tuning were run (steps 22–24). All scores are mean RMSLE over the same 5 grouped folds of the training set.

1. **Representation is chosen per model.** Two inputs have alternative encodings that carry the same information: the phone model (`exact_model`, or `release_year` + `tier`) and condition (`condition_rank`, or `condition_level`). Each model uses the combination with its lowest RMSLE, with all other candidate inputs included. This is the same principle as scaling only where a model needs it.
2. **Which inputs are used is shared.** Each input group is removed one at a time, for every model. A group is **kept if removing it makes RMSLE worse by more than 0.002 for at least one model**; otherwise it is dropped for all models. The phone model and condition are tested like every other group. A final check compares the kept set with all inputs, to confirm the dropped groups don't matter jointly.
3. **Every model is tuned** with a grid search on the same folds. A best setting on the edge of its grid means the grid is widened and the search re-run.
4. **The final model** is chosen with the **one-standard-error rule**: among the models whose RMSLE is within one standard error (fold standard deviation / √5) of the best model's, pick the easiest to explain, in this order: linear regression, decision tree, random forest, gradient boosting, SVR.

## 7. Price ranges and the final evaluation

Fixed after the error analysis ([notebooks/3.0-aa-error-analysis.ipynb](../notebooks/3.0-aa-error-analysis.ipynb)) and **before the test set was opened**.

### Price ranges (step 27)

- **Level:** 80% ranges: about 4 in 5 asking prices should fall inside.
- **Method:** conformal prediction built from held-out errors, **separately for each launch period** (2016 or earlier, 2017–19, 2020–22, 2023–26). For each period, the range half-width on the log scale is the 80% quantile (with the usual finite-sample correction) of the model's out-of-fold absolute errors on the training set. A range is `price ÷ factor` to `price × factor`.
- **Why per period:** the error analysis showed errors for old phones are about three times those for new ones. Checked on the training set (ranges built from four folds' errors, coverage measured on the fifth): one width for all phones covered 80% overall but only 50% of phones from 2016 or earlier and 95% of phones from 2023 on. Per-period widths covered 80–82% in every period, at almost the same average width (×/÷ 1.36 vs 1.34).
- MAPIE's cross-conformal regressor has no per-group option, so the method is implemented directly in `priced_right/ranges.py`.

### Test-set evaluation (step 26)

- The final model is trained on the whole training set and scored **once** on the test set; so is the baseline.
- **Uncertainty:** 95% confidence intervals from 2,000 bootstrap resamples of the test set, drawn by relisting group (seed 42). The improvement over the baseline is bootstrapped on the same resamples.
- **Success bar** (section 3): RMSLE at least 10% lower than the baseline's; lower MAE; 80% ranges covering 75–85% overall and for each seller type.
- **Fairness:** RMSLE, bias and range coverage by seller type, region (regions with at least 20 test listings), launch period and price band.

## Change log

- 27 Sep: plan written.
- 27 Sep: section 6 (model selection rules) added, before the feature check and tuning were run.
- 27 Sep: rule 3 applied during tuning. SVR's grid was widened once; gradient boosting's three times, because its best settings kept moving to smaller trees and more, slower rounds, until the grid reached 2-leaf trees (the smallest possible) and every best setting was inside its grid. Each widening improved its RMSLE by only 0.001–0.003 (0.287 → 0.284), within one standard error, but gradient boosting received more tuning than the other models. The final choice (rule 4) was gradient boosting; random forest (0.293) and SVR (0.292) were just outside one standard error of it (≤ 0.290). Report this as a limitation.
- 27 Sep: error analysis done; no changes to cleaning, features or model. Section 7 (price ranges and final evaluation) added before the test set was opened.
- 27 Sep: test set evaluated once (docs/test-results.md). All success-bar criteria met: RMSLE 0.272 vs 0.374 for the baseline (27% lower, 95% CI 19–35%), MAE 46 € vs 58 €, 80% ranges covering 77% overall (78% private sellers, 75% retailers). Weak spots, as the error analysis predicted: phones under 100 € (65% coverage, priced 28% too high) and small regions.
