import re

import pytest

from priced_right.app import LABEL_HEADINGS, OLDEST_OWN_GROUP, app, bar_positions, euros, model_groups
from priced_right.final_model import load, options, predict
from priced_right.preprocess import model_info

BASE = {"exact_model": "iPhone 13", "storage_gb": "128", "condition": "Hyvä", "seller_type": "private"}


def post(**data):
    response = app.test_client().post("/", data=data)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def price_html(result: dict) -> str:
    """How the result card shows the expected asking price."""
    return f'<p class="price">€{result["price"]:,}</p>'


def test_buyer_result_matches_model():
    expected = predict(exact_model="iPhone 13", storage_gb=128, condition="Hyvä", seller_type="private", asking_price=250)
    page = post(**BASE, mode="buyer", asking_price="250")
    assert price_html(expected) in page
    assert f'€{expected["low"]:,}<span class="range-dash">–</span>€{expected["high"]:,}' in page
    assert LABEL_HEADINGS[expected["label"]] in page


@pytest.mark.parametrize("asking_price, heading, words", [
    ("1000", "Above comparable listings", "% above"),
    ("50", "Below comparable listings", "% below"),
])
def test_buyer_shows_label_and_percentage(asking_price, heading, words):
    expected = predict(exact_model="iPhone 13", storage_gb=128, condition="Hyvä", asking_price=float(asking_price))
    page = post(**BASE, mode="buyer", asking_price=asking_price)
    assert heading in page
    assert f"{round(abs(expected['difference']) * 100)}{words}" in page


def test_seller_ignores_asking_price():
    expected = predict(exact_model="iPhone 13", storage_gb=128)
    page = post(exact_model="iPhone 13", storage_gb="128", mode="seller", asking_price="-5")
    assert price_html(expected) in page
    assert "This listing asks" not in page and 'class="bar-pin"' not in page


@pytest.mark.parametrize("asking_price, message", [
    ("", "Please enter an asking price for buyer mode."),
    ("abc", "The asking price must be a number, e.g. 250."),
    ("   ", "Please enter an asking price for buyer mode."),
    ("1,500,50", "The asking price must be a number, e.g. 250."),   # one mark can't be both separator and decimal
    ("1.5.0", "The asking price must be a number, e.g. 250."),
    ("-100", "The asking price must be more than €0."),
    ("0", "The asking price must be more than €0."),
    ("inf", "The asking price must be more than €0."),
    ("nan", "The asking price must be more than €0."),
    ("0.001", "The asking price must be more than €0."),  # rounds to 0.00
    ("10000.01", "The asking price must be at most €10,000."),
    ("1e6", "The asking price must be at most €10,000."),
    ("10,000.01", "The asking price must be at most €10,000."),
])
def test_buyer_rejects_invalid_asking_price(asking_price, message):
    page = post(**BASE, mode="buyer", asking_price=asking_price)
    assert message in page
    assert 'class="price"' not in page


def test_invalid_asking_price_marks_the_field():
    page = post(**BASE, mode="buyer", asking_price="0")
    assert 'name="asking_price" aria-invalid="true" aria-describedby="form-error"' in page
    assert '<a href="#asking_price">' in page   # the message links to the field


@pytest.mark.parametrize("field, value, message", [
    ("exact_model", "", "Please choose an iPhone model from the list."),
    ("exact_model", "iPhone 99", "Please choose an iPhone model from the list."),
    ("storage_gb", "xyz", "Please choose a storage size from the list."),
    ("storage_gb", "-128", "Please choose a storage size from the list."),
    ("storage_gb", "100", "Please choose a storage size from the list."),
    ("storage_gb", "²", "Please choose a storage size from the list."),  # a digit to isdigit(), not to int()
    ("storage_gb", "9" * 5000, "Please choose a storage size from the list."),  # longer than int() converts
    ("condition", "Rikki", "Please choose a condition from the list."),
    ("seller_type", "dealer", "Please choose private seller or retailer."),
])
def test_invalid_form_values_get_plain_messages(field, value, message):
    page = post(**{**BASE, field: value}, mode="seller")
    assert message in page
    assert "Traceback" not in page and "options()" not in page and 'class="price"' not in page


