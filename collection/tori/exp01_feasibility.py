"""Experiment 01: can we collect iPhone listings from Tori.fi, and which model fields are available?

Deliberately small: robots.txt, three search pages and a seeded sample of item pages.

Run from the repository root:
    python3 -m collection.tori.exp01_feasibility
    python3 -m collection.tori.exp01_feasibility --items 20 --delay 3

Outputs:
    collection/tori/output/exp01_feasibility/summary.json   aggregate findings (committed)
    collection/tori/output/exp01_feasibility/report.md      readable version of the summary (committed)
    collection/tori/output/exp01_feasibility/filters.json   search filter values and hit counts (committed)
    data/raw/tori/exp01_<timestamp>/*.jsonl                 minimized listing records (not committed)
"""
from __future__ import annotations

import argparse
import json
import random
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from collection.tori import tori

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "collection" / "tori" / "output" / "exp01_feasibility"
RAW_DIR = REPO_ROOT / "data" / "raw" / "tori"

# Heuristic only: titles that look like accessories or spare parts rather than phones.
ACCESSORY_TITLE_RE = re.compile(
    r"\b(suoja)?kuor\w*|\bkotelo\w*|suojalasi\w*|panssarilasi\w*|takakan\w*|laturi\w*|kaapeli\w*|johto\w*|varaosa\w*|\bcase\b|\bcover\b",
    re.I,
)


def quantiles(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"count": 0}
    values = sorted(values)
    q1, median, q3 = statistics.quantiles(values, n=4) if len(values) > 1 else (values[0],) * 3
    return {"count": len(values), "min": values[0], "p25": q1, "median": median, "p75": q3, "max": values[-1]}


