"""Clean the collected iPhone listings and derive model features.

Reads the latest collection run and writes one row per usable listing:
    data/processed/iphones_clean.csv   cleaned listings with derived features (no ad text)
    data/processed/iphones_text.csv    their titles and descriptions (local only, git-ignored)
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
# Free text written by sellers: kept out of the public repository, so stored separately
TEXT_COLUMNS = ["title", "description"]

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
# Two models joined by "/" ("iPhone 12/ 12 pro max"): unclear which phone is for sale
MULTI_MODEL_RE = re.compile(r"phone\s*(?:\d{1,2}|se|xr|xs|x)[a-z ]*\s*/\s*(?:\d{1,2}|se|xr|xs|x|pro|max|plus|mini)\b", re.I)
# Spare parts, dropped at any price: an original screen or camera can cost more than 40 €.
PART_RE = re.compile(
    r"takakamera|etukamera|kamera\s*moduul|kameramoduul|emolevy|näyttömoduul|laturiportti|latausportti"
    r"|\boled\b|\blcd\b|\bvaraosa\b|näyttöjä",
    re.I,
)

# "iPhone 15 Pro Max", "iphone13mini", "Phone 12", "iPhone XS Max", "iPhone 16e", "iPhone Air", "iPhone SE3"
_MODEL_RE = re.compile(
    r"\b(?:i\s?-?)?phone\s*(se(?:2016|2020|2022|16|20|22|[1-3])?|xr|xs|x|air|\d{1,2})(?!\d)(?!\s*(?:gb|gt|tb|tt)\b)"  # "iPhone 16 GB" = storage
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
# iPhone SE generations: 1st 2016, 2nd 2020, 3rd 2022 (the only 5G SE). Explicit markers first, then years.
_SE_NAMES = {1: "iPhone SE (1st gen)", 2: "iPhone SE (2nd gen)", 3: "iPhone SE (3rd gen)"}
_SE_SUFFIX_GEN = {"1": 1, "16": 1, "2016": 1, "2": 2, "20": 2, "2020": 2, "3": 3, "22": 3, "2022": 3}  # "SE3", "SE20", "SE2022"
_TORI_SE_LABEL_RE = re.compile(r"\(?\s*2\s*-\s*3\s*gen\s*\)?", re.I)  # Tori's bucket label "(2-3 gen)", not a generation
_SE_INFO = {"iPhone SE": (2020, "iPhone SE (2-3 gen)"), "iPhone SE (1st gen)": (2016, "iPhone 2G-11"),
            "iPhone SE (2nd gen)": (2020, "iPhone SE (2-3 gen)"), "iPhone SE (3rd gen)": (2022, "iPhone SE (2-3 gen)")}
_SE_MARKERS = [
    (3, re.compile(r"\bse\s?3\b|\b3rd\b|\b3\.?\s*(?:gen|sukupolvi)|(?:gen(?:eration)?|sukupolvi)\.?\s*3\b|\b5g\b", re.I)),
    (2, re.compile(r"\bse\s?2\b|\b2nd\b|\b2\.?\s*(?:gen|sukupolvi)|(?:gen(?:eration)?|sukupolvi)\.?\s*2\b", re.I)),
    (1, re.compile(r"\bse\s?1\b|\b1st\b|\b1\.?\s*(?:gen|sukupolvi)|(?:gen(?:eration)?|sukupolvi)\.?\s*1\b|ensimmäi", re.I)),
]
_SE_YEARS = [(3, re.compile(r"\b2022\b")), (2, re.compile(r"\b2020\b")), (1, re.compile(r"\b2016\b"))]
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
# Mention flags: (keyword pattern, words right after it that cancel it). A keyword also doesn't count
# when a negator comes shortly before it in the same clause ("ei halkeamia" = no cracks), see mentions().
_GONE_RE = re.compile(r"puuttu|hukassa|hukattu|kadon|heitetty|missing|lost", re.I)
_FLAGS = {
    "mentions_warranty": (re.compile(r"takuu|warranty", re.I),
                          re.compile(r"loppu|umpeutu|päätty|mennyt|vanhentu|expired|ended", re.I)),
    "mentions_receipt": (re.compile(r"kuitti|receipt", re.I), _GONE_RE),
    "mentions_box": (re.compile(r"pakkaus|laatikko|\bbox\b", re.I), _GONE_RE),
    # "vaurioton" (undamaged) and "halkeamaton" (crack-free) must not count as damage
    "mentions_damage": (re.compile(r"rikki|halkea(?!maton)|haljen|särö|lohkea(?!maton)|vaurio(?!ton)|broken|crack", re.I), None),
}
_NEGATORS = {"ei", "eikä", "ilman", "no", "not", "without", "never"}
_NEGATED_EXISTENCE = {"ole", "ollut", "löydy", "ilmene"}  # "halkeamia ei ole" = there are no cracks
_SENTENCE_END_RE = re.compile(r"[.;:!?\n]")
_CONNECTORS = {"ja", "tai", "eikä", "and", "or", "nor"}
_WORD_RE = re.compile(r"\w+")


def load_clean() -> pd.DataFrame:
    """The cleaned listings written by this module (run it first)."""
    return pd.read_csv(PROCESSED_DIR / "iphones_clean.csv", dtype={"listing_id": str})


def load_text() -> pd.DataFrame:
    """Titles and descriptions of the cleaned listings, keyed by listing_id (local only)."""
    path = PROCESSED_DIR / "iphones_text.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path.relative_to(REPO_ROOT)} is missing: ad text is not in the repository. "
                                "preprocess writes it from the local raw listings, which only the collectors have")
    return pd.read_csv(path, dtype={"listing_id": str})


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
        if series.startswith("se"):
            generation = _SE_SUFFIX_GEN.get(series[2:]) or se_generation(text)
            found.append(_SE_NAMES.get(generation, "iPhone SE"))
            continue
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


def se_generation(text: str, use_years: bool = True) -> Optional[int]:
    """1, 2 or 3 for "SE 2", "2nd gen", "3. sukupolvi", "5G", "SE 2022"; None if unclear.

    Years are only trusted in titles: a description's "2022" may be when the phone was bought.
    """
    text = _TORI_SE_LABEL_RE.sub(" ", text or "")
    markers = _SE_MARKERS + (_SE_YEARS if use_years else [])
    for generation, pattern in markers:
        if pattern.search(text or ""):
            return generation
    return None


def model_info(model: str) -> tuple[int, str]:
    """(release year, Tori model group) for a name returned by parse_model."""
    if model in _SE_INFO:
        return _SE_INFO[model]
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


def mentions(text: str, pattern: re.Pattern, gone_after: Optional[re.Pattern] = None) -> bool:
    """True if the keyword appears at least once without being negated.

    A match doesn't count when, within the same clause:
    - a negator is among the 4 words before it: "ei halkeamia", "ei ole yhtään säröjä", "ilman laatikkoa"
    - it is followed by "ei ole" and similar: "halkeamia ei ole" (there are no cracks)
    - it is followed by a word meaning gone or ended (`gone_after`): "takuu päättyi", "kuitti hukassa"
    """
    text = text or ""
    for match in pattern.finditer(text):
        start, end = match.start(), match.end()
        while start > 0 and text[start - 1].isalnum():  # widen to whole words: "halkea" in "halkeamia"
            start -= 1
        while end < len(text) and text[end].isalnum():
            end += 1
        before = _SENTENCE_END_RE.split(text[max(0, start - 120):start])[-1]
        after = _SENTENCE_END_RE.split(text[end:end + 60])[0].split(",")[0]
        words_after = [w.lower() for w in _WORD_RE.findall(after)][:3]
        if _negated_before(before, pattern):
            continue
        if words_after[:1] == ["ei"] and set(words_after[1:2]) & _NEGATED_EXISTENCE:
            continue
        if gone_after and any(gone_after.match(w) for w in words_after):
            continue
        return True
    return False


def _negated_before(before: str, pattern: re.Pattern) -> bool:
    """A negator among the 4 words before, or at the start of a list of the same kind of words:
    "ei säröjä, lohkeamia, halkeamia" negates all three, "ei vaihtoja, halkeama" negates nothing."""
    segments = before.split(",")
    if _NEGATORS & {w.lower() for w in _WORD_RE.findall(segments[-1])[-4:]}:
        return True
    for segment in reversed(segments[:-1]):
        words = [w.lower() for w in _WORD_RE.findall(segment) if w.lower() not in _CONNECTORS]
        if not words:
            continue
        if words[0] in _NEGATORS and words[1:] and all(pattern.search(w) for w in words[1:]):
            return True  # "ei säröjä" opens the list
        if not all(pattern.search(w) for w in words):
            return False  # not a list of the same kind of words
    return False


def mention_flags(text: str) -> dict[str, bool]:
    """All mention flags for one listing's title + description."""
    return {name: mentions(text, pattern, gone) for name, (pattern, gone) in _FLAGS.items()}


