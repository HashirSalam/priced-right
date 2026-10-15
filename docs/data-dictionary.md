# Data Dictionary: iPhone Listings (Tori.fi)

Scope: for-sale iPhone listings in Tori's phone category (`Matkapuhelimet`, brand Apple). We collect only the fields the model and the fairness audit need. Everything else Tori exposes is dropped when the record is built (`priced_right/tori.py`), before anything is written to disk.

`title` and `description` are free text written by sellers and stay local (git-ignored): the repository keeps only the features derived from them, in `data/processed/iphones_clean.csv`.

Coverage figures come from the full collection run on 2026-09-17: 2,178 listings, see [runs/iphones_2026-09-17T110158Z.md](runs/iphones_2026-09-17T110158Z.md).

## Target

| Field | Type | Source | Coverage | Notes |
|---|---|---|---|---|
| `price_eur` | int | search results | 100% | **Asking** price, not sale price. Clean in preprocessing: 0 € swap ads ("Vaihdetaan"), accessory listings, placeholder prices. Median 230 €, IQR 105–430 €, range 0–2,299 €; 8 listings at 0 €, and 83 titles look like accessories. Train on `log1p(price)` and report RMSLE, the standard for price prediction (e.g. the Mercari price challenge), alongside MAE in € and median % error. |

## Features

| Field | Type | Source | Coverage | Used for (canvas) |
|---|---|---|---|---|
| `title` | text | search results | 100% | TF-IDF; parse the exact model ("15 Pro Max"), release year, storage, colour, battery %; flag accessories and spare parts. Contact details scrubbed like descriptions. |
| `description` | text | listing page | 100% | TF-IDF, description length, keyword flags (battery health, warranty *takuu*, receipt *kuitti*, box *pakkaus/laatikko*, damage *rikki/halkeama/särö*). Contact details are replaced with `[url]` (personal pages, social profiles), `[email]`, `[phone]` or `[number]` at collection time (154 descriptions, 7%). Median length 268 characters. Prices written in the text ("750 €", "250e", "Hinta: 180"): remove them with `preprocess.strip_prices()` before any text model, since 10% of ads repeat their own asking price. |
| `condition` | category | listing page | 96% | 5 levels: Uusi, Kuin uusi, Hyvä, Kohtalainen, Vaatii korjausta. Keep missing as its own category. |
| `model_group` | category | listing page | 78% | Tori's 8 coarse buckets, e.g. `iPhone 15/Plus/Pro/Max`. 22% of sellers leave it empty, so parse the exact model from the title. 3 listings have a Galaxy group: drop the 1 real Samsung phone and relabel the 2 mis-tagged iPhones from their titles. |
| `memory` | category | search results | 88% | 16 GB – 1 TB, plus `Muu` (other); missing stays its own category |
| `seller_type` | category | search results | 100% | `private` or `retailer`. **Retailers are 20% of listings** (40% in the first small sample), with a median of 340 € vs. 200 € for private sellers; model and evaluate this group separately. |
| `shipping_available` | bool | search results | 100% | Seller offers shipping (ToriDiili). Candidate feature. |
| `published_at` | datetime (UTC) | search results | 100% | Listing age = `collected_at − published_at`. Tori resets this when a listing is renewed. |
| `municipality` | category | search results | 100% | Location feature; fallback when `region` is missing |
| `region` | category | listing page | 100% | Region (*maakunta*), e.g. Uusimaa. Regional error/bias audit. Uusimaa is 47% of listings; Kainuu and Keski-Pohjanmaa have under 10 each. |

## Derived in preprocessing

Computed by `priced_right/preprocess.py` into `data/processed/iphones_clean.csv` (2,007 listings). Coverage is on the cleaned data.

