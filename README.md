# Priced Right?

Estimating expected asking prices for second-hand listings.

Group: Abtaal Aatif, Hashir Salam Awan, Hafiz Javid

Sellers and buyers lack a reliable reference for second-hand asking prices. This project learns an expected asking price from comparable listings (phones and furniture; bicycles as a stretch goal) and tells a user whether a listing is below, in line with, or above it. Estimates reflect asking prices, not sale prices.

Full plan: [docs/project-canvas.md](docs/project-canvas.md)

## Plan at a glance

| Week | Focus | Output |
|---|---|---|
| 1 | Data collection, preprocessing | Raw JSON, tidy versioned CSV |
| 2 | EDA, visualizations | Price by category/condition, variation, keyword associations |
| 3–4 | Modelling | Median baseline vs. Ridge (TF-IDF + tabular) vs. Random Forest, grouped k-fold CV |
| 5 | Fairness, privacy | Regional error audit, misuse discussion |
| — | Deliverable | Flask web app (seller and buyer modes), report, presentation |

**Data source:** Tori.fi only with written permission; otherwise the eBay Browse API within its terms.

## Layout

```
collection/      scrapers, API clients and collection experiments (collection/tori)
data/raw/        raw JSON as collected (not committed)
data/processed/  tidy, versioned CSVs (not committed)
notebooks/       EDA and modelling experiments
src/             preprocessing, features, models (pipeline reused by the app)
app/             Flask web app
reports/         figures, report, presentation
docs/            project canvas, data dictionary, data collection notes
```

## Data collection

Current scope: for-sale iPhone listings.

- [docs/data-dictionary.md](docs/data-dictionary.md): the fields we collect, why, and what we deliberately leave out
- [docs/data-collection-notes.md](docs/data-collection-notes.md): crawler rules, how Tori exposes its data, experiments

Run experiment 01 (small feasibility test, standard library only) from the repo root:

```bash
python3 -m collection.tori.exp01_feasibility
```
