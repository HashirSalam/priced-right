# Data Collection Notes

> The canvas makes Tori.fi collection conditional on written permission, with the eBay Browse API as the fallback. On 2026-09-17 the group ran the full iPhone collection ([collection runs](#collection-runs)). The permission status should be recorded here once known.

## Tori.fi: crawler rules

Rules the collector follows, all implemented in [`priced_right/tori.py`](../priced_right/tori.py):

1. **robots.txt:** only `/recommerce/forsale/search` and `/recommerce/forsale/item/*` are fetched. Tori disallows `/map*`, `/profile*`, `/messages*`, `/contact/*`, `/report/*` and account pages. Python's `urllib.robotparser` ignores `*` wildcards and wrongly allows `/profile*` and `/map*`, so `RobotsRules` implements the matching itself (longest match wins).
2. **One request at a time,** at least 3 s apart plus up to 1 s random jitter (`ToriClient`).
3. **Honest user agent:** `priced-right/0.1 (student data science project; non-commercial)`. Tori serves it normally.
4. **Plain HTTP, no browser.** Pages are rendered on the server with the data embedded as JSON; responses take ~0.3 s.
5. **Data minimization at collection time:** records keep only the fields in [data-dictionary.md](data-dictionary.md). Contact details in titles and descriptions are scrubbed before writing (links to personal pages and social profiles, emails, Finnish phone numbers including WhatsApp links, and any other 9–12 digit number), and forbidden keys (seller ID, coordinates, images, …) fail the run.
6. **Storage:** minimized records go to `data/raw/tori/<run>/`. Descriptions are scrubbed of phone numbers and emails but can still mention names, so the files with ad text (`listings.csv`, `*_records.jsonl`) stay local and git-ignored; the run metadata, failures and log are committed.

## Tori.fi: how the site exposes data

### Search pages

`https://www.tori.fi/recommerce/forsale/search?product_category=2.93.3217.39&brand=631&trade_type=1&sort=PUBLISHED_DESC&page=N`

| Parameter | Value | Meaning |
|---|---|---|
| `product_category` | `2.93.3217.39` | Matkapuhelimet (mobile phones) |
| `brand` | `631` | Apple |
| `trade_type` | `1` | Myydään (for sale); `2` giveaway and `3` wanted are excluded |
| `sort` | `PUBLISHED_DESC` | Newest first, which keeps page order stable. Others: `PRICE_ASC`, `PRICE_DESC`, `RELEVANCE`, `PUBLISHED_ASC`, `CLOSEST` |
| `page` | 1…`metadata.paging.last` | 53 results per page; Tori caps paging at page 50 (~2,650 results per query) |
| `condition` | `1`–`5` | Uusi, Kuin uusi, Hyvä, Kohtalainen, Vaatii korjausta |
| `mobile_model` | see below | iPhone model group |
| `mobile_memory_size` | `1`–`7`, `1318` | 16, 32, 64, 128, 256, 512 GB, `7` Muu (other), `1318` 1 TB |
| `dealer_segment` | `1`, `3` | Yksityinen (private), Yritys (business) |

`mobile_model` values for iPhones: `1` iPhone 2G-11, `2` iPhone SE (2-3 gen), `3` iPhone 12/Mini/Plus/Pro/Max, `4` iPhone 13/Mini/Plus/Pro/Max, `5` iPhone 14/Mini/Plus/Pro/Max, `6` iPhone 15/Plus/Pro/Max, `7` iPhone 16/Plus/Pro/Max, `3066` iPhone 17/Air/Pro/Max. Each run also saves the current filter values and hit counts in `data/raw/tori/<run>/search_meta.json`.

- **Data location:** `<script type="application/json" data-react-query-state>` holds **base64-encoded** JSON. The query whose key has `scope: "search"` contains `docs` (listings), `filters` (options with hit counts) and `metadata` (`result_size.match_count`, `paging`).
- **Per listing:** `id`, `heading`, `price.amount` + `currency_code`, `location` ("district, municipality"), `timestamp` (ms, published or renewed), `memory_size`, `brand`, `flags` (`private` / `retailer`, `shipping_exists`, `buy_now`), and image and coordinate fields we drop.
- **Not in search results:** condition, model bucket, description, region.
- **Size (2026-09-17):** 2,196 for-sale iPhones across 42 pages, so a full pass is **42 requests (~3 min)**. No duplicates across pages. The phone category holds 6,307 listings in total.
- **Markup gotcha:** the browser DOM shows the attribute as `data-react-query-state=""`, but the raw HTTP response has a bare `data-react-query-state`. The regex accepts both.

### Listing (item) pages

`https://www.tori.fi/recommerce/forsale/item/<listing_id>`

- **Data location:** a `<script>` containing `window.__staticRouterHydrationData = JSON.parse("…")`. The payload is a JSON string inside JSON, so decode twice. The listing is at `loaderData["item-recommerce"].itemData`.
- **Fields used:** `description` (full text), `extras[]` with `id` = `condition` / `mobile_model` / `mobile_memory_size` / `phone_brand` (each has `value` and `valueId`), and `location.postalName` = "municipality, district, region" (3 parts in 10/10 samples).
- **Activity flags:** `disposed` and `meta.isInactive` mark inactive listings, which are skipped.
- **Fields present but never stored:** `meta.ownerId`, `location.position` (lat/lng), `location.postalCode`, `images`.
- **Size:** a full pass adds **~2,200 requests (~2 h at 3–4 s)**.
- **Cheaper alternative:** condition and model bucket can instead come from filtered search queries (`&condition=N`, `&mobile_model=N`, ~90 requests). That loses the description and region; region could then be mapped from municipality.

### Data quality (full run, 2,178 listings)

- Accessories and spare parts (cases, screen protectors, back covers) are listed under the Apple phone brand, e.g. 9 € "silikonikuori". A title heuristic flags 83 listings (4%). Filter them in preprocessing.
- 8 listings are at 0 €, mostly swap offers ("Vaihdetaan").
- Retailers are 20% of listings (Elisa, Multitronic, …), with a median of 340 € vs. 200 € for private sellers. The first 129-listing sample overstated them at 40%.
- 154 descriptions (7%) contained contact details, now scrubbed. See [Privacy validation](#privacy-validation).
- Sellers leave fields empty: model group 22%, memory 12%, condition 4%.
- 3 listings have a Galaxy model group: 1 is a real Samsung phone and 2 are iPhones (XR, 4) that a seller mis-tagged. `preprocess.py` drops the Samsung and relabels the iPhones from their titles.
- 8 listings were removed (HTTP 404) and 9 went inactive between the search pass and the listing pass.

### Privacy validation

A scan of the full run on 2026-09-17 found **10 contact numbers the first scrubber missed** (3 from private sellers, 7 from shops):

- 8 written as `358…` without a plus, mostly WhatsApp links (`https://wa.me/358…`)
- 2 in other formats: a foreign number and an obfuscated one (`x401234567`)

The scrubber was extended (`_PHONE_RE`, a catch-all `_LONG_NUMBER_RE`, and `_PERSONAL_LINK_RE` for personal sites and social profiles in `tori.py`), with unit cases that keep prices, dates, 15-digit IMEIs and shop links intact. The saved data was then re-scrubbed offline, without new requests, and `listings.csv` and the summary were rebuilt; both steps are logged in the run's `collect.log`. A final scan finds no phone numbers, WhatsApp links, emails or 9–12 digit runs in titles or descriptions.

- **Raw data exception:** `data/raw/` is otherwise never edited after collection; a privacy fix is the one allowed exception.
- **Git history:** the earlier commit `dad9a23` still contains the missed numbers. History was not rewritten, a choice kept when the repository was made public for grading.
- **Addresses and links:** all 47 street addresses are shops'. Of 141 descriptions with links, 133 are shops'; the 8 from private sellers point to product pages (Verkkokauppa, Apple support, GSMArena) and a news article, except one link to a seller's personal website, which was masked as `[url]`.
- **Ad text kept local:** descriptions can mention first names, so titles and descriptions were removed from the repository on 16 Oct, before it was made public. `iphones_clean.csv` keeps the features derived from them.

## Legal and ethical context

Background for the report, not legal advice:

- **Copyright / database rights:** the EU text and data mining exceptions (DSM Directive Art. 3 for research organisations, Art. 4 for everyone else) respect machine-readable opt-outs such as robots.txt, which the collector checks at the start of every run ([COMMUNIA](https://communia-association.org/wp-content/uploads/2020/07/Webinar-Presentation-TDM-A.34.pdf), [IAPP](https://iapp.org/news/a/the-state-of-web-scraping-in-the-eu)).
- **GDPR applies separately** to any personal data in scraped text. The EDPB's [Guidelines 03/2026 on web scraping](https://www.edpb.europa.eu/news/edpb-sheds-light-on-anonymisation-and-web-scraping-for-generative-ai-and-adopts-final-version_en) (July 2026, written for generative AI but applicable in spirit) stress deciding what is necessary before collecting, designing the crawler for data minimisation, and validating collected data. That matches the field allowlist, forbidden-key check and the privacy validation above.
- **Terms of service:** Tori's terms restrict systematic collection without written permission; the group relies on the course supervisor's approval (see the README).

## Collection runs

`python3 -m priced_right.collect_iphones` collects every for-sale iPhone listing. Run it from the repo root; the code uses only the standard library and needs Python 3.9 or newer.

1. **Search pass:** all result pages go to `search_records.jsonl`. Listings shift between pages while new ones are published, so records are deduplicated by `listing_id`.
2. **Listing pass:** one listing page per result goes to `item_records.jsonl`. Inactive or removed listings go to `failures.jsonl` with a reason.
3. **Join:** `listings.csv` contains one row per listing with both records, using the columns in [data-dictionary.md](data-dictionary.md). This is the input for preprocessing.

Everything lands in `data/raw/tori/iphones_<timestamp>/` (committed; about 5 MB per full run). The aggregate summary and report go to `docs/runs/iphones_<timestamp>.json` and `.md`.

**Pause and resume:** press Ctrl-C in the collector's terminal, or run `kill <pid>` from another one. Each record is saved as soon as it's fetched, and a pause also writes `listings.csv` and the summary for the listings so far. The run also stops by itself on HTTP 403 or 429, or after 5 consecutive errors. Removed listings (HTTP 404/410) are recorded in `failures.jsonl` and not retried. Timeouts, connection errors and server errors (5xx) skip the listing without marking it done, so a resume retries it. Continue with:

```bash
python3 -m priced_right.collect_iphones --resume data/raw/tori/iphones_<timestamp>
```

A resume reuses the listing IDs from the original search pass. Over a long pause, sold listings get recorded as inactive and new listings are missed, so start a fresh run instead.

**Progress:** live view with done/total, seconds per listing and estimated finish time (refreshes every 10 s):

```bash
python3 -m priced_right.progress
```

Timeouts seen on 2026-09-17: 3 in the first ~160 listing pages. The same pages loaded in 0.2–1.2 s moments later, so they were temporary slowdowns, not throttling.

Smoke test (1 search page, 5 listings, nothing committed):

```bash
python3 -m priced_right.collect_iphones --max-pages 1 --max-items 5 --no-commit-output
```

| Run | Listings | Report |
|---|---|---|
| `iphones_2026-09-17T110158Z` | 2,178 (2,195 found; 17 removed or inactive during the run) | [report](runs/iphones_2026-09-17T110158Z.md), [summary](runs/iphones_2026-09-17T110158Z.json), data: `data/raw/tori/iphones_2026-09-17T110158Z/listings.csv` (local only) |

## Crawl4AI (Docker)

Not needed for Tori, because plain HTTP gets the embedded JSON. It's kept for sites that need a real browser.

- Image: `unclecode/crawl4ai:0.9.3`, container name `crawl4ai`, published on `127.0.0.1:11235` only
- Playground: http://localhost:11235/playground; dashboard: http://localhost:11235/dashboard
- Since 0.9.x the server only listens outside the container when `CRAWL4AI_API_TOKEN` is set. The token and `SECRET_KEY` are in `~/.config/crawl4ai/docker.env` (never commit them).
- In a browser crawl, Tori listings render inside declarative shadow DOM. Without `"flatten_shadow_dom": true` the page comes back empty and Crawl4AI misreports it as an anti-bot block.

```bash
docker start crawl4ai
```

```bash
docker run -d -p 127.0.0.1:11235:11235 --name crawl4ai --shm-size=1g --restart unless-stopped --env-file ~/.config/crawl4ai/docker.env unclecode/crawl4ai:0.9.3
```

If a browser crawl is ever needed again, the first test's CSS selectors (sent to `/crawl` with `Authorization: Bearer $CRAWL4AI_API_TOKEN`) were `h1[data-testid='object-title']`, `section[aria-label='Tee ostotarjous'] .h2`, `section[aria-label='Lisätietoja'] p`, `section[data-testid='description'] .whitespace-pre-wrap` and `section[data-testid='object-info'] p`.
