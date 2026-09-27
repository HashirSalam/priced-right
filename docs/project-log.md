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
- `preprocess.py`: 2,178 → **2,015 listings** after removing 0 € and placeholder prices, accessories and spare parts, non-iPhones, multi-phone lots, ads with no single model, and implausibly low prices (funnel (`docs/results.md`, removed 27 Sep, in git history)).
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

## 24 Sep: exploratory data analysis

- The team's first exploration (`data/processed/Untitled.ipynb`) was folded into the EDA notebook below and then removed; it stays in git history (commit 4274f3b).
- Wrote [notebooks/1.0-eda.ipynb](../notebooks/1.0-eda.ipynb): 10 documented sections, each saying what we look at and why, followed by the result and a takeaway. It compares groups with a **relative price**: price ÷ the median of the same model and storage (after a Codex review pointed out that storage mixes differ between groups), so the phone itself doesn't hide other effects.
- Findings:
  - price is right-skewed, which supports log price
  - model/release year and storage dominate (Spearman 0.89 and 0.71)
  - retailers ask ~25% more than private sellers for the same model and storage
  - *fair* −30% and *needs repair* −60%, while the top three condition labels are used loosely
  - battery below 80% −13%; damage mentions −22% (after the negation fix below), warranty mentions +10%
  - old models vary far more in price than new ones
  - Pohjanmaa's high prices come from its 79% retailer share, not the region
- **Cleaning fixes** from what the EDA found (same PR):
  - storage right after "iPhone" ("iPhone 16 GB") is no longer read as a model
  - spare parts are dropped at any price (3), e.g. a rear camera (*takakamera*) or screens (*näyttöjä*)
  - bundles are dropped (6): several models in one title ("iPhone 12/ 12 pro max") or an iPhone with an Apple Watch, iPad or Android phones
  - iPhone SE is split by generation when the ad says: 1st 33 €, 2nd 80 €, 3rd 175 € median. Checking this found and fixed 3 bugs: Tori's "(2-3 gen)" label read as 3rd gen, "SE 2nd" without "gen", and "SE20".
- **Negation-aware mention flags:** a keyword doesn't count when negated ("ei halkeamia" = no cracks, "halkeamia ei ole", "ei säröjä, lohkeamia, halkeamia") or followed by "ended/lost" ("takuu päättyi", "kuitti hukassa"). 31% of the damage flags had been denials. Damage flags dropped from 298 to 197, and the damage effect went from −14% to −22%.
- **Feature check** (`models.py` → results (`docs/results.md`, removed 27 Sep, in git history)): Ridge re-scored with one feature group left out. Model (+0.019 RMSLE when removed), condition (+0.018) and text (+0.014) matter most, then model group (+0.009; it carries the age signal once release year is dropped). Seller type, battery, the flags and shipping add ~nothing to Ridge because the text covers them; region is within noise. The flags still matter for Random Forest, which uses them instead of full text.
- Result: 2,007 listings, 51 models. Ridge RMSLE 0.262, 48 € MAE (after dropping release year), 13% median error; median by model + storage 0.367, 56 €, 16%. Tests: 93.

- **Release year dropped from Ridge:** it follows from `exact_model`; no loss without it (RMSLE 0.262 vs 0.263). Kept in the cleaned data and documented in the EDA notebook's summary.

## 27 Sep: back to the first-look stage

At Abtaal's request, the project steps back to what the team did together in the first-look session, keeping the cleaning fixes:
- **Kept:** collector and data, `preprocess.py` with all fixes and their tests, cleaned data, docs, and the decision that `release_year` is not a model input.
- **Reworked:** [notebooks/1.0-eda.ipynb](../notebooks/1.0-eda.ipynb) now follows the team's first-look steps (columns, summary statistics, models, feature shortlist, seller types, correlation heatmap, selected columns), each explained.
- **Removed:** `evaluate.py`, `models.py`, `tests/test_models.py` and `docs/results.md` (baseline, Ridge, feature check), plus the EDA sections beyond the first look. The team will do the modelling. Everything removed stays in git history (last on `main` at `2fb7634`).

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
| Release year not a model input | Redundant with `exact_model` | 24 Sep |

## Open

- Keep retailer listings (20%) with `seller_type` as a feature? (recommended)
- Friday search-only re-run to see which listings disappeared?
- The README collection policy describes collector features not built yet (backoff, contact address, incremental fetching). Waiting for Abtaal.
- Next: step 2, EDA notebook and Random Forest.
