import pytest

from priced_right import final_model
from priced_right.features import CONDITION_ORDER
from priced_right.preprocess import load_clean


def test_saved_model_is_trained_on_every_listing():
    bundle = final_model.load()
    assert bundle["n_listings"] == len(load_clean())
    assert bundle["model"] == "Gradient boosting"
    assert set(bundle["range_factors"]) <= {"2016 or earlier", "2017-19", "2020-22", "2023 or later"}


def test_options_cover_the_dropdowns():
    options = final_model.options()
    assert "iPhone 13" in options["exact_model"] and "iPhone 15 Pro Max" in options["exact_model"]
    assert list(options["condition"]) == CONDITION_ORDER
    assert options["seller_type"] == ["private", "retailer"]
    assert 128 in options["storage_gb"]


def test_seller_mode():
    result = final_model.predict("iPhone 13", 128, "Hyvä", "private", False)
    assert result["low"] < result["price"] < result["high"]
    assert result["range_level"] == 0.8
    assert "asking prices" in result["disclaimer"]
    assert "label" not in result


@pytest.mark.parametrize("asking_price, label", [(1, "below"), (100_000, "above")])
def test_buyer_mode_labels(asking_price, label):
    result = final_model.predict("iPhone 13", 128, "Hyvä", "private", False, asking_price=asking_price)
    assert result["label"] == label
    # `price` is rounded to whole euros; `difference` uses the unrounded prediction
    assert result["difference"] == pytest.approx(asking_price / result["price"] - 1, rel=0.01, abs=0.01)


def test_buyer_mode_in_line_at_the_expected_price():
    expected = final_model.predict("iPhone 13", 128, "Hyvä")["price"]
    assert final_model.predict("iPhone 13", 128, "Hyvä", asking_price=expected)["label"] == "in line"


def test_storage_and_condition_are_optional():
    result = final_model.predict("iPhone 12")
    assert result["low"] < result["price"] < result["high"]


def test_prices_move_the_right_way():
    good = final_model.predict("iPhone 13", 128, "Kuin uusi")["price"]
    assert final_model.predict("iPhone 13", 128, "Vaatii korjausta")["price"] < good
    assert final_model.predict("iPhone 15", 128, "Kuin uusi")["price"] > good


def test_old_phones_get_wider_ranges():
    old, new = final_model.predict("iPhone 6"), final_model.predict("iPhone 16")
    assert old["high"] / old["price"] > new["high"] / new["price"]


@pytest.mark.parametrize("kwargs, message", [
    (dict(exact_model="iPhone 18"), "unknown model"),
    (dict(exact_model="iPhone 13", storage_gb=100), "storage_gb"),
    (dict(exact_model="iPhone 13", condition="good"), "condition"),
    (dict(exact_model="iPhone 13", seller_type="shop"), "seller_type"),
    (dict(exact_model="iPhone 13", asking_price=0), "asking_price"),
])
def test_invalid_input_is_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        final_model.predict(**kwargs)


def test_every_storage_size_in_the_data_can_be_priced():
    sizes = load_clean()["storage_gb"].dropna().astype(int).unique()
    assert set(sizes) <= set(final_model.options()["storage_gb"])
    result = final_model.predict("iPhone 17 Pro Max", 2048, "Kuin uusi")  # a 2 TB phone is in the data
    assert result["low"] < result["price"] < result["high"]
