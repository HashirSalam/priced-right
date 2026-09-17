"""Minimal Tori.fi client for iPhone listing collection.

Tori renders pages on the server and embeds the underlying data as JSON, so
plain HTTP requests are enough (no headless browser). Parsers read that JSON
instead of the visible HTML, and the record builders keep only the fields in
docs/data-dictionary.md. Crawler rules and findings: docs/data-collection-notes.md.
"""
from __future__ import annotations

import base64
import json
import random
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

BASE_URL = "https://www.tori.fi"
SEARCH_PATH = "/recommerce/forsale/search"
ITEM_PATH = "/recommerce/forsale/item/{listing_id}"

USER_AGENT = "priced-right/0.1 (student data science project; non-commercial)"

# Search filter values, verified 2026-09-17.
MOBILE_PHONES_CATEGORY = "2.93.3217.39"
BRAND_APPLE = "631"
TRADE_TYPE_FOR_SALE = "1"  # excludes "Ostetaan" (wanted) and "Annetaan" (giveaway)
IPHONE_SEARCH = {
    "product_category": MOBILE_PHONES_CATEGORY,
    "brand": BRAND_APPLE,
    "trade_type": TRADE_TYPE_FOR_SALE,
    "sort": "PUBLISHED_DESC",  # stable order while paging
}

# Tori stops serving results after this page, whatever match_count says.
MAX_SEARCH_PAGE = 50

# Keys that must never appear in a stored record.
FORBIDDEN_KEYS = {
    "ownerId", "organisation_name", "coordinates", "position", "postalCode",
    "image", "images", "image_urls", "canonical_url", "location",
}

_SEARCH_STATE_RE = re.compile(
    r'<script type="application/json" data-react-query-state(?:="")?>(.*?)</script>', re.S
)
_ITEM_STATE_RE = re.compile(
    r'window\.__staticRouterHydrationData = JSON\.parse\((".*?")\);?\s*</script>', re.S
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Finnish phone numbers: 040…, +358…, 00358…, and 358… without a plus (e.g. wa.me/358… WhatsApp links).
# An unbroken run too long for a phone number (e.g. a 15-digit IMEI) does not match.
_PHONE_RE = re.compile(r"(?<!\d)(?:00358|\+?358(?!\d{10})|0(?!\d{11}))[\s-]?\d{1,3}(?:[\s-]?\d{2,4}){2,3}(?!\d)")
# Catch-all for other contact numbers (foreign formats, obfuscated like "x401234567"): any run of
# 9-12 digits with optional single spaces or hyphens. Unbroken 15-digit IMEIs do not match.
_LONG_NUMBER_RE = re.compile(r"(?<![\d.,])\d(?:[ -]?\d){8,11}(?![\d.,])")
# Links to personal pages a seller controls (site builders, social profiles, link-in-bio, Telegram).
_PERSONAL_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:[\w-]+\.(?:my\.canva\.site|wixsite\.com|carrd\.co)|(?:linktr\.ee|facebook\.com|fb\.com|instagram\.com|tiktok\.com|t\.me)/)\S*",
    re.I,
)


# Heuristic only: titles that look like accessories or spare parts rather than phones.
ACCESSORY_TITLE_RE = re.compile(
    r"\b(suoja)?kuor\w*|\bkotelo\w*|suojalasi\w*|panssarilasi\w*|takakan\w*|laturi\w*|kaapeli\w*|johto\w*|varaosa\w*|\bcase\b|\bcover\b",
    re.I,
)


def quantiles(values: List[float]) -> Dict[str, Any]:
    """Min, quartiles and max for run summaries."""
    if not values:
        return {"count": 0}
    values = sorted(values)
    q1, median, q3 = statistics.quantiles(values, n=4) if len(values) > 1 else (values[0],) * 3
    return {"count": len(values), "min": values[0], "p25": q1, "median": median, "p75": q3, "max": values[-1]}


