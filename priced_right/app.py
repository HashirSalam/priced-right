from flask import Flask, render_template, request
from priced_right.final_model import options, predict

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error = None

    if request.method == "POST":
        selected_model = request.form.get("exact_model")
        selected_storage = request.form.get("storage_gb")
        selected_condition = request.form.get("condition")

        mode = request.form.get("mode", "seller")
        asking_price = request.form.get("asking_price")
        if mode == "buyer" and not asking_price:
            error = "Please enter an asking price for buyer mode."

        if error is None:
            try:
                result = predict(
                    exact_model=selected_model,
                    storage_gb=int(selected_storage) if selected_storage else None,
                    condition=selected_condition or None,
                    seller_type=request.form.get("seller_type", "private"),
                    mentions_damage=request.form.get("mentions_damage") == "yes",
                    asking_price=float(asking_price)
                    if mode == "buyer" and asking_price
                    else None,
                )
            except ValueError as e:
                error = str(e)

    return render_template(
        "index.html",
        models=options()["exact_model"],
        storage_options=options()["storage_gb"],
        condition_options=options()["condition"],
        result=result,
        error=error,
        form=request.form,
    )
