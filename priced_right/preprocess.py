"""Clean the collected iPhone listings and derive model features.

Reads the latest collection run and writes one row per usable listing:
    data/processed/iphones_clean.csv   cleaned listings with derived features
    data/processed/cleaning_log.json   rows removed at each cleaning step

Run from the repository root:
    uv run python -m priced_right.preprocess
    uv run python -m priced_right.preprocess --run data/raw/tori/iphones_2026-09-17T110158Z

Feature definitions: docs/data-dictionary.md ("Derived in preprocessing").
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "tori"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

ACCESSORY_MAX_PRICE = 40  # accessory words in a pricier title usually mean "phone + case"
# Accessories and spare parts. Substrings, not whole words, because Finnish compounds them:
# "silikonikuori", "lompakkokotelo", "suojakalvo", "varanäyttö".
ACCESSORY_RE = re.compile(
    r"kuor(?:i|et|ia|en)|kotelo|suoja|panssarilasi|kalvo|takakan|takalasi|laturi|kaapeli|johto|adapter|magsafe|skini"
    r"|varaos|varanäyt|näytöt|oled|lcd|raato|laatikko|\bakku\b(?!\s*\d)|\bcase\b|\bcover\b|protect|charger|cable",
    re.I,
)
PLACEHOLDER_MAX_PRICE = 5  # 1-4 € asks are placeholders ("make an offer"), not prices
IMPLAUSIBLE_SHARE = 0.10  # under 10% of the model's median price, with no damage or parts mentioned
DAMAGED_OR_PARTS_RE = re.compile(r"rikki|rikkinäi|viallin|varaos|korjau|lukittu|icloud|ei toimi|broken|parts|raato", re.I)
# No trailing \b: Finnish inflects brand names ("Androidin", "Samsungin").
NOT_A_PHONE_RE = re.compile(r"\b(?:ipad|watch|airpods|macbook|imac|samsung|galaxy|android|huawei|xiaomi)", re.I)
LOT_RE = re.compile(r"\b\d+\s*kpl\b", re.I)  # "2 kpl" = 2 pieces: the price covers several phones

# "iPhone 15 Pro Max", "iphone13mini", "Phone 12", "iPhone XS Max", "iPhone 16e", "iPhone Air", "iPhone SE3"
_MODEL_RE = re.compile(
    r"\b(?:i\s?-?)?phone\s*(se[1-3]?|xr|xs|x|air|\d{1,2})(?!\d)"
    r"(?:(s|e|c)(?![a-z]))?"
    r"\s*(pro\s*max|promax|pro|max|plus|mini|air)?",
    re.I,
)
# "Apple 15 pro max 256GB": no "iPhone", so require a variant to avoid "Apple watch 7"
_APPLE_MODEL_RE = re.compile(r"\bapple\s+(1[1-7])\s*(pro\s*max|promax|pro|max|plus|mini)\b", re.I)

# series -> (release year, Tori model group)
_SERIES = {
    "3": (2008, "iPhone 2G-11"), "4": (2010, "iPhone 2G-11"), "5": (2012, "iPhone 2G-11"),
    "6": (2014, "iPhone 2G-11"), "7": (2016, "iPhone 2G-11"), "8": (2017, "iPhone 2G-11"),
    "x": (2017, "iPhone 2G-11"), "xr": (2018, "iPhone 2G-11"), "xs": (2018, "iPhone 2G-11"),
    "11": (2019, "iPhone 2G-11"), "se": (2020, "iPhone SE (2-3 gen)"),
    "12": (2020, "iPhone 12/Mini/Plus/Pro/Max"), "13": (2021, "iPhone 13/Mini/Plus/Pro/Max"),
    "14": (2022, "iPhone 14/Mini/Plus/Pro/Max"), "15": (2023, "iPhone 15/Plus/Pro/Max"),
    "16": (2024, "iPhone 16/Plus/Pro/Max"), "17": (2025, "iPhone 17/Air/Pro/Max"),
    "air": (2025, "iPhone 17/Air/Pro/Max"),
}
_SUFFIX_YEAR_OFFSET = {"s": 1, "c": 1, "e": 1}  # 6s = 2015, 5c = 2013, 16e = 2025
_VARIANTS = {"promax": "Pro Max", "pro max": "Pro Max", "pro": "Pro", "max": "Max", "plus": "Plus", "mini": "Mini", "air": "Air"}
# Variants Apple actually sold; others ("XR Max", "SE Pro") are dropped to the base model.
_VALID_VARIANTS = {
    "6": {"Plus"}, "7": {"Plus"}, "8": {"Plus"}, "xs": {"Max"},
    "11": {"Pro", "Pro Max"}, "12": {"Mini", "Pro", "Pro Max"}, "13": {"Mini", "Pro", "Pro Max"},
    "14": {"Plus", "Pro", "Pro Max"}, "15": {"Plus", "Pro", "Pro Max"}, "16": {"Plus", "Pro", "Pro Max"},
    "17": {"Pro", "Pro Max"},
}

_STORAGE_GB = {8, 16, 32, 64, 128, 256, 512, 1024, 2048}
_STORAGE_RE = re.compile(r"(?<![\d.,])(\d{1,4})\s*(gb|gt|tb|tt)\b", re.I)
_BATTERY_RE = re.compile(
    r"(?:akku\w*|akun\s+(?:kunto|kapasiteetti)|battery(?:\s+(?:health|capacity))?)\D{0,25}?(\d{2,3})\s*%"
    r"|(\d{2,3})\s*%\s*(?:akku|battery)",
    re.I,
)
_PRICE_RE = re.compile(
    r"(?:\b(?:hinta|hintapyyntö|hp|price)\w*\s*:?\s*)?"
    r"(?<![\d.,])\d{1,4}(?:[ .]\d{3})?(?:[.,]\d{1,2})?\s*(?:€|eur\w*|euro\w*|(?P<e>e)\b)"
    r"|\b(?:hinta|hintapyyntö|hp|price)\w*\s*:?\s*\d{1,4}(?:[ .]\d{3})?\b",
    re.I,
)
_FLAGS = {
    "mentions_warranty": re.compile(r"takuu|warranty", re.I),
    "mentions_receipt": re.compile(r"kuitti|receipt", re.I),
    "mentions_box": re.compile(r"pakkaus|laatikko|\bbox\b", re.I),
    # "vaurioton" (undamaged) and "halkeamaton" (crack-free) must not count as damage
    "mentions_damage": re.compile(r"rikki|halkea(?!maton)|haljen|särö|vaurio(?!ton)|broken|crack", re.I),
}


def latest_run(raw_dir: Path = RAW_DIR) -> Path:
    runs = sorted(raw_dir.glob("iphones_*"))
    if not runs:
        raise SystemExit(f"no collection runs in {raw_dir}")
    return runs[-1]


def _models_in(text: str) -> list[str]:
    """Every valid model named in the text, in order of appearance."""
    found = []
    for match in _MODEL_RE.finditer(text or ""):
        series, suffix, variant = (g.lower() if g else "" for g in match.groups())
        series = "se" if series.startswith("se") else series  # "SE3" = 3rd-generation SE
        if series not in _SERIES:
            continue  # e.g. "iPhone 64GB": 64 is storage, not a model
        if series == "air" or variant == "air":
            found.append("iPhone Air")  # sold as "iPhone Air", sometimes listed as "iPhone 17 Air"
            continue
        name = "iPhone " + (series.upper() if series.isalpha() else series + suffix)
        display = _VARIANTS[re.sub(r"\s+", " ", variant)] if variant else ""
        if display in _VALID_VARIANTS.get(series, set()) and suffix != "e":
            name += " " + display
        found.append(name)
    for match in _APPLE_MODEL_RE.finditer(text or ""):
        variant = _VARIANTS[re.sub(r"\s+", " ", match.group(2).lower())]
        found.append(f"iPhone {match.group(1)} {variant}")
    return found


def parse_model(text: str) -> Optional[str]:
    """Normalized model name, e.g. "iPhone 15 Pro Max": the first valid model named in the text, or None."""
    models = _models_in(text)
    return models[0] if models else None


def model_from_description(text: str) -> Optional[str]:
    """Model from a description only if it names exactly one: descriptions often compare with
    other models ("same chip as iPhone 14") or list a bundle of phones."""
    models = set(_models_in(text))
    return models.pop() if len(models) == 1 else None


def model_info(model: str) -> tuple[int, str]:
    """(release year, Tori model group) for a name returned by parse_model."""
    token = model.split()[1].lower()
    if token == "air":
        return _SERIES["air"]
    series = token.rstrip("sce") if token[:-1].isdigit() else token
    year, group = _SERIES[series]
    return year + (_SUFFIX_YEAR_OFFSET.get(token[-1], 0) if series != token else 0), group


def parse_storage_gb(*texts: str) -> Optional[int]:
    """First plausible storage size in GB ("128 GB", "256Gt", "1 TB") across the texts, in order."""
    for text in texts:
        for number, unit in _STORAGE_RE.findall(text or ""):
            gb = int(number) * (1024 if unit.lower() in ("tb", "tt") else 1)
            if gb in _STORAGE_GB:
                return gb
    return None


def parse_battery_pct(text: str) -> Optional[int]:
    for match in _BATTERY_RE.finditer(text or ""):
        value = int(match.group(1) or match.group(2))
        if 50 <= value <= 100:
            return value
    return None


def strip_prices(text: str) -> str:
    """Remove prices ("750 €", "250e", "Hinta: 180") so text features can't read the asking price.

    "16e" right after "iPhone" is a model name (iPhone 16e), not a price, and is kept.
    """
    def replace(match: re.Match) -> str:
        before = text[max(0, match.start() - 7):match.start()].lower()
        return match.group(0) if match.group("e") and before.rstrip().endswith("phone") else " "
    return _PRICE_RE.sub(replace, text or "")


def relisting_key(title: str, description: str) -> str:
    """Same title and description opening means the same ad posted again (or a shop's template)."""
    normalize = lambda s: re.sub(r"\W+", " ", (s or "").lower()).strip()
    return normalize(title) + "|" + normalize(description)[:120]


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Drop unusable rows step by step and derive features. Returns (clean data, cleaning log)."""
    df = raw.copy()
    df["title"] = df["title"].fillna("")
    df["description"] = df["description"].fillna("")
    log = [{"step": "collected listings", "removed": 0, "rows": len(df)}]

    def drop(mask: pd.Series, step: str) -> None:
        nonlocal df
        log.append({"step": step, "removed": int(mask.sum()), "rows": int((~mask).sum())})
        df = df[~mask].copy()

    drop(df["price_eur"] <= 0, "price 0 € (swap offers)")
    drop(df["price_eur"] < PLACEHOLDER_MAX_PRICE, f"placeholder price (under {PLACEHOLDER_MAX_PRICE} €)")
    drop(df["title"].str.contains(ACCESSORY_RE) & (df["price_eur"] < ACCESSORY_MAX_PRICE),
         f"accessories and spare parts (under {ACCESSORY_MAX_PRICE} €)")
    drop(df["title"].str.contains(NOT_A_PHONE_RE) & ~df["title"].str.contains(r"iphone", case=False),
         "not an iPhone (iPad, Watch, Samsung, …)")
    drop(df["title"].str.contains(LOT_RE), 'several phones in one ad ("2 kpl")')

    from_title = df["title"].map(parse_model)
    from_description = df["description"].map(model_from_description)
    df["exact_model"] = from_title.fillna(from_description)
    drop(df["exact_model"].isna(), "no single iPhone model in title or description")

    model_median = df.groupby("exact_model")["price_eur"].transform("median")
    damaged = (df["title"] + " " + df["description"]).str.contains(DAMAGED_OR_PARTS_RE)
    drop((df["price_eur"] < IMPLAUSIBLE_SHARE * model_median) & ~damaged,
         f"implausibly low price (under {IMPLAUSIBLE_SHARE:.0%} of model median, not damaged)")

    info = df["exact_model"].map(model_info)
    df["release_year"] = info.map(lambda x: x[0])
    tori_group_missing_or_wrong = df["model_group"].isna() | ~df["model_group"].fillna("").str.startswith("iPhone")
    df["model_group_filled"] = tori_group_missing_or_wrong
    df["model_group"] = info.map(lambda x: x[1])  # consistent with exact_model; fixes the mis-tagged "Galaxy" iPhones

    df["storage_gb"] = [parse_storage_gb(m, t, d) for m, t, d in zip(df["memory"].fillna(""), df["title"], df["description"], strict=True)]
    df["battery_pct"] = [parse_battery_pct(t + " " + d) for t, d in zip(df["title"], df["description"], strict=True)]
    for name, pattern in _FLAGS.items():
        df[name] = (df["title"] + " " + df["description"]).str.contains(pattern)

    published = pd.to_datetime(df["published_at"], utc=True)
    collected = pd.to_datetime(df["collected_at"], utc=True)
    df["listing_age_days"] = (collected - published).dt.days
    df["relisting_group"] = pd.factorize(pd.Series([relisting_key(t, d) for t, d in zip(df["title"], df["description"], strict=True)]))[0]

    columns = [
        "listing_id", "price_eur", "title", "description",
        "exact_model", "model_group", "model_group_filled", "release_year", "storage_gb", "condition", "battery_pct",
        "mentions_warranty", "mentions_receipt", "mentions_box", "mentions_damage",
        "seller_type", "shipping_available", "municipality", "region",
        "listing_age_days", "relisting_group", "published_at", "collected_at",
    ]
    df["storage_gb"] = df["storage_gb"].astype("Int64")
    df["battery_pct"] = df["battery_pct"].astype("Int64")
    return df[columns].reset_index(drop=True), log


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, help="collection run directory (default: latest)")
    args = parser.parse_args()

    run_dir = (args.run or latest_run()).resolve()
    raw = pd.read_csv(run_dir / "listings.csv", dtype={"listing_id": str})
    df, log = clean(raw)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_DIR / "iphones_clean.csv", index=False)
    coverage = {c: round(float(df[c].notna().mean()), 3) for c in ("storage_gb", "battery_pct", "condition")}
    (PROCESSED_DIR / "cleaning_log.json").write_text(json.dumps({
        "source_run": run_dir.name,
        "steps": log,
        "coverage": coverage,
        "model_group_filled_from_title": int(df["model_group_filled"].sum()),
        "distinct_models": int(df["exact_model"].nunique()),
        "relisting_groups_with_copies": int((df["relisting_group"].value_counts() > 1).sum()),
    }, ensure_ascii=False, indent=2) + "\n")

    for step in log:
        print(f"{step['step']:45} -{step['removed']:>4}  → {step['rows']}")
    print(f"coverage: {coverage} | distinct models: {df['exact_model'].nunique()}")
    print(f"wrote {(PROCESSED_DIR / 'iphones_clean.csv').relative_to(REPO_ROOT)} ({len(df)} rows)")


if __name__ == "__main__":
    main()
