"""
tests/test_07-add-expense.py

Pytest tests for the Spendly "Add Expense" feature (Step 07 spec).

Coverage:
  - GET /expenses/add — auth guard (unauthenticated → /login)
  - GET /expenses/add — 200 with form, today's date pre-filled, ₹ symbol, all 7 categories
  - POST /expenses/add — unauthenticated → redirect to /login, no row inserted
  - POST /expenses/add — valid submission inserts one row and redirects to /profile
  - POST /expenses/add — valid submission stores correct amount, category, date
  - POST /expenses/add — description is optional: omitting it succeeds and stores NULL
  - POST /expenses/add — blank amount returns 200 with error, no row inserted
  - POST /expenses/add — zero or negative amounts return 200 with error, no row inserted
  - POST /expenses/add — invalid or missing date returns 200 with error, no row inserted
  - POST /expenses/add — invalid category (wrong case, empty, unknown) returns 200 with error
  - POST /expenses/add — form retains submitted values when validation fails
  - POST /expenses/add — SQL injection in description field stored safely, table intact
  - POST /expenses/add — every one of the 7 allowed categories is individually accepted

Fixtures 'test_db' and 'client' are defined in tests/conftest.py.
'test_db' monkeypatches database.db.DB_PATH to a per-test tmp file and
calls init_db() + seed_db(), so each test starts with 8 seed expenses for
the demo user (id=1). 'client' depends on 'test_db', so DB_PATH is
already patched whenever 'client' is active.
"""

from datetime import datetime

import pytest

from database.db import get_db

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEMO_USER_ID = 1  # seed_db() always inserts the demo user first

VALID_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

# The seed data inserts 8 expenses for DEMO_USER_ID.
SEED_EXPENSE_COUNT = 8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login(client, user_id=DEMO_USER_ID):
    """Inject user_id into the Flask session without touching the login form."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _expense_count(user_id=DEMO_USER_ID):
    """Return the number of expense rows for *user_id* via the active DB connection.

    Uses get_db() which reads from the monkeypatched DB_PATH, so it always
    reflects the in-flight test database.
    """
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return row[0]


def _fetch_expense_by_description(description):
    """Return the first expense row whose description matches, or None."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM expenses WHERE description = ?", (description,)
    ).fetchone()
    conn.close()
    return row


# ===========================================================================
# GET /expenses/add
# ===========================================================================

class TestGetAddExpense:
    """Tests for GET /expenses/add."""

    # -----------------------------------------------------------------------
    # Auth guard
    # -----------------------------------------------------------------------

    def test_unauthenticated_get_redirects(self, client):
        response = client.get("/expenses/add")
        assert response.status_code == 302, (
            "Unauthenticated GET /expenses/add must redirect, got "
            f"{response.status_code}"
        )

    def test_unauthenticated_get_redirect_target_is_login(self, client):
        response = client.get("/expenses/add")
        assert "/login" in response.headers["Location"], (
            "Unauthenticated redirect must point to /login"
        )

    # -----------------------------------------------------------------------
    # Authenticated — basic render
    # -----------------------------------------------------------------------

    def test_authenticated_get_returns_200(self, client):
        _login(client)
        response = client.get("/expenses/add")
        assert response.status_code == 200, (
            "Authenticated GET /expenses/add must return 200"
        )

    # -----------------------------------------------------------------------
    # Form content
    # -----------------------------------------------------------------------

    def test_form_has_amount_input(self, client):
        _login(client)
        html = client.get("/expenses/add").data.decode("utf-8")
        assert 'name="amount"' in html, (
            "Add-expense form must include an amount input field"
        )

    def test_form_has_category_select(self, client):
        _login(client)
        html = client.get("/expenses/add").data.decode("utf-8")
        assert 'name="category"' in html, (
            "Add-expense form must include a category select field"
        )

    def test_form_has_date_input(self, client):
        _login(client)
        html = client.get("/expenses/add").data.decode("utf-8")
        assert 'name="date"' in html, (
            "Add-expense form must include a date input field"
        )

    def test_form_has_description_input(self, client):
        _login(client)
        html = client.get("/expenses/add").data.decode("utf-8")
        assert 'name="description"' in html, (
            "Add-expense form must include a description input field"
        )

    def test_form_contains_todays_date_prefilled(self, client):
        _login(client)
        today = datetime.today().strftime("%Y-%m-%d")
        html = client.get("/expenses/add").data.decode("utf-8")
        assert today in html, (
            f"Add-expense form must pre-fill today's date ({today})"
        )

    def test_form_displays_rupee_symbol(self, client):
        _login(client)
        html = client.get("/expenses/add").data.decode("utf-8")
        assert "₹" in html, (
            "Add-expense form must display the INR currency symbol ₹"
        )

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_form_lists_each_valid_category(self, client, category):
        _login(client)
        html = client.get("/expenses/add").data.decode("utf-8")
        assert category in html, (
            f"Category option '{category}' must appear in the add-expense form"
        )

    def test_form_contains_cancel_link_to_profile(self, client):
        _login(client)
        html = client.get("/expenses/add").data.decode("utf-8")
        assert "/profile" in html, (
            "Add-expense form must contain a Cancel link back to /profile"
        )