def share(counter: Counter, total: int) -> Dict[str, Any]:
    return {str(k): {"count": v, "share": round(v / total, 3)} for k, v in counter.most_common()} if total else {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--items", type=int, default=10, help="number of item pages to sample")
    parser.add_argument("--delay", type=float, default=3.0, help="minimum seconds between requests")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    started_at = tori.utc_now()
    client = tori.ToriClient(delay_seconds=args.delay, rng=random.Random(args.seed))
    summary: Dict[str, Any] = {"experiment": "exp01_feasibility", "started_at": started_at, "query": tori.IPHONE_SEARCH}

    # 1. robots.txt
    robots = client.robots()
    summary["robots"] = {
        "search_allowed": robots.can_fetch(tori.search_url(tori.IPHONE_SEARCH)),
        "item_allowed": robots.can_fetch(tori.item_url("45132336")),
        "map_allowed": robots.can_fetch(tori.BASE_URL + "/map?adId=45132336"),
        "profile_allowed": robots.can_fetch(tori.BASE_URL + "/profile/ads"),
    }
    if not (summary["robots"]["search_allowed"] and summary["robots"]["item_allowed"]):
        raise SystemExit("robots.txt disallows search or item pages; stopping.")

    # 2. Search pages: first, second and last.
    first = client.search(tori.IPHONE_SEARCH, page=1)
    meta = first["metadata"]
    last_page = min(meta["paging"]["last"], tori.MAX_SEARCH_PAGE)
    pages = {1: first, 2: client.search(tori.IPHONE_SEARCH, page=2), last_page: client.search(tori.IPHONE_SEARCH, page=last_page)}
    ids_by_page = {page: [d["id"] for d in state["docs"]] for page, state in pages.items()}
    docs = {d["id"]: d for state in pages.values() for d in state["docs"]}.values()
    docs = list(docs)

    filters = tori.filter_values(first, ("condition", "mobile_model", "mobile_memory_size", "dealer_segment", "shipping_types", "trade_type"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "filters.json").write_text(json.dumps({"collected_at": started_at, "query": tori.IPHONE_SEARCH, "filters": filters}, ensure_ascii=False, indent=2) + "\n")

    prices = [d["price"]["amount"] for d in docs if d.get("price")]
    summary["search"] = {
        "match_count": meta["result_size"]["match_count"],
        "last_page": meta["paging"]["last"],
        "docs_per_page": {str(p): len(ids) for p, ids in ids_by_page.items()},
        "estimated_requests_for_all_results": last_page,
        "duplicate_ids_across_pages": len([i for ids in ids_by_page.values() for i in ids]) - len(docs),
        "unique_docs_sampled": len(docs),
        "doc_keys": dict(Counter(k for d in docs for k in d)),
        "coverage": {
            "price": sum(1 for d in docs if d.get("price")) / len(docs),
            "memory_size": sum(1 for d in docs if d.get("memory_size")) / len(docs),
            "location_with_municipality": sum(1 for d in docs if "," in (d.get("location") or "")) / len(docs),
            "timestamp": sum(1 for d in docs if d.get("timestamp")) / len(docs),
        },
        "currencies": dict(Counter(d["price"].get("currency_code") for d in docs if d.get("price"))),
        "price_eur": quantiles(prices),
        "price_zero": sum(1 for p in prices if p == 0),
        "price_at_most_20": sum(1 for p in prices if p <= 20),
        "flags": dict(Counter(f for d in docs for f in d.get("flags") or [])),
        "memory_size": dict(Counter(d.get("memory_size") for d in docs)),
        "accessory_like_titles": sum(1 for d in docs if ACCESSORY_TITLE_RE.search(d.get("heading") or "")),
    }
    search_records = [tori.search_doc_to_record(d, started_at) for d in docs]
    summary["search"]["seller_type"] = share(Counter(r["seller_type"] for r in search_records), len(search_records))

    # 3. Item pages: seeded sample from the first page.
    sample_ids = random.Random(args.seed).sample(ids_by_page[1], min(args.items, len(ids_by_page[1])))
    item_records, failures, inactive, pii_replacements, description_lengths, postal_name_parts = [], [], 0, 0, [], Counter()
    for listing_id in sample_ids:
        try:
            item = client.item(listing_id)
        except Exception as error:  # record and continue: parser robustness is part of the experiment
            failures.append({"listing_id": listing_id, "error": f"{type(error).__name__}: {error}"})
            continue
        if not tori.is_listing_active(item):
            inactive += 1
            continue
        postal_name_parts[len(((item.get("location") or {}).get("postalName") or "").split(","))] += 1
        _, replaced = tori.scrub_pii(item.get("description") or "")
        pii_replacements += replaced
        record = tori.item_data_to_record(item, started_at)
        description_lengths.append(len(record["description"] or ""))
        item_records.append(record)

    n = len(item_records)
    summary["items"] = {
        "sampled": len(sample_ids),
        "parsed_active": n,
        "inactive_or_disposed": inactive,
        "failures": failures,
        "coverage": {field: (sum(1 for r in item_records if r[field]) / n if n else None) for field in ("description", "condition", "model_group", "region")},
        "description_chars": quantiles(description_lengths),
        "pii_replacements_in_descriptions": pii_replacements,
        "condition": dict(Counter(r["condition"] for r in item_records)),
        "model_group": dict(Counter(r["model_group"] for r in item_records)),
        "region": dict(Counter(r["region"] for r in item_records)),
        "postal_name_parts": {str(k): v for k, v in postal_name_parts.items()},
    }

    # 4. Privacy check on what would be stored.
    stored_keys = {k for r in search_records + item_records for k in r}
    summary["privacy"] = {"stored_keys": sorted(stored_keys), "forbidden_keys_present": sorted(stored_keys & tori.FORBIDDEN_KEYS)}
    if summary["privacy"]["forbidden_keys_present"]:
        raise SystemExit(f"forbidden keys in records: {summary['privacy']['forbidden_keys_present']}")

    log = client.request_log
    summary["requests"] = {
        "count": len(log),
        "statuses": dict(Counter(r["status"] for r in log)),
        "mean_seconds": round(statistics.mean(r["seconds"] for r in log), 3),
        "total_mb": round(sum(r["bytes"] for r in log) / 1e6, 2),
        "delay_seconds": args.delay,
        "user_agent": client.user_agent,
    }
    summary["finished_at"] = tori.utc_now()

    run_dir = RAW_DIR / ("exp01_" + started_at.replace(":", "").replace("+0000", "Z"))
    run_dir.mkdir(parents=True, exist_ok=True)
    for name, records in (("search_records", search_records), ("item_records", item_records)):
        with open(run_dir / f"{name}.jsonl", "w") as fh:
            fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in records)

    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    (OUTPUT_DIR / "report.md").write_text(render_report(summary, run_dir))
    print(f"wrote {OUTPUT_DIR.relative_to(REPO_ROOT)}/ and {run_dir.relative_to(REPO_ROOT)}/")


def render_report(s: Dict[str, Any], run_dir: Path) -> str:
    search, items, req = s["search"], s["items"], s["requests"]
    pct = lambda x: "n/a" if x is None else f"{x:.0%}"
    lines = [
        "# Experiment 01: Tori.fi iPhone feasibility",
        "",
        f"Run {s['started_at']} → {s['finished_at']}. Generated by `python3 -m collection.tori.exp01_feasibility`; do not edit by hand.",
        "",
        "## Crawl rules",
        "",
        f"- robots.txt allows search pages: **{s['robots']['search_allowed']}**, item pages: **{s['robots']['item_allowed']}**, map: {s['robots']['map_allowed']}, profiles: {s['robots']['profile_allowed']}",
        f"- {req['count']} requests, statuses {req['statuses']}, mean {req['mean_seconds']} s, {req['total_mb']} MB, ≥{req['delay_seconds']} s apart",
        f"- User agent: `{req['user_agent']}`",
        "",
        "## Search results",
        "",
        f"- For-sale iPhones: **{search['match_count']}** across **{search['last_page']}** pages (docs per page {search['docs_per_page']})",
        f"- Full result set needs ~{search['estimated_requests_for_all_results']} search requests; duplicate ids across sampled pages: {search['duplicate_ids_across_pages']}",
        f"- Sampled {search['unique_docs_sampled']} listings. Coverage: " + ", ".join(f"{k} {pct(v)}" for k, v in search["coverage"].items()),
        f"- Price (EUR): {search['price_eur']}; zero prices: {search['price_zero']}; ≤20 €: {search['price_at_most_20']}",
        f"- Seller type: {search['seller_type']}",
        f"- Accessory-like titles (heuristic): {search['accessory_like_titles']}",
        f"- Memory values: {search['memory_size']}",
        "",
        "## Item pages",
        "",
        f"- Sampled {items['sampled']}, parsed {items['parsed_active']}, inactive {items['inactive_or_disposed']}, failures {len(items['failures'])}",
        "- Coverage: " + ", ".join(f"{k} {pct(v)}" for k, v in items["coverage"].items()),
        f"- Description length (chars): {items['description_chars']}",
        f"- Phone/email patterns scrubbed from descriptions: {items['pii_replacements_in_descriptions']}",
        f"- Condition: {items['condition']}",
        f"- Model group: {items['model_group']}",
        f"- Region: {items['region']} (postalName parts: {items['postal_name_parts']})",
        "",
        "## Privacy",
        "",
        f"- Stored record keys: {', '.join(s['privacy']['stored_keys'])}",
        f"- Forbidden keys present: {s['privacy']['forbidden_keys_present'] or 'none'}",
        f"- Minimized records: `{run_dir.relative_to(REPO_ROOT)}/` (git-ignored)",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
