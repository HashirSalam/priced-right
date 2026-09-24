import pytest

import pandas as pd

from priced_right.preprocess import (
    clean,
    model_from_description,
    model_info,
    parse_battery_pct,
    parse_model,
    parse_storage_gb,
    se_generation,
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
    ("iPhone SE 2020", "iPhone SE (2nd gen)"),
    ("Apple iPhone 16 GB valkoinen", None),
    ("Apple iPhone 8gb", None),
    ("iPhone 16 128GB", "iPhone 16"),
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
    ("iPhone SE (1st gen)", 2016, "iPhone 2G-11"),
    ("iPhone SE (3rd gen)", 2022, "iPhone SE (2-3 gen)"),
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
    ("iPhone SE3 5G Product Red", "iPhone SE (3rd gen)"),
    ("iPhone SE2 64GB", "iPhone SE (2nd gen)"),
    ("iPhone SE, gen 1, 32GB", "iPhone SE (1st gen)"),
    ("Apple iPhone SE (1.sukupolvi) 16 GB", "iPhone SE (1st gen)"),
    ("Apple iPhone SE 2022, 128GB", "iPhone SE (3rd gen)"),
    ("Apple iPhone SE", "iPhone SE"),
    ("Apple iPhone SE (2-3 gen) älypuhelin 64 GB", "iPhone SE"),
    ("iPhone SE 2nd 64GB +12KK Takuu", "iPhone SE (2nd gen)"),
    ("Apple iPhone SE20 älypuhelin 64 GB", "iPhone SE (2nd gen)"),
    ("Käyttämätön iPhone SE (3 gen) 128 GB", "iPhone SE (3rd gen)"),
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


@pytest.mark.parametrize("text, use_years, expected", [
    ("toimii 5G-verkossa", True, 3),
    ("2nd gen, akku 90%", True, 2),
    ("ostettu 2022", False, None),  # a purchase year in a description is not a generation
    ("ostettu 2022", True, 3),
    ("ei tietoa", True, None),
])
def test_se_generation(text, use_years, expected):
    assert se_generation(text, use_years=use_years) == expected


def test_clean_drops_parts_and_bundles_and_resolves_se():
    rows = [
        ("1", "iPhone 13 128GB", "Hyvä kunto", 250),
        ("2", "iPhone 13 256 GB", "Kuin uusi", 300),
        ("3", "Iphone 15 alkuperäinen takakamera", "Uusi osa", 45),
        ("4", "Apple iPhone 13 128 GB ja iphone 11 64 GB", "Molemmat", 450),
        ("5", "iPhone 11 sekä Apple Watch 4", "Paketti", 140),
        ("6", "Apple iPhone SE 64GB", "SE 2 toimii hyvin", 90),
        ("7", "Apple iPhone 16 GB valkoinen", "iPhone 6s, toimii", 60),
        ("8", "Apple iPhone 12/ 12 pro max", "Kumpi tahansa", 999),
    ]
    raw = pd.DataFrame(rows, columns=["listing_id", "title", "description", "price_eur"]).assign(
        model_group=None, memory=None, condition="Hyvä", seller_type="private", shipping_available=False,
        municipality="Helsinki", region="Uusimaa",
        published_at="2026-09-10T10:00:00+00:00", collected_at="2026-09-17T10:00:00+00:00",
    )
    df, log = clean(raw)
    assert dict(zip(df["listing_id"], df["exact_model"], strict=True)) == {
        "1": "iPhone 13", "2": "iPhone 13", "6": "iPhone SE (2nd gen)", "7": "iPhone 6s",
    }
    removed = {step["step"]: step["removed"] for step in log}
    assert removed["spare parts (camera, screen, …) at any price"] == 1
    assert removed["bundles (several models, or an iPhone with other devices)"] == 3
