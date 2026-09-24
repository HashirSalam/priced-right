# Priced Right?

[![tests](https://github.com/HashirSalam/priced-right/actions/workflows/tests.yml/badge.svg)](https://github.com/HashirSalam/priced-right/actions/workflows/tests.yml)

Estimating expected asking prices for second-hand listings.

Group: Abtaal Aatif, Hashir Salam Awan, Hafiz Khu. Javid

Sellers and buyers lack a reliable reference for second-hand asking prices. This project
learns an expected asking price for second-hand iPhones from comparable listings and tells
a user whether a listing sits below, in line with, or above it. Estimates reflect **asking
prices, not sale prices**: Tori never publishes what an item actually sold for, so every
claim in this project is about what sellers ask, and the report says so plainly.

Full plan: [docs/project-canvas.md](docs/project-canvas.md)

## Scope

**iPhones only.** The original plan covered phones and furniture with bicycles as a stretch
goal. We narrowed to one category because iPhones have a tight, well-defined comparable set:
Tori exposes model, storage size and a graded condition as coded attributes, so "comparable
listing" means something precise rather than a guess from free text. Categories without that
structure, clothing especially, leave brand and title text doing all the work and the residual
is mostly noise.

Narrowing also buys depth. One category collected properly beats three collected thinly, and
the interesting question is how much of the price spread is explained by the attributes Tori
already gives us.

## Roadmap

Where we are (updated 23 Sep). Tick items off below as they land; the full history is in [docs/project-log.md](docs/project-log.md).

```mermaid
flowchart LR
    subgraph done["Done · 17–23 Sep"]
        direction TB
        a["Repo and package<br/>17 Sep"] --> b["Tori crawler<br/>17 Sep"] --> c["Data: 2,178 iPhones<br/>17 Sep"] --> d["Privacy audit and fixes<br/>17 Sep"] --> s1["1. Preprocess and baselines<br/>23 Sep · Ridge RMSLE 0.26"]
    end
    subgraph next["Next · 23–27 Sep"]
        direction TB
        s2["2. EDA and Random Forest<br/>Up now · Wed–Fri"] --> s3["3. Search re-run<br/>Fri 25 · optional"] --> s4["4. Final model and app<br/>Sat 26 · MAPIE, fairness, Flask"] --> s5["5. Report and slides<br/>Sun 27"]
    end
    done --> next

    classDef done fill:#E1F5EE,stroke:#0F6E56,color:#085041
    classDef now fill:#EEEDFE,stroke:#534AB7,color:#3C3489
    classDef upcoming fill:#F1EFE8,stroke:#5F5E5A,color:#444441
    classDef optional fill:#F1EFE8,stroke:#5F5E5A,color:#444441,stroke-dasharray: 5 5
    class a,b,c,d,s1 done
    class s2 now
    class s4,s5 upcoming
    class s3 optional
    style done fill:none,stroke:#0F6E56
    style next fill:none,stroke:#534AB7
```

### Done

- [x] Repo, `priced_right` package, docs (17 Sep)
- [x] Tori crawler: robots.txt check, ≥3 s between requests, only needed fields, contact details scrubbed, pause/resume (17 Sep)
- [x] Full iPhone run: 2,178 listings in `data/raw/tori/iphones_2026-09-17T110158Z/listings.csv` ([report](docs/runs/iphones_2026-09-17T110158Z.md))
- [x] Privacy audit: missed contact details found and removed (see [privacy validation](docs/data-collection-notes.md#privacy-validation))
- [x] **1. Preprocess and baselines (23 Sep):** Ridge (text + fields) beats the median by model + storage; current numbers after the 24 Sep cleaning fixes: 2,007 clean listings, Ridge RMSLE 0.264 / 47 € / 13% vs. 0.367 / 56 € / 16% ([results](docs/results.md))

### Next

- [ ] **2. EDA and Random Forest (Wed–Fri):** prices by model, storage, condition, seller type and region; keyword associations; Random Forest (optionally gradient boosting)
  - [x] EDA: [notebooks/1.0-eda.ipynb](notebooks/1.0-eda.ipynb) (24 Sep). Main findings: model and storage drive price; retailers ask ~28% more for the same model; condition matters mainly for *fair* (−30%) and *needs repair* (−60%); battery and damage mentions matter.
  - [x] Fixed the 4 cleaning issues the EDA found: storage read as a model, spare parts at any price, bundles, iPhone SE generations (24 Sep)
  - [ ] Random Forest
- [ ] **3. Search re-run (Fri 25, optional):** `collect_iphones --max-items 0` (~42 requests) to see which listings disappeared since 17 Sep
- [ ] **4. Final model and app (Sat 26):** best model with MAPIE price ranges (stated coverage, e.g. 80%); fairness check of error and coverage by region and seller type; Flask app with seller and buyer modes
- [ ] **5. Report and slides (Sun 27):** methods, results, limitations ("asking prices, not sale prices")

The median baseline is grouped by model and storage. If a fitted model does not clearly beat
that lookup table, the finding is about the problem rather than about our modelling, and it
belongs in the report either way.

**Open decisions:** keep retailer listings with `seller_type` as a feature (recommended); run step 3 or not.

## Data source and collection policy

**Tori.fi.** Approved by the course supervisor.

Tori's terms restrict systematic collection without written permission, which we have not
requested. We proceed on the supervisor's approval and keep the collection deliberately
conservative so the footprint is small and the method is defensible:

- one request every 3 seconds, with jitter and exponential backoff on 429 and 5xx
- `robots.txt` checked at the start of every run and the run aborted if the search path is disallowed
- a `User-Agent` identifying the project with a working contact address
- search pages preferred over item pages wherever possible, since one request returns ~52 listings
- static attributes cached, so no listing is fetched twice
- no seller identifiers stored: Tori exposes a persistent `ownerId` on every ad and we drop it

See [docs/data-collection-notes.md](docs/data-collection-notes.md) for the crawler rules and
how Tori exposes its data, and [docs/data-dictionary.md](docs/data-dictionary.md) for the
fields we collect and what we deliberately leave out.

## Setup

Requires Python 3.11+ (3.13 recommended). From the repo root:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[notebook,dev]"
```

This installs the project in editable mode, so `import priced_right` works from notebooks, scripts and the app. The optional extras are `notebook` (JupyterLab) and `dev` (pytest, ruff).

To get the exact versions the group uses, install from the lock file:

```bash
pip install -r requirements-lock.txt
pip install -e . --no-deps
```

Run the checks before opening a PR:

```bash
uv run ruff check priced_right tests
uv run pytest
```

GitHub Actions runs the same two checks on every PR and on `main` ([workflow](.github/workflows/tests.yml)), installing the exact versions from `requirements-lock.txt`.

After adding or upgrading a dependency in `pyproject.toml`, refresh the lock file with `pip freeze --exclude-editable > requirements-lock.txt` and commit both files.

## Project structure

```
priced-right/
├── README.md                        overview, setup, collection policy
├── pyproject.toml                   dependencies and package config
├── requirements-lock.txt            exact package versions for the group
│
├── priced_right/                    all Python code, one package
│   ├── tori.py                      Tori client: requests, robots.txt, parsing, privacy filter
│   ├── collect_iphones.py           full iPhone collection (search + listing pages)
│   ├── progress.py                  live progress of a running collection
│   ├── preprocess.py                cleaning and derived features
│   ├── evaluate.py                  GroupKFold scoring shared by all models
│   └── models.py                    median baseline, Ridge; writes docs/results.md
│
├── notebooks/
│   ├── 1.0-eda.ipynb                exploratory data analysis (documented, with charts)
│   └── 0.0-team-first-look.ipynb    the team's first exploration, kept for history
│
├── tests/                           parser and model tests (uv run pytest)
├── .github/workflows/tests.yml      lint + tests on every PR
│
├── docs/
│   ├── project-canvas.md            the mini project canvas
│   ├── data-dictionary.md           fields we collect, why, and what we leave out
│   ├── data-collection-notes.md     crawler rules and how Tori exposes its data
│   ├── results.md                   cleaning funnel and model comparison (generated)
│   ├── project-log.md               dated history of work and decisions
│   └── runs/                        generated report for every run (committed)
│
└── data/                            collected data (committed)
    ├── raw/tori/iphones_<time>/     records, listings.csv, failures, log
    └── processed/                   iphones_clean.csv, cleaning_log.json (rebuilt by preprocess.py)
```

How the pieces fit together:

```mermaid
flowchart TB
    tori[("Tori.fi")] -->|search + listing pages| client["priced_right/tori.py<br/>requests · robots.txt<br/>parsing · privacy filter"]
    client --> collect["priced_right/collect_iphones.py"]
    collect --> raw["data/raw/tori/…/listings.csv<br/>committed"]
    collect --> reports["docs/runs/ report<br/>committed"]
    raw --> prep["priced_right/preprocess.py"]
    prep --> clean["data/processed/iphones_clean.csv"]
    clean --> models["priced_right/models.py<br/>+ evaluate.py"]
    models --> results["docs/results.md"]
    models -.-> planned["Flask app<br/>planned"]

    classDef code fill:#EEEDFE,stroke:#534AB7,color:#3C3489
    classDef data fill:#E1F5EE,stroke:#0F6E56,color:#085041
    classDef todo fill:#F1EFE8,stroke:#5F5E5A,color:#444441,stroke-dasharray: 5 5
    class client,collect,prep,models code
    class raw,reports,clean,results data
    class planned todo
```

Add folders only when there is something to put in them. When they are needed, follow the [Cookiecutter Data Science](https://cookiecutter-data-science.drivendata.org/) conventions:

- `notebooks/`: numbered with initials, e.g. `1.0-hsa-eda.ipynb`, `2.0-aa-baseline.ipynb`
- `models/`: saved fitted pipelines for the app
- `reports/figures/`: figures for the report
- `data/processed/`: cleaned data, always rebuilt by code from `data/raw/`, which is never edited by hand

`data/` is committed so the whole group works from the same dataset. Listing descriptions are
free text written by sellers, so **the repository must stay private**. A full iPhone run is about
5 MB; three weeks of daily snapshots would run to hundreds of megabytes, so revisit this before
daily collection starts.

## Data collection

Current scope: for-sale iPhone listings.

Collection runs in two stages, because they cost very differently:

**Search sweep.** Paginates the category and returns roughly 52 listings per request,
carrying price, title, location, listing age and the attribute chips. Cheap, so it runs on
every collection pass.

**Item enrichment.** One request per listing, returning the fields the search pages do not
carry: graded condition, model, storage, description, postal code and region. These never
change after a listing is posted, so each listing is fetched exactly once and cached; repeat
runs only pay for listings that appeared since the last pass.

Run from the repo root. The collection code uses only the standard library and also runs on Python 3.9. A full iPhone collection (~2 h) writes `data/raw/tori/iphones_<timestamp>/listings.csv`:

```bash
python3 -m priced_right.collect_iphones
```

## Why the daily cadence matters

Every pass writes a dated snapshot. Stacking them recovers how long each listing stayed live,
which is the only signal available on whether a price was one people acted on. That history
cannot be reconstructed after the fact: a listing that disappears is simply gone, and nothing
in Tori's data says when it went or why.

Disappearance is not the same as sold. A listing can vanish because it sold, because the
seller withdrew it, or because it expired, and nothing distinguishes those from outside. Any
use we make of it says so.
