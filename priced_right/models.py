"""Feature check, tuning and model choice on the training set (lifecycle steps 20-24).

    python -m priced_right.models check   # feature check -> docs/feature-check.md, models/selected_inputs.json
    python -m priced_right.models tune    # tuning + comparison -> docs/model-comparison.md, models/tuned.json

Run `check` first: `tune` uses the inputs it selected. The decision rules are fixed in
docs/ml-plan.md, section 6, and applied here exactly as written. The test set is not used.
"""
from __future__ import annotations

import argparse
import json
import warnings
from itertools import product

import numpy as np
import pandas as pd
from sklearn.model_selection import GridSearchCV

from priced_right import evaluate, features, pipelines
from priced_right.preprocess import REPO_ROOT
from priced_right.split import load_train

MODELS_DIR = REPO_ROOT / "models"
DOCS_DIR = REPO_ROOT / "docs"
SELECTION_PATH = MODELS_DIR / "selected_inputs.json"
TUNED_PATH = MODELS_DIR / "tuned.json"

NOISE = 0.002  # rule 2: a group is kept if removing it worsens RMSLE by more than this for some model

# Rule 1: alternative encodings of the same information, chosen per model
PHONE = {"model name": features.MODEL_AS_NAME, "year + tier": features.MODEL_AS_YEAR_AND_TIER}
CONDITION = {"rank": features.CONDITION_AS_RANK, "levels": features.CONDITION_AS_LEVELS}

# Rule 4: easiest to explain first
SIMPLICITY_ORDER = ["Linear regression", "Decision tree", "Random forest", "Gradient boosting", "SVR"]

# Rule 3: settings tried for each model (plain linear regression has none)
GRIDS = {
    "Linear regression": {},
    "Decision tree": {"model__max_depth": [4, 6, 8, 10, 14, None], "model__min_samples_leaf": [1, 3, 5, 10, 20]},
    "Random forest": {"model__max_features": [0.3, 0.5, 1.0], "model__min_samples_leaf": [1, 3, 5],
                      "model__max_depth": [None, 20]},
    # Widened under rule 3 because best settings landed on grid edges: SVR once (C=30, gamma=0.01,
    # epsilon=0.05 were edges), gradient boosting three times, each time moving to smaller trees and
    # more, slower rounds (learning_rate 0.1 -> 0.05, max_iter 100 -> 400, max_leaf_nodes 15 -> 4),
    # until reaching 2-leaf trees, the smallest possible. See docs/ml-plan.md, change log.
    "SVR": {"model__C": [3.0, 10.0, 30.0, 100.0, 300.0], "model__gamma": [0.001, 0.003, 0.01, 0.03],
            "model__epsilon": [0.01, 0.02, 0.05, 0.1]},
    "Gradient boosting": {"model__learning_rate": [0.02, 0.05, 0.1], "model__max_iter": [200, 400, 800],
                          "model__max_leaf_nodes": [2, 4, 7], "model__min_samples_leaf": [10, 20, 40],
                          "model__l2_regularization": [0.0, 1.0]},
}


def training_data() -> tuple[pd.DataFrame, np.ndarray, pd.Series]:
    """Candidate inputs, log price and relisting groups of the training set."""
    train = load_train()
    return features.build(train), features.target(train), train["relisting_group"]


def inputs(phone: str | None, condition: str | None, groups: list[str]) -> list[str]:
    """Input columns for a phone-model encoding, a condition encoding (None = left out) and other groups."""
    columns = (PHONE[phone] if phone else []) + (CONDITION[condition] if condition else [])
    return columns + [c for g in groups for c in features.GROUPS[g]]


def score(name: str, columns: list[str], X, y, groups) -> dict:
    return evaluate.summarize(evaluate.cross_validate(pipelines.build(name, columns), X, y, groups))


# ---------------------------------------------------------------- feature check (step 22)

