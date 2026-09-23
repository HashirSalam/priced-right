# Project log

What was done, what was decided and why, in date order. Add a dated entry when work lands.

## 17 Sep: data collection

**Setup**
- Wrote up the mini project canvas in [project-canvas.md](project-canvas.md) and created the private repo (`459c05c`).
- Tried Crawl4AI (a headless-browser crawler) in Docker. Tori listings render inside shadow DOM, so a default crawl came back empty. It works with `flatten_shadow_dom`, but it turned out not to be needed (see below).

**How we collect from Tori**
- Tori embeds each page's data as JSON: base64 on search pages, a `JSON.parse("…")` string on listing pages. Plain HTTP requests are enough, with no browser (`82e66ac`).
- Crawler rules: check robots.txt (with a wildcard-aware parser, because Python's built-in one allows `/profile*` and `/map*`), at least 3 s between requests, an honest user agent, and storing only the fields in [data-dictionary.md](data-dictionary.md).
- A small feasibility test (experiment 01, 14 requests) confirmed the fields and pagination. It was later removed (`d55f787`); its filter IDs are kept in [data-collection-notes.md](data-collection-notes.md).

**Full collection**
- Built `collect_iphones.py` (`44875c6`): search pages, then one listing page per result, joined into `listings.csv`. It can pause and resume, and stops on HTTP 403/429.
- Mid-run fix (`52e4927`): read timeouts on Python 3.9 would have stopped the run; they now skip the listing. Added a clean pause (`kill`) and a live progress view.
- Run `iphones_2026-09-17T110158Z`: 2,195 iPhones found, **2,178 collected**, 17 removed or inactive during the run. It took about 2.5 h at ~3.8 s per listing ([report](runs/iphones_2026-09-17T110158Z.md), `dad9a23`).

**Repo and team**
- Abtaal revised the README (`f1e82fe`): iPhones only, Tori collection approved by the course supervisor, and a plan for daily snapshots.
- Added `pyproject.toml` and `requirements-lock.txt` (`523ee34`), flattened the layout into one `priced_right/` package (`3f375ad`), and added README diagrams.
- `data/` is committed so the group shares one dataset. The repo must stay private.
- Replaced the 5-week plan with a two-weekend roadmap (`612e9e1`).

**Audit** (`9e75c5d`)
- The contact scrubber had missed 10 phone numbers (WhatsApp links, `358…`, foreign and disguised formats) and 1 personal website. The pattern was extended and the saved data re-scrubbed offline, without new requests.
- The collector no longer marks temporary server errors (5xx) as permanent failures.
- Only 1 of the 3 "Galaxy" listings is a Samsung; the other 2 are mis-tagged iPhones.
- Added from common practice: train on log price with RMSLE, keep preprocessing inside `GroupKFold`, and MAPIE price ranges.

## 23 Sep: first models

**Setup**
- The project joined the shared UOH uv workspace (`uv run …`); pip users install from `requirements-lock.txt`.
- Made the README diagrams readable on GitHub (`6fd6cb6`, `833e61d`).

**Step 1: preprocessing and baselines** (PR #1, `29662cf`)
- `preprocess.py`: 2,178 → **2,015 listings** after removing 0 € and placeholder prices, accessories and spare parts, non-iPhones, multi-phone lots, ads with no single model, and implausibly low prices ([funnel](results.md)).
- Derived features: exact model (48 models; read from the title for 99% of listings), release year, storage (96%), battery % (51%), warranty/receipt/box/damage mentions, listing age, and a relisting group.
- `evaluate.py`: 5-fold `GroupKFold` on log price, so copies of an ad never end up in both training and test data. Metrics: RMSLE, MAE in €, median % error.
- `models.py` results:

  | Model | RMSLE | MAE | Median % error |
  |---|---|---|---|
  | Overall median | 0.908 | 200 € | 54% |
  | Median by model + storage | 0.378 | 58 € | 17% |
  | Ridge (text + fields) | **0.280** | **49 €** | **13%** |

- Codex reviewed the PR and made 3 comments, all fixed:
  - prices written in ad text are removed before TF-IDF, since 10% of ads repeat their own price (target leakage)
  - scikit-learn ≥ 1.6 is now required
  - "SE3" titles are recognised, and a description is only used when it names exactly one model
- 53 tests (`uv run pytest`).

**GitHub workflow**
- GitHub Actions runs lint and tests on every PR and on `main` (about 75 s).
- A ruleset on `main` requires a pull request (self-merge allowed), squash merging, the **lint and tests** check, an up-to-date branch, and all review conversations resolved. It also blocks force pushes and deletion, and requests Copilot review automatically. Repository admins can bypass it.

## Decisions

| Decision | Why | When |
|---|---|---|
| iPhones only | Coded model, storage and condition make "comparable listing" precise | 17 Sep |
| Tori over plain HTTP, not a browser | Embedded JSON is faster, more reliable and lighter on the site | 17 Sep |
| Store only needed fields; scrub contact details | Data minimisation (canvas, GDPR) | 17 Sep |
| Commit `data/` to the private repo | Everyone works from the same dataset | 17 Sep |
| Log price, RMSLE, GroupKFold | Standard for price prediction; stops copies of an ad from leaking between folds | 17 Sep |
| Flask for the app | Committed in the canvas; simple server-rendered forms | 23 Sep |
| All changes through PRs | Review, tests and history for every change | 23 Sep |

## Open

- Keep retailer listings (20%) with `seller_type` as a feature? (recommended)
- Friday search-only re-run to see which listings disappeared?
- The README collection policy describes collector features not built yet (backoff, contact address, incremental fetching). Waiting for Abtaal.
- Next: step 2, EDA notebook and Random Forest.
