from priced_right.app import app
from priced_right.final_model import predict


def test_buyer_result_matches_model():
    expected = predict(
        exact_model="iPhone 13",
        storage_gb=128,
        condition="Hyvä",
        seller_type="private",
        asking_price=250,
    )

    response = app.test_client().post(
        "/",
        data={
            "mode": "buyer",
            "exact_model": "iPhone 13",
            "storage_gb": "128",
            "condition": "Hyvä",
            "seller_type": "private",
            "asking_price": "250",
        },
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert f"Expected asking price: €{expected['price']}" in page
    assert f"{expected['label'].capitalize()} comparable listings" in page


def test_seller_ignores_asking_price():
    expected = predict(exact_model="iPhone 13", storage_gb=128)

    response = app.test_client().post(
        "/",
        data={
            "mode": "seller",
            "exact_model": "iPhone 13",
            "storage_gb": "128",
            "asking_price": "9999",
        },
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert f"Expected asking price: €{expected['price']}" in page
    assert "Listing asking price:" not in page


def test_buyer_requires_asking_price():
    response = app.test_client().post(
        "/",
        data={"mode": "buyer", "exact_model": "iPhone 13"},
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Please enter an asking price for buyer mode." in page
    assert "Expected asking price:" not in page