def share(counter: Counter, total: int) -> Dict[str, Any]:
    """Counts with their share of the total, most common first."""
    return {str(k): {"count": v, "share": round(v / total, 3)} for k, v in counter.most_common()} if total else {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ToriClient:
    """Polite sequential HTTP client: one request at a time with a randomized delay."""

    def __init__(self, delay_seconds: float = 3.0, jitter_seconds: float = 1.0,
                 user_agent: str = USER_AGENT, timeout: float = 30.0,
                 rng: Optional[random.Random] = None):
        self.delay_seconds = delay_seconds
        self.jitter_seconds = jitter_seconds
        self.user_agent = user_agent
        self.timeout = timeout
        self.rng = rng or random.Random()
        self.request_log: List[Dict[str, Any]] = []
        self._last_request_at = 0.0

    def get(self, url: str) -> str:
        wait = self._last_request_at + self.delay_seconds + self.rng.uniform(0, self.jitter_seconds) - time.monotonic()
        if self._last_request_at and wait > 0:
            time.sleep(wait)
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept-Language": "fi,en;q=0.8"})
        started = time.monotonic()
        status, body = None, b""
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
            raise
        finally:
            self._last_request_at = time.monotonic()
            self.request_log.append({"url": url, "status": status, "seconds": round(self._last_request_at - started, 3), "bytes": len(body)})
        return body.decode("utf-8")

    def robots(self) -> "RobotsRules":
        return RobotsRules(self.get(BASE_URL + "/robots.txt"))

    def search(self, params: Dict[str, str], page: int = 1) -> Dict[str, Any]:
        return parse_search_state(self.get(search_url(params, page)))

    def item(self, listing_id: str) -> Dict[str, Any]:
        return parse_item_data(self.get(item_url(listing_id)))


class RobotsRules:
    """robots.txt rules for `User-agent: *`, with `*` and `$` wildcards.

    urllib.robotparser treats `*` literally, so it wrongly allows Tori's
    `Disallow: /profile*` and `/map*`. The longest matching rule wins and
    Allow wins ties, as in RFC 9309.
    """

    def __init__(self, text: str):
        self.rules: List[Tuple[str, bool, "re.Pattern[str]"]] = []
        applies = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field = field.lower()
            if field == "user-agent":
                applies = value == "*"
            elif applies and field in ("allow", "disallow") and value:
                pattern = re.escape(value).replace(r"\*", ".*")
                pattern = pattern[:-2] + "$" if pattern.endswith(r"\$") else pattern
                self.rules.append((value, field == "allow", re.compile(pattern)))

    def can_fetch(self, url: str) -> bool:
        parts = urllib.parse.urlsplit(url)
        path = parts.path + ("?" + parts.query if parts.query else "")
        matches = [(len(value), allow) for value, allow, pattern in self.rules if pattern.match(path)]
        return max(matches)[1] if matches else True


def search_url(params: Dict[str, str], page: int = 1) -> str:
    query = dict(params)
    if page > 1:
        query["page"] = str(page)
    return f"{BASE_URL}{SEARCH_PATH}?{urllib.parse.urlencode(query)}"


def item_url(listing_id: str) -> str:
    return BASE_URL + ITEM_PATH.format(listing_id=listing_id)


def parse_search_state(html: str) -> Dict[str, Any]:
    """Return the search result state: {"docs", "filters", "metadata", ...}.

    Search pages embed React Query state as base64-encoded JSON.
    """
    match = _SEARCH_STATE_RE.search(html)
    if not match:
        raise ValueError("search page has no data-react-query-state script")
    state = json.loads(base64.b64decode(match.group(1)))
    for query in state["queries"]:
        key = query["queryKey"][0]
        if isinstance(key, dict) and key.get("scope") == "search":
            return query["state"]["data"]
    raise ValueError("search page state has no search query")


def parse_item_data(html: str) -> Dict[str, Any]:
    """Return the listing object embedded in an item page.

    Item pages embed router hydration data as a JSON string inside JSON.parse("...").
    """
    match = _ITEM_STATE_RE.search(html)
    if not match:
        raise ValueError("item page has no __staticRouterHydrationData script")
    hydration = json.loads(json.loads(match.group(1)))
    return hydration["loaderData"]["item-recommerce"]["itemData"]


def filter_values(search_state: Dict[str, Any], names: Tuple[str, ...]) -> Dict[str, List[Dict[str, Any]]]:
    """Filter options with their URL parameter values and hit counts."""
    result = {}
    for f in search_state["filters"]:
        if f.get("name") in names:
            result[f["name"]] = [
                {"label": item.get("display_name"), "param": item.get("name"), "value": item.get("value"), "hits": item.get("hits")}
                for item in f.get("filter_items") or []
            ]
    return result


def scrub_pii(text: str) -> Tuple[str, int]:
    """Replace personal links, emails, Finnish phone numbers (including WhatsApp links) and other long digit runs.

    Returns (text, replacements). Placeholders: [url], [email], [phone], [number].
    """
    text, links = _PERSONAL_LINK_RE.subn("[url]", text)
    text, emails = _EMAIL_RE.subn("[email]", text)
    text, phones = _PHONE_RE.subn("[phone]", text)
    text, numbers = _LONG_NUMBER_RE.subn("[number]", text)
    return text, links + emails + phones + numbers


def search_doc_to_record(doc: Dict[str, Any], collected_at: str) -> Dict[str, Any]:
    flags = doc.get("flags") or []
    price = doc.get("price") or {}
    location = doc.get("location") or ""
    return {
        "listing_id": str(doc["id"]),
        "title": scrub_pii(doc.get("heading") or "")[0] or None,
        "price_eur": price.get("amount") if price.get("currency_code") == "EUR" else None,
        "memory": doc.get("memory_size"),
        "municipality": location.rsplit(",", 1)[-1].strip() or None,
        "published_at": datetime.fromtimestamp(doc["timestamp"] / 1000, timezone.utc).isoformat(timespec="seconds") if doc.get("timestamp") else None,
        "seller_type": "retailer" if "retailer" in flags else "private" if "private" in flags else "unknown",
        "shipping_available": "shipping_exists" in flags,
        "collected_at": collected_at,
    }


def item_data_to_record(item: Dict[str, Any], collected_at: str) -> Dict[str, Any]:
    extras = {e.get("id"): e for e in item.get("extras") or []}
    postal_name = (item.get("location") or {}).get("postalName") or ""
    description, _ = scrub_pii(item.get("description") or "")
    return {
        "listing_id": str(item["meta"]["adId"]),
        "description": description or None,
        "condition": (extras.get("condition") or {}).get("value"),
        "model_group": (extras.get("mobile_model") or {}).get("value"),
        "region": postal_name.rsplit(",", 1)[-1].strip() if postal_name.count(",") >= 2 else None,
        "collected_at": collected_at,
    }


def is_listing_active(item: Dict[str, Any]) -> bool:
    meta = item.get("meta") or {}
    return not item.get("disposed") and not meta.get("isInactive")
