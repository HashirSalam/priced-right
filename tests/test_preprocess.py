import pytest

from priced_right.preprocess import (
    model_from_description,
    model_info,
    parse_battery_pct,
    parse_model,
    parse_storage_gb,
    strip_prices,
)


@pytest.mark.parametrize("text, expected", [
    ("Apple iPhone 15 Pro Max 256 GB", "iPhone 15 Pro Max"),
    ("Iphone 12Pro", "iPhone 12 Pro"),
    ("Apple iPhone 13mini", "iPhone 13 Mini"),
    ("Apple iPhone 16Pro128 GB", "iPhone 16 Pro"),
    ("Phone 12 128 Gt, kuin uusi", "iPhone 12"),
    ("iPhone XS Max 64GB", "iPhone XS Max"),
    ("iPhone 6s", "iPhone 6s"),
    ("iPhone 16e 128GB", "iPhone 16e"),
    ("Apple iPhone Air, 256 Gt", "iPhone Air"),
    ("iPhone 17 Air 256GB", "iPhone Air"),
    ("iPhone SE 2020", "iPhone SE"),
    ("Uudenveroinen Apple 16 Pro Max 256GB", "iPhone 16 Pro Max"),
    ("iPhone 64GB, iPhone 11", "iPhone 11"),
    ("iPhone XR Max 64GB", "iPhone XR"),
    ("iPhone SE Pro", "iPhone SE"),
    ("iPhone 13 Max", "iPhone 13"),
    ("iPhone 16e Pro", "iPhone 16e"),
    ("Apple watch 7 GPS+Cellular", None),
    ("iPad 10th generation", None),
    ("Apple iPhone älypuhelin 128 GB", None),
])
def test_parse_model(text, expected):
    assert parse_model(text) == expected


@pytest.mark.parametrize("model, year, group", [
    ("iPhone 15 Pro Max", 2023, "iPhone 15/Plus/Pro/Max"),
    ("iPhone 6s", 2015, "iPhone 2G-11"),
    ("iPhone 16e", 2025, "iPhone 16/Plus/Pro/Max"),
    ("iPhone XR", 2018, "iPhone 2G-11"),
    ("iPhone SE", 2020, "iPhone SE (2-3 gen)"),
    ("iPhone Air", 2025, "iPhone 17/Air/Pro/Max"),
])
def test_model_info(model, year, group):
    assert model_info(model) == (year, group)


@pytest.mark.parametrize("texts, expected", [
    (("128 GB",), 128),
    (("", "iPhone 13 256Gt musta"), 256),
    (("Muu", "iPhone 17 Pro 1 Tt"), 1024),
    (("", "iPhone 12 5G"), None),
    (("", "akku 100%, 2020"), None),
])
def test_parse_storage_gb(texts, expected):
    assert parse_storage_gb(*texts) == expected


@pytest.mark.parametrize("text, expected", [
    ("Akkukapasiteetti 90%, akku riittää", 90),
    ("akun kunto 87 %", 87),
    ("Battery health is at 91%", 91),
    ("100% akku", 100),
    ("akku 30% alennus", None),
    ("näyttö 100% ehjä", None),
])
def test_parse_battery_pct(text, expected):
    assert parse_battery_pct(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("iPhone SE3 5G Product Red", "iPhone SE"),
    ("iPhone SE2 64GB", "iPhone SE"),
    ("Iphone 2022 se 64GB", None),
])
def test_parse_model_se_generations(text, expected):
    assert parse_model(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Myydään iPhone 12 mini, toimii hyvin.", "iPhone 12 Mini"),
    ("Sama piiri kuin iPhone 14:ssä. Parempi kuin iPhone 13.", None),
    ("Apple ja pari Androidia: iPhone 12 mini ja iPhone 8", None),
    ("Ei mallia mainittu", None),
])
def test_model_from_description_needs_exactly_one_model(text, expected):
    assert model_from_description(text) == expected


@pytest.mark.parametrize("text, removed, kept", [
    ("Hinta: 750 €, iPhone 16e 128GB", ["750"], ["16e", "128GB"]),
    ("Myydään 250e, akku 90%", ["250e"], ["90%"]),
    ("hp 180 tai paras tarjous", ["180"], ["tarjous"]),
    ("Uutena 1 299,00 € nyt 600 eur", ["1 299", "600"], ["Uutena"]),
    ("iPhone 13 256 GB", [], ["13", "256 GB"]),
])
def test_strip_prices(text, removed, kept):
    out = strip_prices(text)
    assert all(r not in out for r in removed) and all(k in out for k in kept)
