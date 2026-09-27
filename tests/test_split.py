import pandas as pd
import pytest

from priced_right import split
from priced_right.preprocess import load_clean


@pytest.fixture(scope="module")
def data():
    return load_clean()


def test_draw_keeps_relisting_groups_together(data):
    is_test = data["listing_id"].isin(split.draw_test_ids(data))
    assert not set(data.loc[is_test, "relisting_group"]) & set(data.loc[~is_test, "relisting_group"])
    assert 0.18 < is_test.mean() < 0.22


def test_draw_is_the_same_every_time(data):
    assert split.draw_test_ids(data) == split.draw_test_ids(data)


def test_saved_test_set_matches_the_draw(data):
    """The committed test set is the documented draw, so nobody picked it by hand."""
    saved = pd.read_csv(split.TEST_IDS_PATH, dtype={"listing_id": str})["listing_id"].tolist()
    assert saved == split.draw_test_ids(data)


def test_train_and_test_cover_the_data_without_overlap(data):
    train, test = split.load_train(), split.load_test()
    assert len(train) + len(test) == len(data)
    assert not set(train["listing_id"]) & set(test["listing_id"])
    assert not set(train["relisting_group"]) & set(test["relisting_group"])