def feature_check(X: pd.DataFrame, y: np.ndarray, groups: pd.Series) -> dict:
    all_groups = list(features.GROUPS)

    # Rule 1: best encoding of the phone model and condition for each model, all other inputs included
    encodings = []
    for name in pipelines.MODELS:
        for phone, condition in product(PHONE, CONDITION):
            result = score(name, inputs(phone, condition, all_groups), X, y, groups)
            encodings.append({"model": name, "phone": phone, "condition": condition, **result})
            print(f"{name:18} {phone:11} condition {condition:6} RMSLE {result['rmsle_mean']:.3f}", flush=True)
    encodings = pd.DataFrame(encodings)
    chosen = {name: encodings[encodings.model == name].sort_values("rmsle_mean").iloc[0] for name in pipelines.MODELS}

    # Rule 2: remove one group at a time, with each model's chosen encodings
    removals = []
    for name, best in chosen.items():
        for group in ["phone model", "condition", *all_groups]:
            columns = inputs(None if group == "phone model" else best.phone,
                             None if group == "condition" else best.condition,
                             [g for g in all_groups if g != group])
            result = score(name, columns, X, y, groups)
            change = result["rmsle_mean"] - best.rmsle_mean
            removals.append({"model": name, "removed": group, "rmsle": result["rmsle_mean"], "change": change})
            print(f"{name:18} without {group:18} RMSLE {result['rmsle_mean']:.3f} ({change:+.3f})", flush=True)
    removals = pd.DataFrame(removals)
    helps = removals.groupby("removed")["change"].max() > NOISE
    kept = [g for g in all_groups if helps[g]]
    keep_phone, keep_condition = helps["phone model"], helps["condition"]

    # Final check: the kept inputs vs all inputs, per model
    selection, joint = {}, []
    for name, best in chosen.items():
        columns = inputs(best.phone if keep_phone else None, best.condition if keep_condition else None, kept)
        result = score(name, columns, X, y, groups)
        joint.append({"model": name, "all inputs": best.rmsle_mean, "kept inputs": result["rmsle_mean"],
                      "change": result["rmsle_mean"] - best.rmsle_mean})
        selection[name] = {"phone": best.phone, "condition": best.condition, "columns": columns}

    return {
        "encodings": encodings, "removals": removals, "joint": pd.DataFrame(joint),
        "selection": {"models": selection, "kept_groups": kept, "dropped_groups": [g for g in all_groups if g not in kept],
                      "phone_model_kept": bool(keep_phone), "condition_kept": bool(keep_condition)},
    }


def render_feature_check(result: dict, n_train: int) -> str:
    enc, sel = result["encodings"], result["selection"]
    table = result["removals"].pivot(index="removed", columns="model", values="change")[list(pipelines.MODELS)]
    table = table.loc[table.max(axis=1).sort_values(ascending=False).index]
    lines = [
        "# Feature check",
        "",
        "Generated by `python -m priced_right.models check`; do not edit by hand.",
        "",
        f"Training set only ({n_train} listings). {evaluate.N_SPLITS}-fold GroupKFold (seed {evaluate.SEED}), "
        "models trained on log1p(price) with default settings. Mean RMSLE over folds; lower is better. "
        "Rules: [ml-plan.md](ml-plan.md), section 6.",
        "",
        "## 1. Encoding of the phone model and condition (rule 1)",
        "",
        "All candidate inputs included; only the encodings change. Each model uses its best combination (**bold**).",
        "",
        "| Model | " + " | ".join(f"{p}, condition {c}" for p, c in product(PHONE, CONDITION)) + " |",
        "|:--|" + ":--|" * (len(PHONE) * len(CONDITION)),
    ]
    for name in pipelines.MODELS:
        rows = enc[enc.model == name].set_index(["phone", "condition"])["rmsle_mean"]
        best = rows.idxmin()
        cells = [f"**{rows[k]:.3f}**" if k == best else f"{rows[k]:.3f}" for k in product(PHONE, CONDITION)]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## 2. Which inputs earn their place (rule 2)",
        "",
        "Change in RMSLE when one group is removed (each model with its chosen encodings). "
        "Positive = worse without it, so the group helps.",
        "",
        "| Removed | " + " | ".join(pipelines.MODELS) + " |",
        "|:--|" + ":--|" * len(pipelines.MODELS),
        *[f"| {group} | " + " | ".join(f"{v:+.3f}" for v in row) + " |" for group, row in table.iterrows()],
        "",
        f"Kept if removing it worsens RMSLE by more than {NOISE} for at least one model.",
        "",
        f"**Kept:** phone model, condition, {', '.join(sel['kept_groups'])}."
        if sel["phone_model_kept"] and sel["condition_kept"] else f"**Kept:** {', '.join(sel['kept_groups'])}.",
        "",
        f"**Dropped:** {', '.join(sel['dropped_groups']) or 'none'}.",
        "",
        "## 3. Check: kept inputs vs all inputs",
        "",
        "Groups were removed one at a time above; this confirms the dropped groups don't matter together.",
        "",
        "| Model | All inputs | Kept inputs | Change |",
        "|:--|:--|:--|:--|",
        *[f"| {r.model} | {r._2:.3f} | {r._3:.3f} | {r.change:+.3f} |" for r in result["joint"].itertuples()],
        "",
        "## 4. Inputs per model",
        "",
        "| Model | Phone model as | Condition as | Inputs |",
        "|:--|:--|:--|:--|",
        *[f"| {name} | {s['phone']} | {s['condition']} | `{'`, `'.join(s['columns'])}` |" for name, s in sel["models"].items()],
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- tuning and comparison (steps 23-24)