def test_damage_and_retailer_reach_the_model():
    damaged = predict(exact_model="iPhone 13", storage_gb=128, condition="Hyvä", mentions_damage=True)
    retailer = predict(exact_model="iPhone 13", storage_gb=128, condition="Hyvä", seller_type="retailer")
    assert price_html(damaged) in post(**BASE, mode="seller", mentions_damage="yes")
    assert price_html(retailer) in post(**{**BASE, "seller_type": "retailer"}, mode="seller")


def test_unknown_storage_and_condition_are_allowed():
    expected = predict(exact_model="iPhone 13")
    assert price_html(expected) in post(exact_model="iPhone 13", storage_gb="", condition="", mode="seller")


@pytest.mark.parametrize("asking_price, shown", [
    ("250", "€250"), ("249.5", "€249.50"), ("250,50", "€250.50"), (" 1500 ", "€1,500"), ("10000", "€10,000"),
    ("1,500", "€1,500"), ("1.500", "€1,500"), ("1 500", "€1,500"), ("1\u00a0500,50", "€1,500.50"),   # thousands separators
    ("1,500.50", "€1,500.50"), ("1.500,50", "€1,500.50"), ("10,000", "€10,000"),
    ("0,99", "€0.99"), ("250 €", "€250"), ("€250", "€250"),
])
def test_asking_price_is_shown_plainly(asking_price, shown):
    page = post(**BASE, mode="buyer", asking_price=asking_price)
    assert f"This listing asks <strong>{shown}</strong>," in page
    assert "e+" not in page


@pytest.mark.parametrize("amount, shown", [(250, "250"), (249.5, "249.50"), (1008, "1,008"), (10000.0, "10,000")])
def test_euros_format(amount, shown):
    assert euros(amount) == shown


def test_bar_positions_inside_the_range():
    bar = bar_positions({"low": 150, "high": 280, "price": 210, "asking_price": 200})
    assert 0 < bar["low"] < bar["price"] < bar["high"] < 100
    assert bar["low"] < bar["listing"] < bar["high"] and not bar["listing_outside"]


@pytest.mark.parametrize("asking_price, end", [(5000, 100), (1, 0)])
def test_bar_positions_clamp_a_listing_off_the_bar(asking_price, end):
    bar = bar_positions({"low": 150, "high": 280, "price": 210, "asking_price": asking_price})
    assert bar["listing"] == end and bar["listing_outside"]


def test_bar_positions_without_a_listing():
    assert "listing" not in bar_positions({"low": 150, "high": 280, "price": 210})


def test_model_groups_cover_every_model_newest_first():
    models = options()["exact_model"]
    groups = model_groups(models)
    flat = [model for _, group in groups for model in group]
    assert sorted(flat) == sorted(models)                       # every model exactly once
    years = [model_info(model)[0] for model in flat]
    assert years == sorted(years, reverse=True)
    assert groups[-1][0] == f"{OLDEST_OWN_GROUP - 1} and earlier"


def test_figures_count_up_only_on_a_fresh_page():
    assert f'data-count="{load()["n_listings"]}"' in app.test_client().get("/").get_data(as_text=True)
    assert "data-count=" not in post(**BASE, mode="seller")


def test_unknown_mode_is_seller_mode():
    page = post(**BASE, mode="xyz")
    assert re.search(r'value="seller"\s+checked', page)   # the page script needs one mode ticked
    assert "This listing asks" not in page


def test_asking_price_field_accepts_a_decimal_comma():
    page = app.test_client().get("/").get_data(as_text=True)
    assert 'type="text" id="asking_price"' in page and 'inputmode="decimal"' in page
