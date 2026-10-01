import pytest

from priced_right.app import LABEL_HEADINGS, app
from priced_right.final_model import predict

BASE = {"exact_model": "iPhone 13", "storage_gb": "128", "condition": "Hyvä", "seller_type": "private"}


def post(**data):
    response = app.test_client().post("/", data=data)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_buyer_result_matches_model():
    expected = predict(exact_model="iPhone 13", storage_gb=128, condition="Hyvä", seller_type="private", asking_price=250)
    page = post(**BASE, mode="buyer", asking_price="250")
    assert f"Expected asking price: €{expected['price']}" in page
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
    assert f"Expected asking price: €{expected['price']}" in page
    assert "Listing asking price:" not in page


@pytest.mark.parametrize("asking_price, message", [
    ("", "Please enter an asking price for buyer mode."),
    ("abc", "The asking price must be a number, e.g. 250."),
    ("-100", "The asking price must be more than 0 €."),
    ("0", "The asking price must be more than 0 €."),
    ("inf", "The asking price must be more than 0 €."),
    ("nan", "The asking price must be more than 0 €."),
    ("0.001", "The asking price must be more than 0 €."),  # rounds to 0.00
    ("10000.01", "The asking price must be at most 10 000 €."),
    ("1e6", "The asking price must be at most 10 000 €."),
])
def test_buyer_rejects_invalid_asking_price(asking_price, message):
    page = post(**BASE, mode="buyer", asking_price=asking_price)
    assert message in page
    assert "Expected asking price:" not in page


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
    assert "Traceback" not in page and "options()" not in page and "Expected asking price:" not in page


def test_damage_and_retailer_reach_the_model():
    damaged = predict(exact_model="iPhone 13", storage_gb=128, condition="Hyvä", mentions_damage=True)
    retailer = predict(exact_model="iPhone 13", storage_gb=128, condition="Hyvä", seller_type="retailer")
    assert f"Expected asking price: €{damaged['price']}" in post(**BASE, mode="seller", mentions_damage="yes")
    assert f"Expected asking price: €{retailer['price']}" in post(**{**BASE, "seller_type": "retailer"}, mode="seller")


def test_unknown_storage_and_condition_are_allowed():
    expected = predict(exact_model="iPhone 13")
    assert f"Expected asking price: €{expected['price']}" in post(exact_model="iPhone 13", storage_gb="", condition="", mode="seller")


@pytest.mark.parametrize("asking_price, shown", [
    ("250", "€250,"), ("249.5", "€249.50,"), ("250,50", "€250.50,"), (" 1500 ", "€1500,"), ("10000", "€10000,"),
])
def test_asking_price_is_shown_plainly(asking_price, shown):
    page = post(**BASE, mode="buyer", asking_price=asking_price)
    assert f"Listing asking price: {shown}" in page
    assert "e+" not in page
