"""The one-time evaluation of the final model on the test set (lifecycle steps 26-27).

    python -m priced_right.final_evaluation   # -> docs/test-results.md, models/test_results.json

Runs once: it refuses to run again once results exist, because re-running after changes would
turn the test set into another validation set (docs/ml-plan.md, sections 4 and 7). The model and
the price ranges are fitted on the training set only; the test set is only predicted.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from priced_right import evaluate, features, pipelines
from priced_right.models import MODELS_DIR, TUNED_PATH
from priced_right.preprocess import REPO_ROOT
from priced_right.ranges import LEVEL, PERIOD_LABELS, PriceRange
from priced_right.split import load_test, load_train

RESULTS_PATH = MODELS_DIR / "test_results.json"
REPORT_PATH = REPO_ROOT / "docs" / "test-results.md"
N_BOOTSTRAP = 2000
SEED = 42
MIN_IMPROVEMENT = 0.10          # success bar 1: RMSLE at least 10% below the baseline's
COVERAGE_BAND = (0.75, 0.85)    # success bar 3: 80% ranges cover 75-85%
MIN_GROUP_SIZE = 20             # regions with fewer test listings are grouped


def bootstrap(test: pd.DataFrame, y: np.ndarray, pred: np.ndarray, base: np.ndarray,
              n: int = N_BOOTSTRAP, seed: int = SEED) -> pd.DataFrame:
    """Scores on n resamples of the test set, drawn by relisting group (copies of an ad stay together)."""
    rng = np.random.default_rng(seed)
    groups = test["relisting_group"].to_numpy()
    rows_of = pd.Series(np.arange(len(test))).groupby(groups).apply(list).to_list()
    rows = []
    for _ in range(n):
        idx = np.concatenate([rows_of[i] for i in rng.integers(0, len(rows_of), len(rows_of))])
        model, baseline = evaluate.scores(y[idx], pred[idx]), evaluate.scores(y[idx], base[idx])
        rows.append({**model, "baseline_rmsle": baseline["rmsle"], "baseline_mae_eur": baseline["mae_eur"],
                     "improvement": 1 - model["rmsle"] / baseline["rmsle"]})
    return pd.DataFrame(rows)


def by_group(results: pd.DataFrame, column: str) -> pd.DataFrame:
    g = results.groupby(column, observed=True)
    return pd.DataFrame({
        "listings": g.size(),
        "rmsle": g["log_error"].apply(lambda e: float(np.sqrt((e ** 2).mean()))),
        "bias": g["log_error"].median().apply(np.expm1),
        "median_ape": g["pct_error"].apply(lambda e: e.abs().median()),
        "coverage": g["covered"].mean(),
    })


def evaluate_once() -> dict:
    tuned = json.loads(TUNED_PATH.read_text(encoding="utf-8"))
    name = tuned["final_model"]
    spec = tuned["models"][name]
    train, test = load_train(), load_test()

    price_range = PriceRange(name, spec["columns"], spec["params"]).fit(train)
    baseline = pipelines.baseline().fit(features.build(train), features.target(train))

    y = features.target(test)
    predicted = price_range.predict(test)
    pred = np.log1p(predicted["price"].to_numpy())
    base = baseline.predict(features.build(test))

    results = test.assign(
        predicted=predicted["price"], low=predicted["low"], high=predicted["high"],
        launch_period=pd.Categorical(predicted["launch_period"], PERIOD_LABELS, ordered=True),
        log_error=pred - y, pct_error=(predicted["price"] - test["price_eur"]) / test["price_eur"],
        covered=(test["price_eur"] >= predicted["low"]) & (test["price_eur"] <= predicted["high"]),
    )
    counts = results["region"].value_counts()
    results["region_grouped"] = results["region"].where(results["region"].map(counts) >= MIN_GROUP_SIZE,
                                                        f"other (fewer than {MIN_GROUP_SIZE})")
    results["price_band"] = pd.qcut(results["price_eur"], 5, precision=0)

    boot = bootstrap(test, y, pred, base)
    ci = boot.quantile([0.025, 0.975])
    model_scores, baseline_scores = evaluate.scores(y, pred), evaluate.scores(y, base)
    improvement = 1 - model_scores["rmsle"] / baseline_scores["rmsle"]
    seller = by_group(results, "seller_type")

    checks = {
        f"RMSLE at least {MIN_IMPROVEMENT:.0%} below the baseline": improvement >= MIN_IMPROVEMENT,
        "MAE below the baseline": model_scores["mae_eur"] < baseline_scores["mae_eur"],
        f"{LEVEL:.0%} ranges cover {COVERAGE_BAND[0]:.0%}-{COVERAGE_BAND[1]:.0%} overall":
            COVERAGE_BAND[0] <= results["covered"].mean() <= COVERAGE_BAND[1],
        **{f"{LEVEL:.0%} ranges cover {COVERAGE_BAND[0]:.0%}-{COVERAGE_BAND[1]:.0%} for {s} sellers":
           COVERAGE_BAND[0] <= cov <= COVERAGE_BAND[1] for s, cov in seller["coverage"].items()},
    }
    return {
        "model": name, "n_train": len(train), "n_test": len(test),
        "model_scores": model_scores, "baseline_scores": baseline_scores, "improvement": improvement,
        "ci": {k: [float(ci.loc[0.025, k]), float(ci.loc[0.975, k])] for k in ci.columns},
        "coverage": float(results["covered"].mean()),
        "range_factors": {p: float(np.exp(h)) for p, h in price_range.half_widths_.items()},
        "checks": {k: bool(v) for k, v in checks.items()},
        "groups": {col: by_group(results, col) for col in ["seller_type", "region_grouped", "launch_period", "price_band"]},
    }


def render(r: dict) -> str:
    m, b, ci = r["model_scores"], r["baseline_scores"], r["ci"]

    def table(df: pd.DataFrame, label: str) -> list[str]:
        def name(k):  # price bands are intervals like (100.0, 190.0]
            return f"{int(k.left) + 1}–{int(k.right)}" if isinstance(k, pd.Interval) else k
        return [f"| {label} | Listings | RMSLE | Bias | Median % error | Range coverage |", "|:--|:--|:--|:--|:--|:--|",
                *[f"| {name(k)} | {int(v.listings)} | {v.rmsle:.3f} | {v.bias:+.0%} | {v.median_ape:.0%} | {v.coverage:.0%} |"
                  for k, v in df.iterrows()], ""]

    lines = [
        "# Test-set results",
        "",
        "Generated once by `python -m priced_right.final_evaluation`; do not edit by hand.",
        "",
        f"Final model: **{r['model']}**, trained on the {r['n_train']} training listings and scored once on the "
        f"{r['n_test']} held-out test listings. 95% confidence intervals from {N_BOOTSTRAP:,} bootstrap resamples "
        f"of the test set by relisting group. Procedure: [ml-plan.md](ml-plan.md), section 7.",
        "",
        "## Scores",
        "",
        "| | Final model | Baseline (median by model + storage) |",
        "|:--|:--|:--|",
        f"| RMSLE | {m['rmsle']:.3f} (95% CI {ci['rmsle'][0]:.3f}–{ci['rmsle'][1]:.3f}) | {b['rmsle']:.3f} "
        f"({ci['baseline_rmsle'][0]:.3f}–{ci['baseline_rmsle'][1]:.3f}) |",
        f"| MAE | {m['mae_eur']:.0f} € ({ci['mae_eur'][0]:.0f}–{ci['mae_eur'][1]:.0f} €) | {b['mae_eur']:.0f} € "
        f"({ci['baseline_mae_eur'][0]:.0f}–{ci['baseline_mae_eur'][1]:.0f} €) |",
        f"| Median % error | {m['median_ape']:.1%} ({ci['median_ape'][0]:.1%}–{ci['median_ape'][1]:.1%}) | {b['median_ape']:.1%} |",
        f"| {LEVEL:.0%} price ranges | cover {r['coverage']:.0%} of test listings | |",
        "",
        f"RMSLE is **{r['improvement']:.0%} lower** than the baseline's (95% CI {ci['improvement'][0]:.0%}–{ci['improvement'][1]:.0%}).",
        "",
        "## Success bar",
        "",
        "| Criterion | Met? |",
        "|:--|:--|",
        *[f"| {k} | {'yes' if v else '**no**'} |" for k, v in r["checks"].items()],
        "",
        "## Price ranges",
        "",
        f"{LEVEL:.0%} ranges from held-out training errors, per launch period: a range is price ÷ factor to price × factor.",
        "",
        "| Launch period | Factor |",
        "|:--|:--|",
        *[f"| {p} | ×/÷ {f:.2f} |" for p, f in r["range_factors"].items()],
        "",
        "## Errors and coverage by group (fairness)",
        "",
        "Bias: typical over- (+) or under-pricing (−). Range coverage should be near 80%.",
        "",
        *table(r["groups"]["seller_type"], "Seller type"),
        *table(r["groups"]["region_grouped"].sort_values("listings", ascending=False), "Region"),
        *table(r["groups"]["launch_period"], "Launched"),
        *table(r["groups"]["price_band"], "Asking price (€)"),
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true",
                        help="run again although results exist (only to reproduce them, never after changing anything)")
    args = parser.parse_args()
    if RESULTS_PATH.exists() and not args.force:
        raise SystemExit(f"{RESULTS_PATH.relative_to(REPO_ROOT)} already exists: the test set has been used. "
                         "Use --force only to reproduce the same results.")

    r = evaluate_once()
    REPORT_PATH.write_text(render(r), encoding="utf-8")
    saved = {k: v for k, v in r.items() if k != "groups"}
    saved["groups"] = {k: json.loads(v.reset_index().astype({v.index.name or "index": str}).to_json(orient="records"))
                       for k, v in r["groups"].items()}
    RESULTS_PATH.write_text(json.dumps(saved, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    m, b = r["model_scores"], r["baseline_scores"]
    print(f"test RMSLE {m['rmsle']:.3f} vs baseline {b['rmsle']:.3f} ({r['improvement']:.0%} lower); "
          f"MAE {m['mae_eur']:.0f} € vs {b['mae_eur']:.0f} €; {LEVEL:.0%} ranges cover {r['coverage']:.0%}")
    for check, met in r["checks"].items():
        print(f"  {'met    ' if met else 'NOT met'}  {check}")
    print(f"wrote {REPORT_PATH.relative_to(REPO_ROOT)} and {RESULTS_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
