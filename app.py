from flask import Flask, render_template, request, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db, init_db, seed_db, create_user, get_user_by_email

app = Flask(__name__)
app.secret_key = "dev-secret-change-in-prod"


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

    user = {
        "name":         "Priya Sharma",
        "email":        "priya@example.com",
        "member_since": "January 2026",
        "initials":     "PS",
    }
    stats = {
        "total_spent":       "₹14,832.50",
        "transaction_count": 23,
        "top_category":      "Food",
    }
    transactions = [
        {"date": "20 Jun 2026", "description": "Grocery run",            "category": "Food",          "amount": "₹842.50"},
        {"date": "18 Jun 2026", "description": "Electricity bill",       "category": "Bills",         "amount": "₹1,240.00"},
        {"date": "15 Jun 2026", "description": "New headphones",         "category": "Shopping",      "amount": "₹2,499.00"},
        {"date": "12 Jun 2026", "description": "Doctor consultation",    "category": "Health",        "amount": "₹600.00"},
        {"date": "10 Jun 2026", "description": "Streaming subscription", "category": "Entertainment", "amount": "₹199.00"},
        {"date": "08 Jun 2026", "description": "Cab to office",          "category": "Transport",     "amount": "₹380.00"},
        {"date": "05 Jun 2026", "description": "Birthday dinner",        "category": "Food",          "amount": "₹1,850.00"},
    ]
    categories = [
        {"name": "Food",          "amount": "₹5,420.00", "percent": 37},
        {"name": "Bills",         "amount": "₹3,200.00", "percent": 22},
        {"name": "Shopping",      "amount": "₹2,499.00", "percent": 17},
        {"name": "Transport",     "amount": "₹1,540.00", "percent": 10},
        {"name": "Health",        "amount": "₹1,200.00", "percent":  8},
        {"name": "Entertainment", "amount": "₹597.50",   "percent":  4},
        {"name": "Other",         "amount": "₹376.00",   "percent":  2},
    ]
    return render_template("profile.html",
        user=user, stats=stats,
        transactions=transactions, categories=categories,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    with app.app_context():
        init_db()
        seed_db()
    app.run(debug=True, port=5001)
