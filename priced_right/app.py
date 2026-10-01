"""Flask app: expected asking price for an iPhone (seller mode), or how a listing compares (buyer mode).

    python -m flask --app priced_right.app run

The form only offers valid choices, but every input is checked again here, because a request
can be sent without the form. Invalid input gets a plain-language message instead of a crash.
"""
import math
import re
from datetime import datetime

from flask import Flask, render_template, request

from priced_right.final_model import load, options, predict
from priced_right.preprocess import model_info
from priced_right.ranges import LEVEL

app = Flask(__name__)

LABEL_HEADINGS = {"below": "Below comparable listings", "in line": "In line with comparable listings",
                  "above": "Above comparable listings"}
# One line per condition chip, so users pick the level Tori sellers would choose
CONDITION_HINTS = {"Vaatii korjausta": "Doesn't fully work", "Kohtalainen": "Clear signs of use",
                   "Hyvä": "Light signs of use", "Kuin uusi": "No visible marks", "Uusi": "Unused or sealed"}
OLDEST_OWN_GROUP = 2016    # older models share one dropdown group instead of many one-model groups
MAX_ASKING_PRICE = 10_000   # € — far above any iPhone listing; larger numbers are typos


# A number with thousands separators: groups of 3 digits after a "," or "." (the same mark throughout),
# then optional cents after the other mark. "1,500", "1.500", "12,345.67", "1.500,50"; not "0.001" or "250,50"
_GROUPED = re.compile(r"([1-9]\d{0,2}(?:([.,])\d{3})(?:\2\d{3})*)(?:([.,])(\d{1,2}))?")


def price_text_to_number(raw: str) -> str:
    """Asking price as typed -> text float() reads: "1 500,50 €" -> "1500.50", "1,500" -> "1500", "250,50" -> "250.50"."""
    text = re.sub(r"[\s€]", "", raw)              # Finnish thousands spaces (also no-break) and the euro sign
    grouped = _GROUPED.fullmatch(text)
    if grouped:
        whole, group_mark, decimal_mark, cents = grouped.groups()
        if decimal_mark == group_mark:             # "1,500,50": the same mark can't be both
            return text
        return whole.replace(group_mark, "") + (f".{cents}" if cents else "")
    return text.replace(",", ".")                  # a single decimal comma, as Finnish prices are written


def parse_asking_price(raw: str | None) -> tuple[float | None, str | None]:
    """(price rounded to cents, None) for a number above 0 and up to MAX_ASKING_PRICE, else (None, message).

    Thousands separators and a decimal comma are both understood (see price_text_to_number).
    """
    if not raw or not raw.strip():
        return None, "Please enter an asking price for buyer mode."
    try:
        price = round(float(price_text_to_number(raw)), 2)
    except ValueError:
        return None, "The asking price must be a number, e.g. 250."
    if not math.isfinite(price) or price <= 0:
        return None, "The asking price must be more than €0."
    if price > MAX_ASKING_PRICE:
        return None, f"The asking price must be at most €{MAX_ASKING_PRICE:,}."
    return price, None


@app.template_filter("euros")
def euros(amount: float) -> str:
    """250.0 -> "250", 249.5 -> "249.50", 1008 -> "1,008": cents only when there are any, thousands separated."""
    return f"{amount:,.0f}" if amount == int(amount) else f"{amount:,.2f}"


def read_form(form, choices: dict) -> tuple[dict | None, tuple[str, str] | None]:
    """The predict() arguments from the submitted form, or (field name, message) for the first invalid input."""
    model = form.get("exact_model")
    if model not in choices["exact_model"]:
        return None, ("exact_model", "Please choose an iPhone model from the list.")

    storage = form.get("storage_gb") or None
    if storage is not None:
        # Compare the text itself: int() fails on some strings isdigit() accepts, such as "²"
        allowed = {str(size): size for size in choices["storage_gb"]}
        if storage not in allowed:
            return None, ("storage_gb", "Please choose a storage size from the list.")
        storage = allowed[storage]

    condition = form.get("condition") or None
    if condition is not None and condition not in choices["condition"]:
        return None, ("condition", "Please choose a condition from the list.")

    seller_type = form.get("seller_type", "private")
    if seller_type not in choices["seller_type"]:
        return None, ("seller_type", "Please choose private seller or retailer.")

    asking_price = None
    if form.get("mode", "seller") == "buyer":
        asking_price, error = parse_asking_price(form.get("asking_price"))
        if error:
            return None, ("asking_price", error)

    return {"exact_model": model, "storage_gb": storage, "condition": condition, "seller_type": seller_type,
            "mentions_damage": form.get("mentions_damage") == "yes", "asking_price": asking_price}, None


def model_groups(models: list[str]) -> list[tuple[str, list[str]]]:
    """Models grouped by release year, newest first, for the model dropdown (release order within a year)."""
    groups: dict[str, list[str]] = {}
    for model in sorted(models, key=lambda m: model_info(m)[0], reverse=True):   # sort is stable
        year = model_info(model)[0]
        label = str(year) if year >= OLDEST_OWN_GROUP else f"{OLDEST_OWN_GROUP - 1} and earlier"
        groups.setdefault(label, []).append(model)
    return list(groups.items())


def bar_positions(result: dict) -> dict:
    """Where to draw the range bar, as % of its width (0–100).

    The axis runs from 70% of the range's low end to 130% of its high end, so the 80% range sits in
    the middle. A listing price off the axis is drawn at the nearest end, with `listing_outside` set.
    """
    start, end = result["low"] * 0.7, max(result["high"] * 1.3, result["low"] * 0.7 + 1)

    def at(amount: float) -> float:
        return round(min(max((amount - start) / (end - start) * 100, 0), 100), 1)

    bar = {"low": at(result["low"]), "high": at(result["high"]), "price": at(result["price"])}
    if result.get("asking_price") is not None:
        bar["listing"] = at(result["asking_price"])
        bar["listing_outside"] = not start <= result["asking_price"] <= end
    return bar


@app.route("/", methods=["GET", "POST"])
def index():
    choices = options()
    bundle = load()
    result, error, error_field = None, None, None

    if request.method == "POST":
        args, problem = read_form(request.form, choices)
        if problem:
            error_field, error = problem
        else:
            try:
                result = predict(**args)
            except ValueError:
                error = "Something in the form isn't valid. Please check your choices and try again."

    return render_template(
        "index.html",
        model_groups=model_groups(choices["exact_model"]),
        storage_options=choices["storage_gb"],
        condition_options=choices["condition"],
        condition_hints=CONDITION_HINTS,
        label_headings=LABEL_HEADINGS,
        bar=bar_positions(result) if result else None,
        n_listings=bundle["n_listings"],
        n_models=len(bundle["exact_models"]),
        collected_at=datetime.fromisoformat(bundle["data_collected_at"]),
        range_pct=round(LEVEL * 100),
        max_asking_price=MAX_ASKING_PRICE,
        result=result,
        error=error,
        error_field=error_field,
        form=request.form,
    )
