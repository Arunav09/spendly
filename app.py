import math
from datetime import datetime
from flask import Flask, abort, render_template, request, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db, init_db, seed_db, create_user, get_user_by_email, insert_expense, get_expense_by_id, update_expense, delete_expense as db_delete_expense
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)

app = Flask(__name__)
app.secret_key = "dev-secret-change-in-prod"

EXPENSE_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


def _validate_date_str(s):
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        return None


def _extract_expense_form_data():
    return (
        request.form.get("amount", "").strip(),
        request.form.get("category", "").strip(),
        request.form.get("date", "").strip(),
        request.form.get("description", "").strip(),
    )


def _validate_expense_form(amount_str, category, date_str, description):
    if not amount_str:
        return "Amount is required.", None
    try:
        amount = float(amount_str)
        if amount <= 0 or not math.isfinite(amount):
            return "Amount must be a positive number.", None
    except ValueError:
        return "Amount must be a valid number.", None

    if category not in EXPENSE_CATEGORIES:
        return "Please select a valid category.", None

    if not _validate_date_str(date_str):
        return "Please enter a valid date.", None

    if description and len(description) > 200:
        return "Description must be 200 characters or fewer.", None

    return None, amount


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        name             = request.form.get("name", "").strip()
        email            = request.form.get("email", "").strip()
        password         = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not name or not email or not password or not confirm_password:
            return render_template("register.html", error="All fields are required.")

        if len(password) < 8:
            return render_template("register.html", error="Password must be at least 8 characters.")

        if password != confirm_password:
            return render_template("register.html", error="Passwords do not match.")

        if get_user_by_email(email):
            return render_template("register.html", error="An account with that email already exists.")

        create_user(name, email, generate_password_hash(password))
        user = get_user_by_email(email)
        session["user_id"] = user["id"]
        return redirect(url_for("profile"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        user = get_user_by_email(email)
        if not user or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Invalid email or password.")

        session["user_id"] = user["id"]
        return redirect(url_for("profile"))

    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user_data = get_user_by_id(user_id)
    if user_data is None:
        abort(404)

    words = user_data["name"].split()
    initials = "".join(w[0] for w in words[:2]).upper()

    user = {
        "name":         user_data["name"],
        "email":        user_data["email"],
        "member_since": user_data["member_since"],
        "initials":     initials,
    }
    raw_from = request.args.get("from", "").strip()
    raw_to   = request.args.get("to",   "").strip()

    date_from = _validate_date_str(raw_from) if raw_from else None
    date_to   = _validate_date_str(raw_to)   if raw_to   else None

    if (raw_from and date_from is None) or (raw_to and date_to is None):
        date_from = None
        date_to   = None

    stats = get_summary_stats(user_id, date_from=date_from, date_to=date_to)
    transactions = get_recent_transactions(user_id, date_from=date_from, date_to=date_to)
    categories = [
        {"name": c["name"], "amount": c["amount"], "percent": c["pct"]}
        for c in get_category_breakdown(user_id, date_from=date_from, date_to=date_to)
    ]
    return render_template("profile.html",
        user=user, stats=stats,
        transactions=transactions, categories=categories,
        date_from=date_from or "",
        date_to=date_to or "",
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    today = datetime.today().strftime("%Y-%m-%d")

    if request.method == "POST":
        amount_str, category, date_str, description = _extract_expense_form_data()

        error, amount = _validate_expense_form(amount_str, category, date_str, description)

        if error:
            return render_template(
                "add_expense.html",
                error=error,
                categories=EXPENSE_CATEGORIES,
                form={"amount": amount_str, "category": category,
                      "date": date_str, "description": description},
                today=today,
            )

        insert_expense(session["user_id"], amount, category, date_str, description or None)
        return redirect(url_for("profile"))

    return render_template("add_expense.html", categories=EXPENSE_CATEGORIES, today=today, form={})


@app.route("/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
def edit_expense(expense_id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    expense = get_expense_by_id(expense_id)
    if expense is None:
        abort(404)
    if expense["user_id"] != session["user_id"]:
        abort(403)

    if request.method == "POST":
        amount_str, category, date_str, description = _extract_expense_form_data()

        error, amount = _validate_expense_form(amount_str, category, date_str, description)
        if error:
            return render_template(
                "edit_expense.html",
                error=error,
                categories=EXPENSE_CATEGORIES,
                expense=expense,
                form={"amount": amount_str, "category": category,
                      "date": date_str, "description": description},
            )

        update_expense(expense_id, session["user_id"], amount, category, date_str, description or None)
        return redirect(url_for("profile"))

    return render_template(
        "edit_expense.html",
        categories=EXPENSE_CATEGORIES,
        expense=expense,
        form={
            "amount": expense["amount"],
            "category": expense["category"],
            "date": expense["date"],
            "description": expense["description"] or "",
        },
    )


@app.route("/expenses/<int:expense_id>/delete", methods=["GET", "POST"])
def delete_expense(expense_id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    expense = get_expense_by_id(expense_id)
    if expense is None:
        abort(404)
    if expense["user_id"] != session["user_id"]:
        abort(403)

    if request.method == "POST":
        db_delete_expense(expense_id, session["user_id"])
        return redirect(url_for("profile"))

    return render_template("delete_expense.html", expense=expense)


if __name__ == "__main__":
    with app.app_context():
        init_db()
        seed_db()
    app.run(debug=True, port=5001)
