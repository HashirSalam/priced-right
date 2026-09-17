# Data Collection Notes

> Bulk collection from Tori.fi waits on written permission (see the canvas). So far only small experiments have run: 14 requests on 2026-09-17. The eBay Browse API is the fallback source.

## Tori.fi: crawler rules

Rules the collector follows, all implemented in [`collection/tori/tori.py`](../collection/tori/tori.py):

1. **robots.txt:** only `/recommerce/forsale/search` and `/recommerce/forsale/item/*` are fetched. Tori disallows `/map*`, `/profile*`, `/messages*`, `/contact/*`, `/report/*` and account pages. Python's `urllib.robotparser` ignores `*` wildcards and wrongly allows `/profile*` and `/map*`, so `RobotsRules` implements the matching itself (longest match wins).
2. **One request at a time,** at least 3 s apart plus up to 1 s random jitter (`ToriClient`).
3. **Honest user agent:** `priced-right/0.1 (student data science project; non-commercial)`. Tori serves it normally.
4. **Plain HTTP, no browser.** Pages are rendered on the server with the data embedded as JSON; responses take ~0.3 s.
5. **Data minimization at collection time:** records keep only the fields in [data-dictionary.md](data-dictionary.md). Phone numbers and emails in descriptions are scrubbed before writing, and forbidden keys (seller ID, coordinates, images, …) fail the run.
6. **Storage:** minimized records go to `data/raw/tori/<run>/` (git-ignored). Only aggregate outputs are committed.

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
| `mobile_model` | e.g. `6` | iPhone 15/Plus/Pro/Max. All values: [filters.json](../collection/tori/output/exp01_feasibility/filters.json) |

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

### Data quality seen so far

- Accessories and spare parts (cases, screen protectors, back covers) are listed under the Apple phone brand, e.g. 9 € "silikonikuori". A title heuristic flagged 2 of 129 in one sample and 6 of 225 in another. Filter them in preprocessing.
- 0 € listings are swap offers ("Vaihdetaan").
- Retailers made up 40% of listings in the sample (Elisa, Multitronic, …).
- Some descriptions contain phone numbers (1 of 10 sampled).

## Experiments

| # | Script | Question | Output |
|---|---|---|---|
| 01 | `python3 -m collection.tori.exp01_feasibility` | Can we collect iPhones, and which fields are available? | [report](../collection/tori/output/exp01_feasibility/report.md), [summary.json](../collection/tori/output/exp01_feasibility/summary.json), [filters.json](../collection/tori/output/exp01_feasibility/filters.json) |

Run from the repo root. The code uses only the standard library and needs Python 3.9 or newer.

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

The CSS-selector extraction request from the first test is in [`collection/tori/listing_extraction_request.json`](../collection/tori/listing_extraction_request.json). It sends `Authorization: Bearer $CRAWL4AI_API_TOKEN` and targets `h1[data-testid='object-title']`, `section[aria-label='Tee ostotarjous'] .h2`, `section[aria-label='Lisätietoja'] p`, `section[data-testid='description'] .whitespace-pre-wrap` and `section[data-testid='object-info'] p`.
