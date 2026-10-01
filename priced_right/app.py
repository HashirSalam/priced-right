"""Flask app: expected asking price for an iPhone (seller mode), or how a listing compares (buyer mode).

    python -m flask --app priced_right.app run

The form only offers valid choices, but every input is checked again here, because a request
can be sent without the form. Invalid input gets a plain-language message instead of a crash.
"""
import math

from flask import Flask, render_template, request

from priced_right.final_model import options, predict

app = Flask(__name__)

LABEL_HEADINGS = {"below": "Below comparable listings", "in line": "In line with comparable listings",
                  "above": "Above comparable listings"}


def parse_asking_price(raw: str | None) -> tuple[float | None, str | None]:
    """(price, None) for a finite number above 0, else (None, message)."""
    if not raw:
        return None, "Please enter an asking price for buyer mode."
    try:
        price = float(raw)
    except ValueError:
        return None, "The asking price must be a number, e.g. 250."
    if not math.isfinite(price) or price <= 0:
        return None, "The asking price must be more than 0 €."
    return price, None


def read_form(form, choices: dict) -> tuple[dict | None, str | None]:
    """The predict() arguments from the submitted form, or a message for the first invalid input."""
    model = form.get("exact_model")
    if model not in choices["exact_model"]:
        return None, "Please choose an iPhone model from the list."

    storage = form.get("storage_gb") or None
    if storage is not None:
        # Compare the text itself: int() fails on some strings isdigit() accepts, such as "²"
        allowed = {str(size): size for size in choices["storage_gb"]}
        if storage not in allowed:
            return None, "Please choose a storage size from the list."
        storage = allowed[storage]

    condition = form.get("condition") or None
    if condition is not None and condition not in choices["condition"]:
        return None, "Please choose a condition from the list."

    seller_type = form.get("seller_type", "private")
    if seller_type not in choices["seller_type"]:
        return None, "Please choose private seller or retailer."

    asking_price = None
    if form.get("mode", "seller") == "buyer":
        asking_price, error = parse_asking_price(form.get("asking_price"))
        if error:
            return None, error

    return {"exact_model": model, "storage_gb": storage, "condition": condition, "seller_type": seller_type,
            "mentions_damage": form.get("mentions_damage") == "yes", "asking_price": asking_price}, None


@app.route("/", methods=["GET", "POST"])
def index():
    choices = options()
    result, error = None, None

    if request.method == "POST":
        args, error = read_form(request.form, choices)
        if args is not None:
            try:
                result = predict(**args)
            except ValueError:
                error = "Something in the form isn't valid. Please check your choices and try again."

    return render_template(
        "index.html",
        models=choices["exact_model"],
        storage_options=choices["storage_gb"],
        condition_options=choices["condition"],
        label_headings=LABEL_HEADINGS,
        result=result,
        error=error,
        form=request.form,
    )