# ===========================================================================
# POST /expenses/add
# ===========================================================================

class TestPostAddExpense:
    """Tests for POST /expenses/add."""

    # -----------------------------------------------------------------------
    # Auth guard
    # -----------------------------------------------------------------------

    def test_unauthenticated_post_redirects(self, client):
        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Lunch",
        })
        assert response.status_code == 302, (
            "Unauthenticated POST /expenses/add must redirect"
        )

    def test_unauthenticated_post_redirect_target_is_login(self, client):
        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Lunch",
        })
        assert "/login" in response.headers["Location"], (
            "Unauthenticated POST redirect must point to /login"
        )

    def test_unauthenticated_post_does_not_insert_row(self, client, test_db):
        before = _expense_count()
        client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Unauthenticated attempt",
        })
        after = _expense_count()
        assert after == before, (
            "Unauthenticated POST must not insert any expense row"
        )

    # -----------------------------------------------------------------------
    # Happy path — full valid submission
    # -----------------------------------------------------------------------

    def test_valid_post_redirects(self, client):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": "75.50",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Grocery store",
        })
        assert response.status_code == 302, (
            "Valid POST must redirect (POST/Redirect/GET pattern)"
        )

    def test_valid_post_redirects_to_profile(self, client):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": "75.50",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Grocery store",
        })
        assert "/profile" in response.headers["Location"], (
            "Valid POST must redirect to /profile"
        )

    def test_valid_post_inserts_exactly_one_row(self, client, test_db):
        _login(client)
        before = _expense_count()
        client.post("/expenses/add", data={
            "amount": "75.50",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Grocery store",
        })
        after = _expense_count()
        assert after == before + 1, (
            f"Valid POST must insert exactly one expense row; "
            f"before={before}, after={after}"
        )

    def test_valid_post_stores_correct_amount(self, client, test_db):
        _login(client)
        client.post("/expenses/add", data={
            "amount": "99.99",
            "category": "Transport",
            "date": "2026-07-01",
            "description": "Train ticket for amount test",
        })
        row = _fetch_expense_by_description("Train ticket for amount test")
        assert row is not None, "Expense row must exist after valid POST"
        assert row["amount"] == 99.99, (
            f"Stored amount must be 99.99, got {row['amount']}"
        )

    def test_valid_post_stores_correct_category(self, client, test_db):
        _login(client)
        client.post("/expenses/add", data={
            "amount": "30.00",
            "category": "Health",
            "date": "2026-07-02",
            "description": "Vitamins for category test",
        })
        row = _fetch_expense_by_description("Vitamins for category test")
        assert row is not None, "Expense row must exist after valid POST"
        assert row["category"] == "Health", (
            f"Stored category must be 'Health', got '{row['category']}'"
        )

    def test_valid_post_stores_correct_date(self, client, test_db):
        _login(client)
        client.post("/expenses/add", data={
            "amount": "20.00",
            "category": "Bills",
            "date": "2026-07-03",
            "description": "Internet bill for date test",
        })
        row = _fetch_expense_by_description("Internet bill for date test")
        assert row is not None, "Expense row must exist after valid POST"
        assert row["date"] == "2026-07-03", (
            f"Stored date must be '2026-07-03', got '{row['date']}'"
        )

    def test_valid_post_stores_correct_user_id(self, client, test_db):
        _login(client)
        client.post("/expenses/add", data={
            "amount": "15.00",
            "category": "Other",
            "date": "2026-07-04",
            "description": "User ID check expense",
        })
        row = _fetch_expense_by_description("User ID check expense")
        assert row is not None, "Expense row must exist after valid POST"
        assert row["user_id"] == DEMO_USER_ID, (
            f"Expense must be owned by user {DEMO_USER_ID}, got {row['user_id']}"
        )

    # -----------------------------------------------------------------------
    # Description is optional
    # -----------------------------------------------------------------------

    def test_post_without_description_redirects_to_profile(self, client):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Other",
            "date": "2026-07-05",
            "description": "",
        })
        assert response.status_code == 302, (
            "POST without description must redirect (description is optional)"
        )
        assert "/profile" in response.headers["Location"], (
            "POST without description must redirect to /profile"
        )

    def test_post_without_description_inserts_row(self, client, test_db):
        _login(client)
        before = _expense_count()
        client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Other",
            "date": "2026-07-05",
            "description": "",
        })
        after = _expense_count()
        assert after == before + 1, (
            "POST without description must still insert one expense row"
        )

    def test_post_omitting_description_key_succeeds(self, client, test_db):
        """Submitting no description key at all (not just empty string) must succeed."""
        _login(client)
        before = _expense_count()
        response = client.post("/expenses/add", data={
            "amount": "45.00",
            "category": "Shopping",
            "date": "2026-07-06",
            # 'description' key intentionally omitted
        })
        after = _expense_count()
        assert response.status_code == 302, (
            "Omitting description key must still succeed"
        )
        assert after == before + 1, (
            "Omitting description key must insert one expense row"
        )

    # -----------------------------------------------------------------------
    # Validation — blank amount
    # -----------------------------------------------------------------------

    def test_blank_amount_returns_200(self, client):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": "",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Blank amount test",
        })
        assert response.status_code == 200, (
            "Blank amount must re-render the form (200), not redirect"
        )

    def test_blank_amount_response_contains_error(self, client):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": "",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Blank amount test",
        })
        html = response.data.decode("utf-8")
        # The page must communicate an error — any of these markers are acceptable
        error_present = (
            "error" in html.lower()
            or "required" in html.lower()
            or "invalid" in html.lower()
        )
        assert error_present, (
            "Blank amount must trigger an inline error message in the response"
        )

    def test_blank_amount_does_not_insert_row(self, client, test_db):
        _login(client)
        before = _expense_count()
        client.post("/expenses/add", data={
            "amount": "",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Blank amount test",
        })
        after = _expense_count()
        assert after == before, (
            "Blank amount must not insert any expense row"
        )

    # -----------------------------------------------------------------------
    # Validation — zero and negative amounts (parametrized)
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("bad_amount", ["0", "0.00", "-1", "-100", "-0.01"])
    def test_nonpositive_amount_returns_200(self, client, bad_amount):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": bad_amount,
            "category": "Food",
            "date": "2026-06-15",
            "description": "Nonpositive amount test",
        })
        assert response.status_code == 200, (
            f"Amount '{bad_amount}' must re-render the form (200), not redirect"
        )

    @pytest.mark.parametrize("bad_amount", ["0", "0.00", "-1", "-100", "-0.01"])
    def test_nonpositive_amount_response_contains_error(self, client, bad_amount):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": bad_amount,
            "category": "Food",
            "date": "2026-06-15",
            "description": "Nonpositive amount test",
        })
        html = response.data.decode("utf-8")
        error_present = (
            "error" in html.lower()
            or "zero" in html.lower()
            or "positive" in html.lower()
            or "greater" in html.lower()
            or "invalid" in html.lower()
        )
        assert error_present, (
            f"Amount '{bad_amount}' must trigger an inline error message"
        )

    @pytest.mark.parametrize("bad_amount", ["0", "0.00", "-1", "-100", "-0.01"])
    def test_nonpositive_amount_does_not_insert_row(self, client, test_db, bad_amount):
        _login(client)
        before = _expense_count()
        client.post("/expenses/add", data={
            "amount": bad_amount,
            "category": "Food",
            "date": "2026-06-15",
            "description": "Nonpositive amount test",
        })
        after = _expense_count()
        assert after == before, (
            f"Amount '{bad_amount}' must not insert any expense row"
        )

    # -----------------------------------------------------------------------
    # Validation — invalid / missing date (parametrized)
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("bad_date", [
        "",               # missing entirely
        "not-a-date",     # free text
        "15/06/2026",     # wrong format (DD/MM/YYYY)
        "2026-13-01",     # month 13
        "2026-00-01",     # month 0
        "20261501",       # no separators
    ])
    def test_invalid_date_returns_200(self, client, bad_date):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": bad_date,
            "description": "Invalid date test",
        })
        assert response.status_code == 200, (
            f"Date '{bad_date}' must re-render the form (200), not redirect"
        )

    @pytest.mark.parametrize("bad_date", [
        "",
        "not-a-date",
        "15/06/2026",
        "2026-13-01",
    ])
    def test_invalid_date_response_contains_error(self, client, bad_date):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": bad_date,
            "description": "Invalid date test",
        })
        html = response.data.decode("utf-8")
        error_present = (
            "error" in html.lower()
            or "date" in html.lower()
            or "valid" in html.lower()
            or "invalid" in html.lower()
        )
        assert error_present, (
            f"Date '{bad_date}' must trigger an inline error message"
        )

    @pytest.mark.parametrize("bad_date", [
        "",
        "not-a-date",
        "15/06/2026",
        "2026-13-01",
    ])
    def test_invalid_date_does_not_insert_row(self, client, test_db, bad_date):
        _login(client)
        before = _expense_count()
        client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": bad_date,
            "description": "Invalid date test",
        })
        after = _expense_count()
        assert after == before, (
            f"Date '{bad_date}' must not insert any expense row"
        )

    # -----------------------------------------------------------------------
    # Validation — invalid category (parametrized)
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("bad_category", [
        "",                           # empty string
        "food",                       # wrong case
        "FOOD",                       # all caps
        "Groceries",                  # plausible but not in the allowed list
        "Invalid",                    # arbitrary string
        "'; DROP TABLE expenses; --", # SQL injection attempt
    ])
    def test_invalid_category_returns_200(self, client, bad_category):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": bad_category,
            "date": "2026-06-15",
            "description": "Invalid category test",
        })
        assert response.status_code == 200, (
            f"Category '{bad_category}' must re-render the form (200), not redirect"
        )

    @pytest.mark.parametrize("bad_category", [
        "",
        "food",
        "Groceries",
        "Invalid",
    ])
    def test_invalid_category_response_contains_error(self, client, bad_category):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": bad_category,
            "date": "2026-06-15",
            "description": "Invalid category test",
        })
        html = response.data.decode("utf-8")
        error_present = (
            "error" in html.lower()
            or "category" in html.lower()
            or "valid" in html.lower()
            or "invalid" in html.lower()
        )
        assert error_present, (
            f"Category '{bad_category}' must trigger an inline error message"
        )

    @pytest.mark.parametrize("bad_category", [
        "",
        "food",
        "Groceries",
        "Invalid",
        "'; DROP TABLE expenses; --",
    ])
    def test_invalid_category_does_not_insert_row(self, client, test_db, bad_category):
        _login(client)
        before = _expense_count()
        client.post("/expenses/add", data={
            "amount": "50.00",
            "category": bad_category,
            "date": "2026-06-15",
            "description": "Invalid category test",
        })
        after = _expense_count()
        assert after == before, (
            f"Category '{bad_category}' must not insert any expense row"
        )

    # -----------------------------------------------------------------------
    # Form value retention on validation failure
    # -----------------------------------------------------------------------

    def test_form_retains_amount_after_invalid_category(self, client):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": "123.45",
            "category": "NotACategory",
            "date": "2026-06-15",
            "description": "Retention test",
        })
        html = response.data.decode("utf-8")
        assert "123.45" in html, (
            "The submitted amount must be retained in the re-rendered form"
        )

    def test_form_retains_description_after_invalid_category(self, client):
        _login(client)
        unique_desc = "UniquePhraseForRetentionCheck"
        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "NotACategory",
            "date": "2026-06-15",
            "description": unique_desc,
        })
        html = response.data.decode("utf-8")
        assert unique_desc in html, (
            "The submitted description must be retained in the re-rendered form"
        )

    def test_form_retains_date_after_invalid_amount(self, client):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": "-5",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Date retention test",
        })
        html = response.data.decode("utf-8")
        assert "2026-06-15" in html, (
            "The submitted date must be retained in the re-rendered form"
        )

    def test_form_retains_amount_after_invalid_date(self, client):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": "88.00",
            "category": "Health",
            "date": "not-a-date",
            "description": "Amount retention after bad date",
        })
        html = response.data.decode("utf-8")
        assert "88.00" in html, (
            "The submitted amount must be retained after a date validation failure"
        )

    def test_form_retains_description_after_invalid_date(self, client):
        _login(client)
        unique_desc = "DescRetainedAfterBadDate"
        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "not-a-date",
            "description": unique_desc,
        })
        html = response.data.decode("utf-8")
        assert unique_desc in html, (
            "The submitted description must be retained after a date validation failure"
        )

    def test_form_retains_amount_after_blank_amount(self, client):
        """Even for a blank amount, the other fields should be retained."""
        _login(client)
        unique_desc = "BlankAmountRetentionDesc"
        response = client.post("/expenses/add", data={
            "amount": "",
            "category": "Food",
            "date": "2026-07-10",
            "description": unique_desc,
        })
        html = response.data.decode("utf-8")
        assert unique_desc in html, (
            "Description must be retained in the form even when amount is blank"
        )

    # -----------------------------------------------------------------------
    # SQL injection safety
    # -----------------------------------------------------------------------

    def test_sql_injection_in_description_is_accepted_on_valid_post(self, client, test_db):
        """Parameterised queries must handle injection-like description without error."""
        _login(client)
        injection = "'; DROP TABLE expenses; --"
        before = _expense_count()
        response = client.post("/expenses/add", data={
            "amount": "10.00",
            "category": "Other",
            "date": "2026-07-07",
            "description": injection,
        })
        assert response.status_code == 302, (
            "A POST with SQL injection in description must still succeed and redirect"
        )
        after = _expense_count()
        assert after == before + 1, (
            "The expense with injection-like description must be inserted (1 new row)"
        )

    def test_sql_injection_in_description_stored_as_literal(self, client, test_db):
        """The injection string must be stored verbatim, not executed."""
        _login(client)
        injection = "'; DROP TABLE expenses; --"
        client.post("/expenses/add", data={
            "amount": "10.00",
            "category": "Other",
            "date": "2026-07-07",
            "description": injection,
        })
        row = _fetch_expense_by_description(injection)
        assert row is not None, (
            "SQL injection attempt in description must be stored as a literal string"
        )

    def test_expenses_table_survives_injection_attempt(self, client, test_db):
        """After an injection-like description is inserted the table must still exist."""
        _login(client)
        client.post("/expenses/add", data={
            "amount": "10.00",
            "category": "Other",
            "date": "2026-07-07",
            "description": "'; DROP TABLE expenses; --",
        })
        # Query the table — if it had been dropped this would raise OperationalError
        conn = get_db()
        count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        conn.close()
        assert count >= SEED_EXPENSE_COUNT, (
            "The expenses table must remain intact after an injection-like description"
        )

    # -----------------------------------------------------------------------
    # All 7 valid categories are individually accepted
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_each_valid_category_is_accepted(self, client, test_db, category):
        _login(client)
        before = _expense_count()
        response = client.post("/expenses/add", data={
            "amount": "10.00",
            "category": category,
            "date": "2026-07-08",
            "description": f"Category acceptance test — {category}",
        })
        after = _expense_count()
        assert response.status_code == 302, (
            f"Category '{category}' must be accepted and redirect (302)"
        )
        assert after == before + 1, (
            f"Category '{category}' must result in exactly one new expense row"
        )

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_each_valid_category_redirect_target_is_profile(self, client, category):
        _login(client)
        response = client.post("/expenses/add", data={
            "amount": "10.00",
            "category": category,
            "date": "2026-07-08",
            "description": f"Profile redirect test — {category}",
        })
        assert "/profile" in response.headers["Location"], (
            f"Category '{category}' acceptance must redirect to /profile"
        )
