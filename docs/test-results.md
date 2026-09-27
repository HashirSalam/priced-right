# Test-set results

Generated once by `python -m priced_right.final_evaluation`; do not edit by hand.

Final model: **Gradient boosting**, trained on the 1602 training listings and scored once on the 405 held-out test listings. 95% confidence intervals from 2,000 bootstrap resamples of the test set by relisting group. Procedure: [ml-plan.md](ml-plan.md), section 7.

## Scores

| | Final model | Baseline (median by model + storage) |
|:--|:--|:--|
| RMSLE | 0.272 (95% CI 0.242–0.302) | 0.374 (0.331–0.418) |
| MAE | 46 € (42–52 €) | 58 € (51–64 €) |
| Median % error | 14.3% (12.8%–15.6%) | 16.5% |
| 80% price ranges | cover 77% of test listings | |

RMSLE is **27% lower** than the baseline's (95% CI 19%–35%).

## Success bar

| Criterion | Met? |
|:--|:--|
| RMSLE at least 10% below the baseline | yes |
| MAE below the baseline | yes |
| 80% ranges cover 75%-85% overall | yes |
| 80% ranges cover 75%-85% for private sellers | yes |
| 80% ranges cover 75%-85% for retailer sellers | yes |

## Price ranges

80% ranges from held-out training errors, per launch period: a range is price ÷ factor to price × factor.

| Launch period | Factor |
|:--|:--|
| 2016 or earlier | ×/÷ 1.86 |
| 2017-19 | ×/÷ 1.42 |
| 2020-22 | ×/÷ 1.35 |
| 2023 or later | ×/÷ 1.19 |

## Errors and coverage by group (fairness)

Bias: typical over- (+) or under-pricing (−). Range coverage should be near 80%.

| Seller type | Listings | RMSLE | Bias | Median % error | Range coverage |
|:--|:--|:--|:--|:--|:--|
| private | 308 | 0.284 | +1% | 15% | 78% |
| retailer | 97 | 0.230 | -2% | 14% | 75% |

| Region | Listings | RMSLE | Bias | Median % error | Range coverage |
|:--|:--|:--|:--|:--|:--|
| Uusimaa | 189 | 0.234 | +2% | 15% | 79% |
| other (fewer than 20) | 103 | 0.327 | +2% | 13% | 74% |
| Varsinais-Suomi | 35 | 0.351 | -9% | 19% | 63% |
| Pirkanmaa | 33 | 0.231 | +3% | 11% | 88% |
| Pohjanmaa | 24 | 0.248 | -14% | 15% | 83% |
| Pohjois-Pohjanmaa | 21 | 0.224 | -6% | 22% | 76% |

| Launched | Listings | RMSLE | Bias | Median % error | Range coverage |
|:--|:--|:--|:--|:--|:--|
| 2016 or earlier | 25 | 0.529 | +2% | 27% | 80% |
| 2017-19 | 71 | 0.330 | +11% | 23% | 69% |
| 2020-22 | 204 | 0.252 | +0% | 15% | 77% |
| 2023 or later | 105 | 0.149 | -1% | 7% | 82% |

| Asking price (€) | Listings | RMSLE | Bias | Median % error | Range coverage |
|:--|:--|:--|:--|:--|:--|
| 6–100 | 82 | 0.424 | +28% | 30% | 65% |
| 101–190 | 82 | 0.280 | +4% | 18% | 74% |
| 191–314 | 79 | 0.235 | -9% | 13% | 81% |
| 315–500 | 85 | 0.181 | -3% | 11% | 84% |
| 501–1499 | 77 | 0.146 | -4% | 7% | 82% |
