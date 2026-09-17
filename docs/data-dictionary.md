# Data Dictionary: iPhone Listings (Tori.fi)

Scope: for-sale iPhone listings in Tori's phone category (`Matkapuhelimet`, brand Apple). We collect only the fields the model and the fairness audit need. Everything else Tori exposes is dropped when the record is built (`priced_right/tori.py`), before anything is written to disk.

Coverage figures come from the full collection run on 2026-09-17: 2,178 listings, see [runs/iphones_2026-09-17T110158Z.md](runs/iphones_2026-09-17T110158Z.md).

## Target

| Field | Type | Source | Coverage | Notes |
|---|---|---|---|---|
| `price_eur` | int | search results | 100% | **Asking** price, not sale price. Clean in preprocessing: 0 € swap ads ("Vaihdetaan"), accessory listings, placeholder prices. Median 230 €, IQR 105–430 €, range 0–2,299 €; 8 listings at 0 €, and 83 titles look like accessories. Train on `log1p(price)` and report RMSLE, the standard for price prediction (e.g. the Mercari price challenge), alongside MAE in € and median % error. |

## Features

| Field | Type | Source | Coverage | Used for (canvas) |
|---|---|---|---|---|
| `title` | text | search results | 100% | TF-IDF; parse the exact model ("15 Pro Max"), release year, storage, colour, battery %; flag accessories and spare parts. Contact details scrubbed like descriptions. |
| `description` | text | listing page | 100% | TF-IDF, description length, keyword flags (battery health, warranty *takuu*, receipt *kuitti*, box *pakkaus/laatikko*, damage *rikki/halkeama/naarmu*). Contact details are replaced with `[url]` (personal pages, social profiles), `[email]`, `[phone]` or `[number]` at collection time (154 descriptions, 7%). Median length 268 characters. |
| `condition` | category | listing page | 96% | 5 levels: Uusi, Kuin uusi, Hyvä, Kohtalainen, Vaatii korjausta. Keep missing as its own category. |
| `model_group` | category | listing page | 78% | Tori's 8 coarse buckets, e.g. `iPhone 15/Plus/Pro/Max`. 22% of sellers leave it empty, so parse the exact model from the title. 3 listings have a Galaxy group: drop the 1 real Samsung phone and relabel the 2 mis-tagged iPhones from their titles. |
| `memory` | category | search results | 88% | 16 GB – 1 TB, plus `Muu` (other); missing stays its own category |
| `seller_type` | category | search results | 100% | `private` or `retailer`. **Retailers are 20% of listings** (40% in the first small sample), with a median of 340 € vs. 200 € for private sellers; model and evaluate this group separately. |
| `shipping_available` | bool | search results | 100% | Seller offers shipping (ToriDiili). Candidate feature. |
| `published_at` | datetime (UTC) | search results | 100% | Listing age = `collected_at − published_at`. Tori resets this when a listing is renewed. |
| `municipality` | category | search results | 100% | Location feature; fallback when `region` is missing |
| `region` | category | listing page | 100% | Region (*maakunta*), e.g. Uusimaa. Regional error/bias audit. Uusimaa is 47% of listings; Kainuu and Keski-Pohjanmaa have under 10 each. |

## Derived in preprocessing

Planned, not collected: to be computed from the fields above in `priced_right/`, so the notebooks and the app share the same logic.

| Feature | From | Why |
|---|---|---|
| `exact_model` | `title`, `description`, `model_group` | "iPhone 15 Pro Max" instead of the coarse bucket |
| `release_year` | `exact_model` | Device age drives used-phone prices more than listing age |
| `battery_health_pct` | `title`, `description` | Common in iPhone ads ("akun kunto 91%") and price-relevant |
| `mentions_warranty`, `mentions_receipt`, `mentions_box` | `description` | *takuu*, *kuitti*, *pakkaus/laatikko* |
| `mentions_damage` | `title`, `description` | *rikki*, *halkeama*, *naarmu* |
| `is_accessory` | `title`, `price_eur` | Filter out cases, screen protectors and spare parts |
| `listing_age_days` | `published_at`, `collected_at` | 45 listings are older than 180 days |
| `relisting_group` | normalized `title` + `description` + `municipality` | Grouped k-fold keeps relistings on one side of each split |

## Keys and metadata

| Field | Type | Notes |
|---|---|---|
| `listing_id` | string | Joins search and listing-page records; deduplication; basis for relisting groups. Do not publish: it leads back to the live listing. |
| `collected_at` | datetime (UTC) | Run timestamp; listing age and dataset versioning |

Relisting group IDs are derived in preprocessing (normalized title + description + municipality), so no extra field is collected for them.

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
