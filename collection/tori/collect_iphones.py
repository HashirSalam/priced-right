"""Collect all for-sale iPhone listings from Tori.fi.

Two passes, both following the crawler rules in docs/data-collection-notes.md:
  1. Search pass: every results page (~42 requests) -> search_records.jsonl
  2. Listing pass: one page per listing (~2,200 requests, ~2 h) -> item_records.jsonl
Then joins both into listings.csv and writes an aggregate summary.

Run from the repository root:
    python3 -m collection.tori.collect_iphones
    python3 -m collection.tori.collect_iphones --resume data/raw/tori/iphones_2026-09-17T110000Z
    python3 -m collection.tori.collect_iphones --max-pages 1 --max-items 5    # smoke test

Outputs:
    data/raw/tori/iphones_<timestamp>/                     records, listings.csv, failures, log (not committed)
    collection/tori/output/collect_iphones/<run>/          summary.json and report.md (committed)

Safe to interrupt: rerun with --resume and finished listings are skipped. The run
stops early on HTTP 403/429 or repeated errors, and progress is kept.
"""
from __future__ import annotations

import argparse
import csv
import http.client
import json
import signal
import statistics
import sys
import urllib.error
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

from collection.tori import tori
from collection.tori.exp01_feasibility import ACCESSORY_TITLE_RE, quantiles, share

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "tori"
OUTPUT_DIR = REPO_ROOT / "collection" / "tori" / "output" / "collect_iphones"