def tune(X: pd.DataFrame, y: np.ndarray, groups: pd.Series, selection: dict) -> tuple[pd.DataFrame, dict]:
    rows = [{"model": "Median by model + storage (baseline)", "params": None,
             **evaluate.summarize(evaluate.cross_validate(pipelines.baseline(), X, y, groups))}]
    tuned = {}
    for name in pipelines.MODELS:
        columns = selection["models"][name]["columns"]
        search = GridSearchCV(pipelines.build(name, columns), GRIDS[name], cv=evaluate.cv_splitter(),
                              scoring="neg_root_mean_squared_error", n_jobs=-1)
        search.fit(X, y, groups=groups)
        params = {k.removeprefix("model__"): v for k, v in search.best_params_.items()}
        result = evaluate.summarize(evaluate.cross_validate(pipelines.build(name, columns, **params), X, y, groups))
        rows.append({"model": name, "params": params, **result})
        tuned[name] = {"columns": columns, "params": params, "on_grid_edge": grid_edges(name, params)}
        print(f"{name:18} RMSLE {result['rmsle_mean']:.3f} ± {result['rmsle_std']:.3f} | MAE {result['mae_eur_mean']:.0f} € "
              f"| median error {result['median_ape_mean']:.1%} | {params}", flush=True)
    return pd.DataFrame(rows), tuned


# Values that can't be widened past: 1 sample per leaf, no regularization, all features, 2-leaf trees
NATURAL_LIMITS = {"min_samples_leaf": 1, "l2_regularization": 0.0, "max_features": 1.0, "max_leaf_nodes": 2}


def grid_edges(name: str, params: dict) -> list[str]:
    """Settings whose best value is the smallest or largest value tried (rule 3: widen the grid).

    Not flagged: a value at its natural limit, and settings whose grid includes None (no limit).
    """
    edges = []
    for key, values in GRIDS[name].items():
        setting = key.removeprefix("model__")
        numeric = [v for v in values if isinstance(v, (int, float))]
        value = params[setting]
        if None in values or len(numeric) < 2 or value == NATURAL_LIMITS.get(setting):
            continue
        if value in (min(numeric), max(numeric)):
            edges.append(setting)
    return edges


def choose(results: pd.DataFrame) -> tuple[str, float]:
    """Rule 4, one-standard-error rule: the easiest-to-explain model within one SE of the best RMSLE."""
    models = results[results.model.isin(pipelines.MODELS)].set_index("model")
    best = models["rmsle_mean"].idxmin()
    threshold = models.loc[best, "rmsle_mean"] + models.loc[best, "rmsle_se"]
    eligible = [m for m in SIMPLICITY_ORDER if models.loc[m, "rmsle_mean"] <= threshold]
    return eligible[0], float(threshold)


