# Data Dictionary: iPhone Listings (Tori.fi)

Scope: for-sale iPhone listings in Tori's phone category (`Matkapuhelimet`, brand Apple). We collect only the fields the model and the fairness audit need. Everything else Tori exposes is dropped when the record is built (`priced_right/tori.py`), before anything is written to disk.

Coverage figures come from experiment 01 (2026-09-17: 129 search results, 10 listing pages), see [runs/exp01_feasibility.md](runs/exp01_feasibility.md).

## Target

| Field | Type | Source | Coverage | Notes |
|---|---|---|---|---|
| `price_eur` | int | search results | 100% | **Asking** price, not sale price. Clean in preprocessing: 0 € swap ads ("Vaihdetaan"), accessory listings, placeholder prices. Sample median 250 €, IQR 169–599 €. |

## Features

| Field | Type | Source | Coverage | Used for (canvas) |
|---|---|---|---|---|
| `title` | text | search results | 100% | TF-IDF; parse the exact model ("15 Pro Max"), storage, colour, battery %; flag accessories and spare parts |
| `description` | text | listing page | 100% | TF-IDF, description length, keyword flags (battery health, warranty *takuu*, receipt *kuitti*, box *pakkaus/laatikko*, damage *rikki/halkeama/naarmu*). Phone numbers and emails are replaced with `[phone]`/`[email]` at collection time. |
| `condition` | category | listing page | 100% | 5 levels: Uusi, Kuin uusi, Hyvä, Kohtalainen, Vaatii korjausta. Keep missing as its own category. |
| `model_group` | category | listing page | 100% | Tori's 8 coarse buckets, e.g. `iPhone 15/Plus/Pro/Max`. The exact model comes from the title. |
| `memory` | category | search results | 93% | 16 GB – 1 TB, plus `Muu` (other); missing stays its own category |
| `seller_type` | category | search results | 100% | `private` or `retailer`. **Retailers were 40% of the sample** and price like shops; model and evaluate this group separately. |
| `shipping_available` | bool | search results | 100% | Seller offers shipping (ToriDiili). Candidate feature. |
| `published_at` | datetime (UTC) | search results | 100% | Listing age = `collected_at − published_at`. Tori resets this when a listing is renewed. |
| `municipality` | category | search results | 100% | Location feature; fallback when `region` is missing |
| `region` | category | listing page | 100% | Region (*maakunta*), e.g. Uusimaa. Regional error/bias audit. |

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

`FORBIDDEN_KEYS` in `tori.py` lists these, and experiment 01 fails if any of them reaches a stored record.
