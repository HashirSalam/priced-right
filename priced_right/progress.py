"""Show progress of an iPhone collection run.

    python3 -m priced_right.progress            # latest run, refreshes every 10 s (Ctrl-C to quit)
    python3 -m priced_right.progress --once     # print once
    python3 -m priced_right.progress data/raw/tori/iphones_<timestamp>
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "tori"


def count_lines(path: Path) -> int:
    return sum(1 for _ in path.open()) if path.exists() else 0


def status(run_dir: Path) -> str:
    total = count_lines(run_dir / "search_records.jsonl")
    parsed, failed = count_lines(run_dir / "item_records.jsonl"), count_lines(run_dir / "failures.jsonl")
    log_lines = (run_dir / "collect.log").read_text().splitlines() if (run_dir / "collect.log").exists() else []
    last = log_lines[-1] if log_lines else "(no log yet)"
    if not total:
        return f"{run_dir.name}: search pass in progress\n  last log: {last}"

    done = parsed + failed
    lines = [f"{run_dir.name}", f"  listing pages: {done}/{total} ({done / total:.1%})  parsed {parsed}, inactive/failed {failed}"]
    starts = [l for l in log_lines if "listing pass:" in l]
    if starts and done:
        started_at = datetime.fromisoformat(starts[-1].split()[0])
        already_done = int(starts[-1].split("listing pass: ")[1].split()[0])
        now = datetime.now(timezone.utc)
        fetched = done - already_done
        if fetched > 0:
            per_listing = (now - started_at).total_seconds() / fetched
            remaining = timedelta(seconds=per_listing * (total - done))
            finish = (now + remaining).astimezone()
            lines.append(f"  speed: {per_listing:.1f} s per listing, ~{remaining.seconds // 3600} h {remaining.seconds % 3600 // 60} min left, finishes ~{finish:%H:%M %Z}")
    lines.append(f"  last log: {last}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", nargs="?", type=Path, help="run directory (default: latest iphones_* run)")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--every", type=float, default=10.0, help="refresh interval in seconds")
    args = parser.parse_args()

    run_dir = args.run_dir or max(RAW_DIR.glob("iphones_*"), default=None)
    if run_dir is None:
        raise SystemExit(f"no iphones_* runs in {RAW_DIR}")
    while True:
        print(f"\n[{datetime.now():%H:%M:%S}] " + status(run_dir), flush=True)
        if args.once:
            break
        try:
            time.sleep(args.every)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
