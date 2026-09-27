"""The held-out test set: created once, then locked away until the final evaluation.

    python -m priced_right.split      # creates data/processed/test_listing_ids.csv (once)

20% of the cleaned listings, drawn by relisting group, so every copy of an ad lands on the
same side. The test set is stored as listing IDs, so it stays the same if preprocessing is
re-run or a library update changes how the random draw works.

Everything before the final evaluation (EDA, feature checks, tuning, model choice) uses
`load_train()`. `load_test()` is for the final evaluation only (docs/ml-plan.md).
"""
from __future__ import annotations

import argparse

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from priced_right.preprocess import PROCESSED_DIR, REPO_ROOT, load_clean

TEST_SIZE = 0.2
SEED = 42
TEST_IDS_PATH = PROCESSED_DIR / "test_listing_ids.csv"


def draw_test_ids(df: pd.DataFrame, test_size: float = TEST_SIZE, seed: int = SEED) -> list[str]:
    """Listing IDs of a grouped random test set: whole relisting groups, about `test_size` of the rows."""
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    _, test_idx = next(splitter.split(df, groups=df["relisting_group"]))
    return sorted(df["listing_id"].iloc[test_idx])


def _test_ids() -> set[str]:
    if not TEST_IDS_PATH.exists():
        raise SystemExit("no test set yet: run `python -m priced_right.split` first")
    return set(pd.read_csv(TEST_IDS_PATH, dtype={"listing_id": str})["listing_id"])


def load_train() -> pd.DataFrame:
    """The 80% of listings used for everything before the final evaluation."""
    df = load_clean()
    return df[~df["listing_id"].isin(_test_ids())].reset_index(drop=True)


def load_test() -> pd.DataFrame:
    """The held-out 20%. Only for the final evaluation of the chosen model."""
    df = load_clean()
    return df[df["listing_id"].isin(_test_ids())].reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="overwrite an existing test set (don't, once modelling has started)")
    args = parser.parse_args()
    if TEST_IDS_PATH.exists() and not args.force:
        raise SystemExit(f"{TEST_IDS_PATH.relative_to(REPO_ROOT)} already exists; the test set is fixed")

    df = load_clean()
    test_ids = draw_test_ids(df)
    pd.DataFrame({"listing_id": test_ids}).to_csv(TEST_IDS_PATH, index=False)
    is_test = df["listing_id"].isin(test_ids)
    print(f"train {(~is_test).sum()} listings, test {is_test.sum()} listings ({is_test.mean():.1%}); "
          f"relisting groups: train {df.loc[~is_test, 'relisting_group'].nunique()}, test {df.loc[is_test, 'relisting_group'].nunique()}")
    print(f"wrote {TEST_IDS_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
