# Model Card: Priced Right? iPhone Asking-Price Model

A short, standard summary of the final model: what it's for, how it was built and tested, and where it shouldn't be trusted. Details: [ml-plan.md](ml-plan.md) (rules), [feature-check.md](feature-check.md), [model-comparison.md](model-comparison.md), [test-results.md](test-results.md), [notebooks/3.0-aa-error-analysis.ipynb](../notebooks/3.0-aa-error-analysis.ipynb).

## 1. Intended use

- **For:** private sellers setting an asking price for a used iPhone on Tori.fi, and buyers judging whether a listing's price is below, in line with, or above comparable listings.
- **Predicts:** the typical **asking** price of comparable listings, with an 80% range. Tori doesn't publish sale prices, so the model knows nothing about what phones actually sell for.
- **Not for:** valuing a phone (insurance, trade-in, disputes), other phone brands or products, bulk or business pricing decisions, or finding underpriced listings to buy from inexperienced sellers and resell.

## 2. Data

- 2,007 for-sale iPhone listings from Tori.fi, collected on 17 Sep 2026 (one snapshot) and cleaned by `priced_right/preprocess.py`. No seller identities, contact details or photos are stored ([data-dictionary.md](data-dictionary.md)).
- Development used 1,602 listings; 405 (20%, grouped so copies of an ad stay together) were held out and used once for the final test. The saved model is retrained on all 2,007.
- Coverage: 51 iPhone models from 2008 to 2026; 78% private sellers, 22% retailers; 46% of listings in Uusimaa.

## 3. Model

- **Gradient boosting** (scikit-learn `HistGradientBoostingRegressor`: 400 rounds of 4-leaf trees, learning rate 0.05), trained on log price.
- **Inputs** (all things a user can give before posting an ad): launch year and product line (both derived from the model name), condition (one column per level), storage (log2 of GB), seller type, and whether damage is mentioned.
- Chosen from five tuned models (linear regression, decision tree, random forest, SVR, gradient boosting) with rules fixed in advance ([ml-plan.md](ml-plan.md), section 6).
- **What drives estimates** (permutation importance): launch year by far, then product line, condition, seller type and storage; damage adds little beyond condition.

## 4. Performance on the held-out test set (405 listings, used once)

| | Model | Baseline: median of the same model and storage |
|:--|:--|:--|
| RMSLE | **0.272** (95% CI 0.242–0.302) | 0.374 |
| Mean absolute error | **46 €** | 58 € |
| Median % error | **14.3%** | 16.5% |
| 80% range coverage | **77%** | |

RMSLE is 27% below the baseline's (95% CI 19–35%). All criteria of the success bar set before modelling were met.

**Price ranges** (retrained on all data): a range is price ÷ factor to price × factor, with the factor per launch period: ×/÷ 1.97 (2016 or earlier), 1.42 (2017–19), 1.36 (2020–22), 1.19 (2023 or later).

## 5. Results by group and known weaknesses

| Group (test set) | Median % error | Bias | Range coverage |
|:--|:--|:--|:--|
| Private sellers (308) | 15% | +1% | 78% |
| Retailers (97) | 14% | −2% | 75% |
| Launched 2023 or later (105) | 7% | −1% | 82% |
| Launched 2016 or earlier (25) | 27% | +2% | 80% |
| Asking under 100 € (82) | 30% | **+28%** | **65%** |

- **Cheap phones (under about 100 €)** are the weak spot: estimates are typically too high and the range misses a third of them.
- **Old phones** get wide ranges on purpose; their prices vary a lot.
- **Regions:** region is not an input. Errors differ between regions, but mostly within what small samples (20–35 test listings) explain; Varsinais-Suomi's range coverage (63%, 35 listings) and Pohjanmaa's bias (−14%, 24 listings) are the largest gaps.
- **Listings the inputs can't describe:** phones sold for parts but marked in good condition, collector pricing for very old phones, and multi-phone lots.
- **No free text:** the ad text is only used in cleaning to extract inputs, so the app works from dropdowns and wording can't move an estimate. Details that only appear in the text are not used.

## 6. Evaluation limitations

- The first look at the data (`notebooks/1.0-eda.ipynb`) and one cleaning rule (dropping prices under 10% of a model's median) used all listings, including the later test set; both are descriptive or data-quality steps and changed no modelling choice.
- Duplicate ads are detected by matching title and description openings, so a reworded repost could fall on both sides of the split.
- Gradient boosting's grid was widened more often than the other models' during tuning ([ml-plan.md](ml-plan.md), change log); random forest and SVR were within about 0.01 RMSLE of it in cross-validation.
- One snapshot of one marketplace: seasonal effects, and how long listings stay up, are not captured.

## 7. Ethical considerations

- Estimates describe what sellers **ask**; a price above the range is *unusual*, not *wrong*. The app must say so and show the disclaimer ([model-handover.md](model-handover.md)).
- Risk of misuse: flagging "below" listings could help resellers target inexperienced sellers. The app compares one listing at a time and offers no search or bulk scoring.
- No personal data is used as input; seller type and region are checked for unequal errors (section 5).

## 8. Maintenance

- **Retrain when prices move:** at least when Apple releases new iPhones (each September), or when a fresh collection's prices differ noticeably from the model's estimates. New models don't exist in `options()` until the model is retrained on data that includes them.
- **How:** collect (`python -m priced_right.collect_iphones`), clean (`python -m priced_right.preprocess`), then retrain the saved model (`python -m priced_right.final_model`). A full re-evaluation needs a new test set.
- **Check drift** on each new collection: the share of listings inside their 80% range should stay near 80%; a clear drop means the model is out of date.