STOP_STATUSES = {403, 429}
MAX_CONSECUTIVE_ERRORS = 5
CSV_COLUMNS = [
    "listing_id", "title", "description", "price_eur", "condition", "model_group", "memory",
    "seller_type", "shipping_available", "municipality", "region", "published_at", "collected_at",
]


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read records, skipping a line cut short if the run was killed mid-write."""
    records = []
    if path.exists():
        for line in path.open():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    with path.open("a") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def log(run_dir: Path, message: str) -> None:
    line = f"{tori.utc_now()} {message}"
    print(line, flush=True)
    with (run_dir / "collect.log").open("a") as fh:
        fh.write(line + "\n")


class StopCollection(Exception):
    pass


def check_forbidden(record: Dict[str, Any]) -> None:
    leaked = set(record) & tori.FORBIDDEN_KEYS
    if leaked:
        raise StopCollection(f"forbidden keys in record: {sorted(leaked)}")


def search_pass(client: tori.ToriClient, run_dir: Path, collected_at: str, max_pages: int) -> List[Dict[str, Any]]:
    path = run_dir / "search_records.jsonl"
    existing = read_jsonl(path)
    if existing:
        log(run_dir, f"search pass already done: {len(existing)} records")
        return existing

    first = client.search(tori.IPHONE_SEARCH, page=1)
    meta = first["metadata"]
    last_page = min(meta["paging"]["last"], tori.MAX_SEARCH_PAGE, max_pages)
    log(run_dir, f"search: match_count={meta['result_size']['match_count']} pages={meta['paging']['last']} fetching={last_page}")
    (run_dir / "search_meta.json").write_text(json.dumps({
        "match_count": meta["result_size"]["match_count"], "last_page": meta["paging"]["last"], "pages_fetched": last_page,
        "filters": tori.filter_values(first, ("condition", "mobile_model", "mobile_memory_size", "dealer_segment")),
    }, ensure_ascii=False, indent=2) + "\n")

    records: Dict[str, Dict[str, Any]] = {}
    seen_twice = 0
    for page in range(1, last_page + 1):
        state = first if page == 1 else client.search(tori.IPHONE_SEARCH, page=page)
        for doc in state["docs"]:
            record = tori.search_doc_to_record(doc, collected_at)
            check_forbidden(record)
            if record["listing_id"] in records:
                seen_twice += 1  # listings shift between pages while new ones are published
            records[record["listing_id"]] = record
        if page % 10 == 0 or page == last_page:
            log(run_dir, f"search page {page}/{last_page}: {len(records)} unique listings")

    with path.open("w") as fh:
        fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in records.values())
    log(run_dir, f"search pass done: {len(records)} unique listings, {seen_twice} seen on two pages")
    return list(records.values())


def item_pass(client: tori.ToriClient, run_dir: Path, collected_at: str, listing_ids: List[str], max_items: int) -> None:
    items_path, failures_path = run_dir / "item_records.jsonl", run_dir / "failures.jsonl"
    done = {r["listing_id"] for r in read_jsonl(items_path)} | {f["listing_id"] for f in read_jsonl(failures_path)}
    todo = [i for i in listing_ids if i not in done][:max_items]
    log(run_dir, f"listing pass: {len(done)} already done, {len(todo)} to fetch")

    consecutive_errors = 0
    for n, listing_id in enumerate(todo, 1):
        try:
            item = client.item(listing_id)
            if not tori.is_listing_active(item):
                append_jsonl(failures_path, {"listing_id": listing_id, "reason": "inactive"})
            else:
                record = tori.item_data_to_record(item, collected_at)
                check_forbidden(record)
                append_jsonl(items_path, record)
            consecutive_errors = 0
        except urllib.error.HTTPError as error:
            if error.code in STOP_STATUSES:
                raise StopCollection(f"HTTP {error.code} on listing {listing_id}; stopping to respect the site")
            append_jsonl(failures_path, {"listing_id": listing_id, "reason": f"http_{error.code}"})
            consecutive_errors = 0 if error.code in (404, 410) else consecutive_errors + 1
        except (OSError, http.client.HTTPException, ValueError, KeyError) as error:
            # OSError covers URLError and, on Python 3.9, socket.timeout during read.
            consecutive_errors += 1
            log(run_dir, f"error on {listing_id}: {type(error).__name__}: {error}")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                raise StopCollection(f"{consecutive_errors} consecutive errors; stopping")
        if n % 100 == 0 or n == len(todo):
            log(run_dir, f"listing {n}/{len(todo)}")


def join_listings(search_records: List[Dict[str, Any]], item_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = {r["listing_id"]: r for r in item_records}
    joined = []
    for s in search_records:
        item = items.get(s["listing_id"])
        if item:
            row = {**s, **{k: v for k, v in item.items() if k != "collected_at"}}
            joined.append({column: row.get(column) for column in CSV_COLUMNS})
    return joined


def write_csv(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def summarize(run_dir: Path, search_records, item_records, failures, listings, client, stopped_reason) -> Dict[str, Any]:
    n = len(listings)
    prices = [r["price_eur"] for r in listings if r["price_eur"] is not None]
    log_entries = client.request_log
    return {
        "run": run_dir.name,
        "query": tori.IPHONE_SEARCH,
        "search_meta": {k: v for k, v in json.loads((run_dir / "search_meta.json").read_text()).items() if k != "filters"},
        "stopped_reason": stopped_reason,
        "counts": {
            "search_records": len(search_records),
            "item_records": len(item_records),
            "failures": dict(Counter(f["reason"] for f in failures)),
            "listings_joined": n,
            "search_records_without_listing_page": len(search_records) - len(item_records) - len(failures),
        },
        "coverage": {c: round(sum(1 for r in listings if r[c] not in (None, "")) / n, 3) if n else None for c in CSV_COLUMNS},
        "price_eur": quantiles(prices),
        "price_zero": sum(1 for p in prices if p == 0),
        "accessory_like_titles": sum(1 for r in listings if ACCESSORY_TITLE_RE.search(r["title"] or "")),
        "seller_type": share(Counter(r["seller_type"] for r in listings), n),
        "condition": share(Counter(r["condition"] for r in listings), n),
        "model_group": share(Counter(r["model_group"] for r in listings), n),
        "memory": share(Counter(r["memory"] for r in listings), n),
        "region": share(Counter(r["region"] for r in listings), n),
        "median_price_by_condition": {str(k): statistics.median(v) for k, v in group_prices(listings, "condition").items()},
        "median_price_by_model_group": {str(k): statistics.median(v) for k, v in group_prices(listings, "model_group").items()},
        "median_price_by_seller_type": {str(k): statistics.median(v) for k, v in group_prices(listings, "seller_type").items()},
        "description_chars": quantiles([len(r["description"] or "") for r in listings]),
        "descriptions_with_scrubbed_contacts": sum(1 for r in listings if "[phone]" in (r["description"] or "") or "[email]" in (r["description"] or "")),
        "requests_this_session": {
            "count": len(log_entries),
            "statuses": dict(Counter(str(e["status"]) for e in log_entries)),
            "mean_seconds": round(statistics.mean(e["seconds"] for e in log_entries), 3) if log_entries else None,
            "total_mb": round(sum(e["bytes"] for e in log_entries) / 1e6, 1),
            "delay_seconds": client.delay_seconds,
            "user_agent": client.user_agent,
        },
    }


def group_prices(rows: List[Dict[str, Any]], column: str) -> Dict[Any, List[float]]:
    groups: Dict[Any, List[float]] = {}
    for r in rows:
        if r["price_eur"] is not None:
            groups.setdefault(r[column], []).append(r["price_eur"])
    return dict(sorted(groups.items(), key=lambda kv: -len(kv[1])))


def render_report(s: Dict[str, Any]) -> str:
    c, req = s["counts"], s["requests_this_session"]
    fmt = lambda d: ", ".join(f"{k} {v['count']} ({v['share']:.0%})" for k, v in d.items())
    lines = [
        f"# iPhone collection run `{s['run']}`",
        "",
        "Generated by `python3 -m collection.tori.collect_iphones`; do not edit by hand. Listing-level data is in `data/raw/tori/` (git-ignored).",
        "",
        f"- Stopped early: **{s['stopped_reason']}**" if s["stopped_reason"] else "- Completed without stopping early",
        f"- Search: {s['search_meta']['match_count']} matches, {s['search_meta']['pages_fetched']} pages fetched, {c['search_records']} unique listings",
        f"- Listing pages: {c['item_records']} parsed, failures {c['failures'] or 'none'}, not yet fetched {c['search_records_without_listing_page']}",
        f"- **Joined listings: {c['listings_joined']}**",
        f"- Requests this session: {req['count']}, statuses {req['statuses']}, mean {req['mean_seconds']} s, {req['total_mb']} MB, ≥{req['delay_seconds']} s apart",
        "",
        "## Coverage",
        "",
        ", ".join(f"{k} {v:.0%}" for k, v in s["coverage"].items() if v is not None),
        "",
        "## Prices (EUR)",
        "",
        f"- Overall: {s['price_eur']}; zero prices {s['price_zero']}; accessory-like titles (heuristic) {s['accessory_like_titles']}",
        f"- Median by condition: {s['median_price_by_condition']}",
        f"- Median by seller type: {s['median_price_by_seller_type']}",
        f"- Median by model group: {s['median_price_by_model_group']}",
        "",
        "## Distributions",
        "",
        f"- Seller type: {fmt(s['seller_type'])}",
        f"- Condition: {fmt(s['condition'])}",
        f"- Model group: {fmt(s['model_group'])}",
        f"- Memory: {fmt(s['memory'])}",
        f"- Region: {fmt(s['region'])}",
        f"- Description length (chars): {s['description_chars']}; descriptions with scrubbed phone/email: {s['descriptions_with_scrubbed_contacts']}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--resume", type=Path, help="existing run directory to continue")
    parser.add_argument("--delay", type=float, default=3.0, help="minimum seconds between requests")
    parser.add_argument("--max-pages", type=int, default=tori.MAX_SEARCH_PAGE)
    parser.add_argument("--max-items", type=int, default=10**9)
    parser.add_argument("--no-commit-output", action="store_true", help="skip writing the committed summary (for smoke tests)")
    args = parser.parse_args()

    if args.resume:
        run_dir = args.resume.resolve()
        collected_at = json.loads((run_dir / "run.json").read_text())["collected_at"]
    else:
        collected_at = tori.utc_now()
        run_dir = RAW_DIR / ("iphones_" + collected_at.replace(":", "").replace("+0000", "Z"))
        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "run.json").write_text(json.dumps({"collected_at": collected_at, "query": tori.IPHONE_SEARCH, "delay_seconds": args.delay}, indent=2) + "\n")

    # `kill <pid>` pauses as cleanly as Ctrl-C: progress is written and --resume continues.
    signal.signal(signal.SIGTERM, signal.default_int_handler)

    client = tori.ToriClient(delay_seconds=args.delay)
    robots = client.robots()
    if not (robots.can_fetch(tori.search_url(tori.IPHONE_SEARCH)) and robots.can_fetch(tori.item_url("1"))):
        sys.exit("robots.txt disallows search or listing pages; stopping.")

    stopped_reason = None
    try:
        search_records = search_pass(client, run_dir, collected_at, args.max_pages)
        item_pass(client, run_dir, collected_at, [r["listing_id"] for r in search_records], args.max_items)
    except StopCollection as stop:
        stopped_reason = str(stop)
        log(run_dir, f"STOPPED: {stopped_reason}")
    except KeyboardInterrupt:
        stopped_reason = "interrupted"
        log(run_dir, "interrupted; rerun with --resume to continue")

    search_records = read_jsonl(run_dir / "search_records.jsonl")
    item_records = read_jsonl(run_dir / "item_records.jsonl")
    failures = read_jsonl(run_dir / "failures.jsonl")
    listings = join_listings(search_records, item_records)
    write_csv(run_dir / "listings.csv", listings)

    if search_records:
        summary = summarize(run_dir, search_records, item_records, failures, listings, client, stopped_reason)
        (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        if not args.no_commit_output:
            out = OUTPUT_DIR / run_dir.name
            out.mkdir(parents=True, exist_ok=True)
            (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
            (out / "report.md").write_text(render_report(summary))
    log(run_dir, f"wrote {len(listings)} listings to {run_dir.relative_to(REPO_ROOT)}/listings.csv")


if __name__ == "__main__":
    main()