def _fmt_params(params) -> str:
    if params is None:
        return "baseline"
    return ", ".join(f"{k}={v}" for k, v in params.items()) or "none to tune"


def render_comparison(results: pd.DataFrame, tuned: dict, chosen: str, threshold: float, n_train: int) -> str:
    best = results[results.model.isin(pipelines.MODELS)].sort_values("rmsle_mean").iloc[0]
    baseline = results.iloc[0]
    final = results.set_index("model").loc[chosen]
    edges = {m: t["on_grid_edge"] for m, t in tuned.items() if t["on_grid_edge"]}
    within = [m for m in SIMPLICITY_ORDER if results.set_index("model").loc[m, "rmsle_mean"] <= threshold]
    lines = [
        "# Model comparison",
        "",
        "Generated by `python -m priced_right.models tune`; do not edit by hand.",
        "",
        f"Training set only ({n_train} listings). Every model was tuned with a grid search on the same "
        f"{evaluate.N_SPLITS}-fold GroupKFold (seed {evaluate.SEED}) and scored on those folds. "
        "Inputs per model: [feature-check.md](feature-check.md). Mean ± standard deviation over folds.",
        "",
        "| Model | RMSLE | MAE (€) | Median % error | Best settings |",
        "|:--|:--|:--|:--|:--|",
        *[f"| {r.model} | {r.rmsle_mean:.3f} ± {r.rmsle_std:.3f} | {r.mae_eur_mean:.0f} ± {r.mae_eur_std:.0f} | "
          f"{r.median_ape_mean:.1%} ± {r.median_ape_std:.1%} | {_fmt_params(r.params)} |" for r in results.itertuples()],
        "",
        "## Choice (rule 4)",
        "",
        f"Lowest RMSLE: {best.model} ({best.rmsle_mean:.3f}, standard error {best.rmsle_se:.3f}). "
        f"Models within one standard error (RMSLE ≤ {threshold:.3f}): "
        f"{', '.join(within)}.",
        "",
        f"**Final model: {chosen}** "
        f"({'the only one' if len(within) == 1 else 'the easiest to explain among them'}). "
        f"Cross-validated RMSLE {final.rmsle_mean:.3f} vs {baseline.rmsle_mean:.3f} for the baseline "
        f"({1 - final.rmsle_mean / baseline.rmsle_mean:.0%} lower).",
        "",
        "These cross-validation scores are slightly optimistic, because settings and model were chosen on the same "
        "folds. The final, unbiased number comes from the test set (step 26).",
        "",
        f"Grid check (rule 3): {'no best setting on the edge of its grid' if not edges else f'on the edge: {edges}'}.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- command line

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["check", "tune"])
    args = parser.parse_args()
    # Expected: a rare model can appear in a validation fold but not its training folds;
    # the pipeline routes it to the shared "infrequent" column (pipelines.preprocessor).
    warnings.filterwarnings("ignore", message="Found unknown categories")
    X, y, groups = training_data()
    MODELS_DIR.mkdir(exist_ok=True)

    if args.step == "check":
        result = feature_check(X, y, groups)
        SELECTION_PATH.write_text(json.dumps(result["selection"], indent=2) + "\n", encoding="utf-8")
        (DOCS_DIR / "feature-check.md").write_text(render_feature_check(result, len(X)), encoding="utf-8")
        print(f"kept: {result['selection']['kept_groups']}\ndropped: {result['selection']['dropped_groups']}")
        print("wrote docs/feature-check.md and models/selected_inputs.json")
    else:
        if not SELECTION_PATH.exists():
            raise SystemExit("run `python -m priced_right.models check` first")
        selection = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
        results, tuned = tune(X, y, groups, selection)
        chosen, threshold = choose(results)
        TUNED_PATH.write_text(json.dumps({"final_model": chosen, "models": tuned}, indent=2) + "\n", encoding="utf-8")
        (DOCS_DIR / "model-comparison.md").write_text(render_comparison(results, tuned, chosen, threshold, len(X)), encoding="utf-8")
        print(f"final model: {chosen}\nwrote docs/model-comparison.md and models/tuned.json")


if __name__ == "__main__":
    main()