def strip_prices(text: str) -> str:
    """Remove prices ("750 €", "250e", "Hinta: 180") so text models can't read the asking price.

    Not used in cleaning; apply it to title/description before building text features.

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
    drop(df["title"].str.contains(PART_RE), "spare parts (camera, screen, …) at any price")
    drop(df["title"].map(lambda t: len(set(_models_in(t))) > 1) | df["title"].str.contains(MULTI_MODEL_RE)
         | df["title"].str.contains(NOT_A_PHONE_RE),
         "bundles (several models, or an iPhone with other devices)")

    from_title = df["title"].map(parse_model)
    from_description = df["description"].map(model_from_description)
    df["exact_model"] = from_title.fillna(from_description)
    # An SE without a generation in the title: take it from the description's explicit markers
    unknown_se = df["exact_model"].eq("iPhone SE")
    from_description_se = df.loc[unknown_se, "description"].map(lambda d: _SE_NAMES.get(se_generation(d, use_years=False)))
    df.loc[unknown_se, "exact_model"] = from_description_se.fillna("iPhone SE")
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
    flags = [mention_flags(t + "\n" + d) for t, d in zip(df["title"], df["description"], strict=True)]
    for name in _FLAGS:
        df[name] = [f[name] for f in flags]

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
    listings_path = run_dir / "listings.csv"
    if not listings_path.exists():
        raise SystemExit(f"{listings_path} is missing: raw listings hold ad text and stay local. "
                         "data/processed/iphones_clean.csv is committed, so skip this step.")
    raw = pd.read_csv(listings_path, dtype={"listing_id": str})
    df, log = clean(raw)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.drop(columns=TEXT_COLUMNS).to_csv(PROCESSED_DIR / "iphones_clean.csv", index=False)
    df[["listing_id", *TEXT_COLUMNS]].to_csv(PROCESSED_DIR / "iphones_text.csv", index=False)
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