| Feature | From | Coverage | Notes |
|---|---|---|---|
| `exact_model` | `title`, else `description` if it names exactly one model | 100% | e.g. "iPhone 15 Pro Max"; handles "12Pro", "13mini", "Phone 12", "Apple 15 pro max", "iPhone Air"; variants Apple never sold ("XR Max") drop to the base model; "iPhone 16 GB" is storage, not a model. iPhone SE is split into 1st/2nd/3rd gen when the ad says ("SE 2", "3rd gen", "2022", "5G"; not Tori's "(2-3 gen)" label), otherwise plain "iPhone SE". Descriptions naming several models are not used. 51 models. |
| `model_group` | `exact_model` | 100% | Tori's bucket, recomputed from the model: fills the 22% left empty and fixes 2 mis-tagged iPhones. `model_group_filled` marks the 407 changed rows. |
| `release_year` | `exact_model` | 100% | Launch year, e.g. 6s → 2015, 16e → 2025; SE 1st/2nd/3rd gen → 2016/2020/2022, SE of unknown generation → 2020. Follows from `exact_model`, so never used together with it: launch year + product line is one of two candidate descriptions of the phone model (see [Model inputs](#model-inputs)). |
| `storage_gb` | `memory`, then title, then description | 96% | 8 GB – 2 TB; "Gt"/"Tt" are Finnish for GB/TB |
| `battery_pct` | `title` + `description` | 51% | "Akun kunto 89%", "Battery health: 100%"; values 50–100 only |
| `mentions_warranty`, `mentions_receipt`, `mentions_box` | `title` + `description` | 20%, 4%, 12% | *takuu*, *kuitti*, *pakkaus/laatikko*. Negated or ended mentions don't count: "ei takuuta" (no warranty), "takuu päättyi" (warranty ended), "kuitti hukassa" (receipt lost), "ilman laatikkoa" (without box). |
| `mentions_damage` | `title` + `description` | 10% | *rikki*, *halkeama*, *särö*, *lohkeama*, *vaurio*, broken, crack; not "vaurioton"/"halkeamaton" (undamaged). Negations don't count: "ei halkeamia", "halkeamia ei ole", "ei säröjä, lohkeamia, halkeamia" (one "ei" negating a list). About 2 of 197 flags are subtler denials that still count. |
| `listing_age_days` | `published_at`, `collected_at` | 100% | Median 14 days; Tori resets `published_at` when a listing is renewed. Not a model input: a new ad in the app always has age 0 ([ml-plan.md](ml-plan.md), section 4). |
| `relisting_group` | normalized `title` + first 120 characters of `description` | 100% | Same ad posted again, or a shop's template; GroupKFold keeps a group in one fold |

Rows removed during cleaning (0 € and placeholder prices, accessories and spare parts, non-iPhones, multi-phone lots and bundles, no single model, implausibly low prices) are counted in `data/processed/cleaning_log.json`.

## Model inputs

Candidate inputs built by `priced_right/features.py` from the cleaned data, following the EDA ([notebooks/2.0-aa-eda.ipynb](../notebooks/2.0-aa-eda.ipynb)). Only inputs a user can give the app before posting an ad ([ml-plan.md](ml-plan.md), section 4). Which of them each model uses is decided by the feature check on the training set.

**Target:** `log1p(price_eur)`; predictions are converted back with `expm1` (EDA section 2).

| Input | From | Encoding | Missing values |
|---|---|---|---|
| `exact_model` | `exact_model` | category | none |
| `release_year` + `tier` | `exact_model` | number + category (base, Mini, Plus, Pro, Pro Max, e, SE, Air; X and XS count as Pro, XS Max as Pro Max) | none |
| `storage_log2` | `storage_gb` | log2 of GB (64 → 6, 128 → 7): each doubling is one step (EDA 4.2) | training median + was-missing column |
| `condition_rank` | `condition` | 0 needs repair … 4 new (EDA 4.3) | training median + was-missing column |
| `condition_level` | `condition` | category, one column per level | own category "missing" |
| `battery_band` | `battery_pct` | category: under 80%, 80-89%, 90-100% (EDA 4.5) | own category "not mentioned" (EDA 6) |
| `seller_type`, `region` | same | category | none |
| `mentions_*`, `shipping_available` | same | 0/1 | none |

`exact_model` and `release_year` + `tier` are alternatives, never used together; so are `condition_rank` and `condition_level`.

Categories with fewer than 5 training listings share one column, and values never seen in training (e.g. a newly released iPhone) are routed there instead of failing. Filling, scaling and encoding happen inside each model's pipeline (`priced_right/pipelines.py`), fitted on training data only; numbers are scaled only for linear regression and SVR.

## Keys and metadata

| Field | Type | Notes |
|---|---|---|
| `listing_id` | string | Joins search and listing-page records; deduplication; basis for relisting groups. Do not publish: it leads back to the live listing. |
| `collected_at` | datetime (UTC) | Run timestamp; listing age and dataset versioning |

Relisting group IDs are derived in preprocessing (see above), so no extra field is collected for them.

## Available but deliberately not collected

| Tori field | Why not |
|---|---|
| `meta.ownerId` (seller account ID) | Identifies a person. Canvas: remove seller IDs. |
| `organisation_name` (business seller name) | Not needed; `seller_type` is enough |
| Coordinates, postal code, district (e.g. "Kivistö") | Too precise; municipality and region are enough |
| Images, image URLs, image counts | Canvas excludes photos |
| Seller profile, contact, map, report pages | Personal data; also disallowed by robots.txt |
| `meta.edited` (last edited) | `published_at` already covers listing age |
| JSON-LD `itemCondition` | Lossy: a "Kuin uusi" (like new) listing was marked `NewCondition`. Use `condition`. |
| `labels`, `ad_type`, `distance`, search `metadata` | No modelling value |

`FORBIDDEN_KEYS` in `tori.py` lists these, and the collector stops if any of them reaches a stored record.
