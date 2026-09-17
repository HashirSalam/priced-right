# Data Collection Notes

> Bulk collection from Tori.fi waits on written permission (see the canvas). Everything below comes from a single test listing and is kept for when permission arrives. Until then, the eBay Browse API is the fallback source.

## Crawler: Crawl4AI in Docker

- Image: `unclecode/crawl4ai:0.9.3`, container name `crawl4ai`
- API: http://localhost:11235, published on `127.0.0.1` only
- Playground: http://localhost:11235/playground; monitor dashboard: http://localhost:11235/dashboard
- Since 0.9.x the server only listens outside the container when `CRAWL4AI_API_TOKEN` is set. The token and `SECRET_KEY` live in `~/.config/crawl4ai/docker.env` (never commit them).

Start and stop:

```bash
docker start crawl4ai
docker stop crawl4ai
```

Recreate from scratch:

```bash
docker run -d -p 127.0.0.1:11235:11235 --name crawl4ai --shm-size=1g --restart unless-stopped --env-file ~/.config/crawl4ai/docker.env unclecode/crawl4ai:0.9.3
```

## Tori.fi listing pages

Test URL: https://www.tori.fi/recommerce/forsale/item/45132336

- **Shadow DOM:** listing content is rendered inside declarative shadow DOM (Web Components). A default crawl returns an empty page and Crawl4AI misreports it as "Blocked by anti-bot protection". Set `"flatten_shadow_dom": true` in `CrawlerRunConfig`.
- **JSON-LD:** the page also embeds a schema.org `Product` block (`sku`, `name`, `description`, `image`, `brand`, `offers.price`). Its description is truncated, so use the DOM for full text.
- **Images:** image URLs follow `https://img.tori.net/dynamic/{size}/item/{listing_id}/{uuid}`. The canvas excludes photos, so only count them if useful as a feature.

### CSS selectors (verified 2026-09-17)

| Field | Selector |
|---|---|
| Title | `h1[data-testid='object-title']` |
| Asking price | `section[aria-label='Tee ostotarjous'] .h2` (e.g. `580 €`) |
| Attributes (condition, brand, memory, model) | `section[aria-label='Lisätietoja'] p` (e.g. `Kunto: Kuin uusi`) |
| Description | `section[data-testid='description'] .whitespace-pre-wrap` |
| Location | `a[data-testid='map-link']` → `aria-label` (postal code, district, region) and `href` (lat/lon) |
| Last edited + listing ID | `section[data-testid='object-info'] p` |
| Category breadcrumbs | markdown output; `category`, `sub_category`, `product_category` query params in breadcrumb links |

Full request body: [`collection/tori/listing_extraction_request.json`](../collection/tori/listing_extraction_request.json)

```bash
set -a; . ~/.config/crawl4ai/docker.env; set +a
```

```bash
curl -s -X POST http://localhost:11235/crawl -H "Authorization: Bearer $CRAWL4AI_API_TOKEN" -H 'Content-Type: application/json' -d @collection/tori/listing_extraction_request.json
```

### Known gaps

- The extracted description loses paragraph breaks.
- Attribute label and value arrive joined (`Kunto:Kuin uusi`) and need splitting.
- Seller profile is hidden unless logged in; the canvas excludes seller data anyway.
- Selectors are tied to Tori's current markup and will break when it changes.
