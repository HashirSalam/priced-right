# Mini Project Canvas

**Title (preliminary):** Priced Right? Estimating Expected Asking Prices for Second-Hand Listings
**Group members:** Abtaal Aatif, Hashir Salam Awan, Hafiz Javid
**Workshop #:** 2

## Motivation

Buyers and sellers lack a reliable reference for second-hand asking prices. Sellers risk underpricing or long listing times; buyers must compare many ads. We estimate an expected asking price from comparable listings and show whether a listing is below, in line with, or above it. The estimate is not a final sale price.

## Data collection

Primary: Tori.fi only if written permission is granted. Fallback: eBay Browse API, used within its terms and limits. Collect active listings for phones and furniture; bicycles are a stretch goal. Fields: listing ID, title/description, asking price, category, condition, location, and posting date. Store raw JSON and tidy, versioned CSV with fixed seeds.

## Preprocessing

Remove invalid or placeholder prices; normalize text, currency, units, and brand/model terms; group duplicates and relistings via normalized titles and group IDs; strip personal information; exclude photos; keep missing condition as its own category; review outliers and bulk lots. Engineer TF-IDF, keyword flags, description length, category, condition, region, and listing age. Optionally model log-price. Reuse the fitted pipeline in the app.

## Exploratory data analysis (EDA)

Summarize median and IQR (interquartile range) asking price by category and condition. Inspect distributions, missingness, outliers, regional differences, and variation among comparable items. Compare standardized phones with heterogeneous furniture: do phone listings vary less, and are their prices easier to predict? Explore keyword-price associations.

## Visualizations

Box plots: price by category and condition. Comparable-item price variation across categories. Predicted-vs-actual and residual/deviation plots. Model-comparison bars. Ridge word coefficients and Random Forest feature importance. In the web app, show the expected range and a marker for the user's listing price.

## Learning task (problem definition)

Supervised regression. Target: active-listing asking price, optionally log-transformed, not transaction value. Inputs: title/description text, category, condition, location, listing age, description length, and keyword flags. Learn the expected asking price for a comparable item and compare an entered price with it. A deviation means unusual, not objectively wrong.

## Learning approach (solution implementation)

Compare three pipelines:

1. Median baseline by category/condition
2. Ridge on sparse TF-IDF plus tabular features
3. Random Forest on tabular plus keyword features

Evaluate MAE in euros per category and median absolute percentage error. Use grouped k-fold CV on relisting group IDs where possible; fit preprocessing and tuning inside training folds. Build ranges from held-out errors.

## Communication of results

Required deliverable: Python/Flask web app.

- **Seller mode:** enter item details to receive an expected asking price and estimated range.
- **Buyer mode:** also enter a listing price to see percentage deviation and a plain-language label: below, in line with, or above comparable listings.

State clearly that outputs reflect asking prices, not sale prices or intrinsic value. Support with a report and presentation.

## Data privacy and ethical considerations

Respect platform terms: collect from Tori only with written permission; otherwise use eBay's API within its terms. Avoid claiming a definitive GDPR lawful basis. Remove seller IDs, names, contact details, addresses, and photos; never re-identify anyone. Audit regional error/bias and test location's effect. Present estimates cautiously and discuss misuse, like arbitrage targeting inexperienced sellers.

## Added value

Thousands of listings contain price signals no user can efficiently aggregate. The app converts them into an expected asking price, honest range, and clear comparison. Sellers gain a defensible starting price and may avoid lost value or stalled listings; buyers gain a negotiation target and faster screening. Value comes from improving a decision, not prediction alone.

## Timeline (legend)

| Week | Focus |
|---|---|
| 1 | Data collection / preprocessing |
| 2 | EDA & visualizations |
| 3–4 | Machine / deep learning |
| 5 | Fairness & data privacy |
