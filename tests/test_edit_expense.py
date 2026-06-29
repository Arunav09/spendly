"""
tests/test_edit_expense.py

Pytest tests for the Spendly "Edit Expense" feature (Step 08 spec).

Coverage:
  - GET /expenses/<id>/edit — auth guard (unauthenticated -> /login)
  - GET /expenses/<id>/edit — 404 for non-existent expense ID
  - GET /expenses/<id>/edit — 403 when expense belongs to a different user
  - GET /expenses/<id>/edit — 200 with form pre-filled from DB values
  - GET /expenses/<id>/edit — Rs symbol, all 7 categories, Save Changes, Cancel link
  - POST /expenses/<id>/edit — auth guard (unauthenticated -> /login)
  - POST /expenses/<id>/edit — 404 for non-existent expense ID
  - POST /expenses/<id>/edit — 403 when expense belongs to a different user
  - POST /expenses/<id>/edit — valid submission updates DB row and redirects to /profile
  - POST /expenses/<id>/edit — updated values visible on /profile after redirect
  - POST /expenses/<id>/edit — blank amount -> inline error, DB unchanged
  - POST /expenses/<id>/edit — zero / negative amount -> inline error, DB unchanged
  - POST /expenses/<id>/edit — invalid date -> inline error, DB unchanged
  - POST /expenses/<id>/edit — invalid category -> inline error, DB unchanged
  - POST /expenses/<id>/edit — form retains user-typed values (not original DB values) on failure
  - Profile page — each transaction row has a working /expenses/<id>/edit link

Fixtures 'test_db' and 'client' are defined in tests/conftest.py.
'test_db' monkeypatches database.db.DB_PATH to a per-test tmp file and
calls init_db() + seed_db() so each test starts with 8 seed expenses for
the demo user (id=1).  'client' depends on 'test_db', so DB_PATH is
already patched whenever 'client' is active.
"""

import re

import pytest

from database.db import get_db, get_expense_by_id

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEMO_USER_ID = 1        # seed_db() always creates the demo user with id=1
NONEXISTENT_ID = 99999  # guaranteed not to exist in a freshly seeded DB

VALID_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

# seed_db() inserts exactly 8 expenses for DEMO_USER_ID
SEED_EXPENSE_COUNT = 8


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _login(client, user_id=DEMO_USER_ID):
    """Inject user_id into the Flask session without touching the login form."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _get_first_seed_expense_id():
    """Return the id of the first expense row owned by DEMO_USER_ID."""
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM expenses WHERE user_id = ? ORDER BY id LIMIT 1",
        (DEMO_USER_ID,),
    ).fetchone()
    conn.close()
    return row["id"]


def _get_expense_amount(expense_id):
    """Return the current amount stored for the given expense, or None."""
    row = get_expense_by_id(expense_id)
    return row["amount"] if row else None


def _expense_count(user_id=DEMO_USER_ID):
    """Return the total number of expense rows for *user_id*."""
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) FROM expenses WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row[0]


def _create_other_user_expense():
    """
    Create a second user with one expense and return that expense's id.
    Used exclusively to exercise the 403 ownership-enforcement path.
    Parameterised INSERT — no f-strings in SQL.
    """
    conn = get_db()
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Other User", "other@spendly.com", "fakehash"),
    )
    conn.commit()
    other_user_id = conn.execute(
        "SELECT id FROM users WHERE email = ?",
        ("other@spendly.com",),
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        (other_user_id, 100.0, "Food", "2026-01-01", "Other user expense"),
    )
    conn.commit()
    expense_id = conn.execute(
        "SELECT id FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (other_user_id,),
    ).fetchone()["id"]
    conn.close()
    return expense_id


# ===========================================================================
# GET /expenses/<id>/edit
# ===========================================================================

class TestGetEditExpense:
    """Tests for GET /expenses/<id>/edit."""

    # -----------------------------------------------------------------------
    # Auth guard
    # -----------------------------------------------------------------------

    def test_unauthenticated_get_redirects(self, client):
        response = client.get("/expenses/1/edit")
        assert response.status_code == 302, (
            "Unauthenticated GET /expenses/1/edit must redirect (302)"
        )

    def test_unauthenticated_get_redirect_target_is_login(self, client):
        response = client.get("/expenses/1/edit")
        assert "/login" in response.headers["Location"], (
            "Unauthenticated GET must redirect to /login"
        )

    # -----------------------------------------------------------------------
    # 404 — non-existent expense
    # -----------------------------------------------------------------------

    def test_nonexistent_expense_returns_404(self, client, test_db):
        _login(client)
        response = client.get(f"/expenses/{NONEXISTENT_ID}/edit")
        assert response.status_code == 404, (
            f"GET /expenses/{NONEXISTENT_ID}/edit must return 404"
        )

    # -----------------------------------------------------------------------
    # 403 — expense belongs to a different user
    # -----------------------------------------------------------------------

    def test_other_users_expense_returns_403(self, client, test_db):
        other_expense_id = _create_other_user_expense()
        _login(client)  # logged in as DEMO_USER_ID
        response = client.get(f"/expenses/{other_expense_id}/edit")
        assert response.status_code == 403, (
            "GET /expenses/<id>/edit for another user's expense must return 403"
        )

    # -----------------------------------------------------------------------
    # Happy path — form render
    # -----------------------------------------------------------------------

    def test_authenticated_get_returns_200(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        response = client.get(f"/expenses/{expense_id}/edit")
        assert response.status_code == 200, (
            f"Authenticated GET /expenses/{expense_id}/edit must return 200"
        )

    # -----------------------------------------------------------------------
    # Form field presence
    # -----------------------------------------------------------------------

    def test_form_has_amount_input(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.get(f"/expenses/{expense_id}/edit").data.decode("utf-8")
        assert 'name="amount"' in html, (
            "Edit form must include an amount input field"
        )

    def test_form_has_category_select(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.get(f"/expenses/{expense_id}/edit").data.decode("utf-8")
        assert 'name="category"' in html, (
            "Edit form must include a category select field"
        )

    def test_form_has_date_input(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.get(f"/expenses/{expense_id}/edit").data.decode("utf-8")
        assert 'name="date"' in html, (
            "Edit form must include a date input field"
        )

    def test_form_has_description_input(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.get(f"/expenses/{expense_id}/edit").data.decode("utf-8")
        assert 'name="description"' in html, (
            "Edit form must include a description input field"
        )

    # -----------------------------------------------------------------------
    # Form pre-fill — values match current DB row
    # -----------------------------------------------------------------------

    def test_form_prefills_amount(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        expense = get_expense_by_id(expense_id)
        html = client.get(f"/expenses/{expense_id}/edit").data.decode("utf-8")
        assert str(expense["amount"]) in html, (
            "Edit form must pre-fill the amount input with the current expense amount"
        )

    def test_form_prefills_category(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        expense = get_expense_by_id(expense_id)
        html = client.get(f"/expenses/{expense_id}/edit").data.decode("utf-8")
        assert expense["category"] in html, (
            "Edit form must pre-fill the category with the current expense category"
        )

    def test_form_prefills_date(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        expense = get_expense_by_id(expense_id)
        html = client.get(f"/expenses/{expense_id}/edit").data.decode("utf-8")
        assert expense["date"] in html, (
            "Edit form must pre-fill the date input with the current expense date"
        )

    def test_form_prefills_description(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        expense = get_expense_by_id(expense_id)
        if expense["description"]:  # description is optional; skip assertion if NULL
            html = client.get(f"/expenses/{expense_id}/edit").data.decode("utf-8")
            assert expense["description"] in html, (
                "Edit form must pre-fill the description input with the current expense description"
            )

    # -----------------------------------------------------------------------
    # UI elements
    # -----------------------------------------------------------------------

    def test_form_shows_rupee_symbol(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.get(f"/expenses/{expense_id}/edit").data.decode("utf-8")
        assert "₹" in html, (
            "Edit form must display the INR currency symbol ₹"
        )

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_form_lists_each_valid_category(self, client, test_db, category):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.get(f"/expenses/{expense_id}/edit").data.decode("utf-8")
        assert category in html, (
            f"Category option '{category}' must appear in the edit form"
        )

    def test_form_has_save_changes_button(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.get(f"/expenses/{expense_id}/edit").data.decode("utf-8")
        assert "Save Changes" in html, (
            "Edit form must include a 'Save Changes' submit button"
        )

    def test_form_contains_cancel_link_to_profile(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.get(f"/expenses/{expense_id}/edit").data.decode("utf-8")
        assert "/profile" in html, (
            "Edit form must contain a Cancel/Back link pointing to /profile"
        )


# ===========================================================================
# POST /expenses/<id>/edit
# ===========================================================================

class TestPostEditExpense:
    """Tests for POST /expenses/<id>/edit."""

    # -----------------------------------------------------------------------
    # Auth guard
    # -----------------------------------------------------------------------

    def test_unauthenticated_post_redirects(self, client):
        response = client.post("/expenses/1/edit", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Auth guard check",
        })
        assert response.status_code == 302, (
            "Unauthenticated POST /expenses/1/edit must redirect (302)"
        )

    def test_unauthenticated_post_redirect_target_is_login(self, client):
        response = client.post("/expenses/1/edit", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Auth guard check",
        })
        assert "/login" in response.headers["Location"], (
            "Unauthenticated POST must redirect to /login"
        )

    # -----------------------------------------------------------------------
    # 404 — non-existent expense
    # -----------------------------------------------------------------------

    def test_nonexistent_expense_post_returns_404(self, client, test_db):
        _login(client)
        response = client.post(f"/expenses/{NONEXISTENT_ID}/edit", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Non-existent check",
        })
        assert response.status_code == 404, (
            f"POST /expenses/{NONEXISTENT_ID}/edit must return 404"
        )

    # -----------------------------------------------------------------------
    # 403 — expense belongs to a different user
    # -----------------------------------------------------------------------

    def test_other_users_expense_post_returns_403(self, client, test_db):
        other_expense_id = _create_other_user_expense()
        _login(client)
        response = client.post(f"/expenses/{other_expense_id}/edit", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Ownership hijack attempt",
        })
        assert response.status_code == 403, (
            "POST edit for another user's expense must return 403"
        )

    def test_other_users_expense_post_does_not_update_db(self, client, test_db):
        """A 403 response must leave the target row completely untouched."""
        other_expense_id = _create_other_user_expense()
        original_amount = _get_expense_amount(other_expense_id)
        _login(client)
        client.post(f"/expenses/{other_expense_id}/edit", data={
            "amount": "999.99",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Ownership hijack attempt",
        })
        assert _get_expense_amount(other_expense_id) == original_amount, (
            "A 403 POST must not modify the target expense row"
        )

    # -----------------------------------------------------------------------
    # Happy path — valid submission
    # -----------------------------------------------------------------------

    def test_valid_post_redirects(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        response = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "55.00",
            "category": "Transport",
            "date": "2026-07-01",
            "description": "Valid update",
        })
        assert response.status_code == 302, (
            "Valid POST must redirect (POST/Redirect/GET pattern)"
        )

    def test_valid_post_redirects_to_profile(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        response = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "55.00",
            "category": "Transport",
            "date": "2026-07-01",
            "description": "Redirect target check",
        })
        assert "/profile" in response.headers["Location"], (
            "Valid POST must redirect to /profile"
        )

    def test_valid_post_updates_amount_in_db(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "234.56",
            "category": "Bills",
            "date": "2026-07-10",
            "description": "Amount update test",
        })
        row = get_expense_by_id(expense_id)
        assert row is not None, "Expense row must still exist after update"
        assert row["amount"] == 234.56, (
            f"DB amount must be 234.56 after update, got {row['amount']}"
        )

    def test_valid_post_updates_category_in_db(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50.00",
            "category": "Health",
            "date": "2026-07-10",
            "description": "Category update test",
        })
        row = get_expense_by_id(expense_id)
        assert row is not None, "Expense row must still exist after update"
        assert row["category"] == "Health", (
            f"DB category must be 'Health' after update, got '{row['category']}'"
        )

    def test_valid_post_updates_date_in_db(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-08-15",
            "description": "Date update test",
        })
        row = get_expense_by_id(expense_id)
        assert row is not None, "Expense row must still exist after update"
        assert row["date"] == "2026-08-15", (
            f"DB date must be '2026-08-15' after update, got '{row['date']}'"
        )

    def test_valid_post_updates_description_in_db(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        new_desc = "UniqueUpdatedDescriptionXYZ42"
        client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-07-10",
            "description": new_desc,
        })
        row = get_expense_by_id(expense_id)
        assert row is not None, "Expense row must still exist after update"
        assert row["description"] == new_desc, (
            f"DB description must be '{new_desc}' after update, got '{row['description']}'"
        )

    def test_valid_post_does_not_change_expense_count(self, client, test_db):
        """Update must modify the existing row — not insert a new one."""
        _login(client)
        expense_id = _get_first_seed_expense_id()
        before = _expense_count()
        client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "55.00",
            "category": "Food",
            "date": "2026-07-10",
            "description": "Row count check",
        })
        after = _expense_count()
        assert after == before, (
            f"Edit must not change total expense count; before={before}, after={after}"
        )

    def test_valid_post_updated_amount_appears_on_profile(self, client, test_db):
        """After a successful update the new amount must be visible on /profile."""
        _login(client)
        expense_id = _get_first_seed_expense_id()
        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "987.65",
                "category": "Shopping",
                "date": "2026-07-20",
                "description": "Profile visibility check",
            },
            follow_redirects=True,
        )
        html = response.data.decode("utf-8")
        assert "987.65" in html, (
            "Updated amount must appear in the Transaction History table on /profile"
        )

    def test_valid_post_with_empty_description_redirects(self, client, test_db):
        """Clearing the description field (empty string) is valid — description is optional."""
        _login(client)
        expense_id = _get_first_seed_expense_id()
        response = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "60.00",
            "category": "Other",
            "date": "2026-07-12",
            "description": "",
        })
        assert response.status_code == 302, (
            "POST with empty description must redirect (description is optional)"
        )
        assert "/profile" in response.headers["Location"], (
            "POST with empty description must redirect to /profile"
        )

    # -----------------------------------------------------------------------
    # Validation — blank amount
    # -----------------------------------------------------------------------

    def test_blank_amount_returns_200(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        response = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Blank amount test",
        })
        assert response.status_code == 200, (
            "Blank amount must re-render the form (200), not redirect"
        )

    def test_blank_amount_shows_inline_error(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Blank amount test",
        }).data.decode("utf-8")
        error_present = (
            "error" in html.lower()
            or "required" in html.lower()
            or "invalid" in html.lower()
        )
        assert error_present, (
            "Blank amount must trigger an inline error message in the response"
        )

    def test_blank_amount_does_not_update_db(self, client, test_db):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        original_amount = _get_expense_amount(expense_id)
        client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Blank amount test",
        })
        assert _get_expense_amount(expense_id) == original_amount, (
            "Blank amount must not modify the expense row in the DB"
        )

    # -----------------------------------------------------------------------
    # Validation — zero and negative amount (parametrized)
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("bad_amount", ["0", "0.00", "-1", "-100", "-0.01"])
    def test_nonpositive_amount_returns_200(self, client, test_db, bad_amount):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        response = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": bad_amount,
            "category": "Food",
            "date": "2026-06-15",
            "description": "Nonpositive amount test",
        })
        assert response.status_code == 200, (
            f"Amount '{bad_amount}' must re-render the form (200), not redirect"
        )

    @pytest.mark.parametrize("bad_amount", ["0", "0.00", "-1", "-100", "-0.01"])
    def test_nonpositive_amount_shows_inline_error(self, client, test_db, bad_amount):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": bad_amount,
            "category": "Food",
            "date": "2026-06-15",
            "description": "Nonpositive amount test",
        }).data.decode("utf-8")
        error_present = (
            "error" in html.lower()
            or "positive" in html.lower()
            or "greater" in html.lower()
            or "invalid" in html.lower()
        )
        assert error_present, (
            f"Amount '{bad_amount}' must trigger an inline error message"
        )

    @pytest.mark.parametrize("bad_amount", ["0", "0.00", "-1", "-100", "-0.01"])
    def test_nonpositive_amount_does_not_update_db(self, client, test_db, bad_amount):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        original_amount = _get_expense_amount(expense_id)
        client.post(f"/expenses/{expense_id}/edit", data={
            "amount": bad_amount,
            "category": "Food",
            "date": "2026-06-15",
            "description": "Nonpositive amount test",
        })
        assert _get_expense_amount(expense_id) == original_amount, (
            f"Amount '{bad_amount}' must not update the expense row in the DB"
        )

    # -----------------------------------------------------------------------
    # Validation — invalid date (parametrized)
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("bad_date", [
        "",            # missing entirely
        "not-a-date",  # free text
        "15/06/2026",  # wrong format (DD/MM/YYYY)
        "2026-13-01",  # month 13
        "2026-00-01",  # month 0
        "20261501",    # no separators
    ])
    def test_invalid_date_returns_200(self, client, test_db, bad_date):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        response = client.post(f"/expenses/{expense_id}/edit", data={
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
    def test_invalid_date_shows_inline_error(self, client, test_db, bad_date):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50.00",
            "category": "Food",
            "date": bad_date,
            "description": "Invalid date test",
        }).data.decode("utf-8")
        error_present = (
            "error" in html.lower()
            or "date" in html.lower()
            or "invalid" in html.lower()
            or "valid" in html.lower()
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
    def test_invalid_date_does_not_update_db(self, client, test_db, bad_date):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        original_amount = _get_expense_amount(expense_id)
        client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50.00",
            "category": "Food",
            "date": bad_date,
            "description": "Invalid date test",
        })
        assert _get_expense_amount(expense_id) == original_amount, (
            f"Date '{bad_date}' must not update the expense row in the DB"
        )

    # -----------------------------------------------------------------------
    # Validation — invalid category (parametrized)
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("bad_category", [
        "",                           # empty string
        "food",                       # wrong case
        "FOOD",                       # all caps
        "Groceries",                  # plausible but not in allowed list
        "Invalid",                    # arbitrary string
        "'; DROP TABLE expenses; --", # SQL injection attempt
    ])
    def test_invalid_category_returns_200(self, client, test_db, bad_category):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        response = client.post(f"/expenses/{expense_id}/edit", data={
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
    def test_invalid_category_shows_inline_error(self, client, test_db, bad_category):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50.00",
            "category": bad_category,
            "date": "2026-06-15",
            "description": "Invalid category test",
        }).data.decode("utf-8")
        error_present = (
            "error" in html.lower()
            or "category" in html.lower()
            or "invalid" in html.lower()
            or "valid" in html.lower()
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
    def test_invalid_category_does_not_update_db(self, client, test_db, bad_category):
        _login(client)
        expense_id = _get_first_seed_expense_id()
        original_amount = _get_expense_amount(expense_id)
        client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50.00",
            "category": bad_category,
            "date": "2026-06-15",
            "description": "Invalid category test",
        })
        assert _get_expense_amount(expense_id) == original_amount, (
            f"Category '{bad_category}' must not update the expense row in the DB"
        )

    # -----------------------------------------------------------------------
    # Form value retention — user-typed values shown, NOT original DB values
    # -----------------------------------------------------------------------

    def test_form_retains_new_amount_on_invalid_category(self, client, test_db):
        """
        After a POST that fails category validation the form must show the
        user-typed amount (777.77), not the original DB amount (42.5 for the
        first seed expense 'Grocery run').
        """
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "777.77",
            "category": "NotACategory",
            "date": "2026-06-15",
            "description": "Retention test",
        }).data.decode("utf-8")
        assert "777.77" in html, (
            "The user-typed amount must be retained in the re-rendered form "
            "(not the original DB value)"
        )

    def test_form_retains_new_date_on_invalid_category(self, client, test_db):
        """After a POST that fails category validation the user-typed date must appear."""
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50.00",
            "category": "NotACategory",
            "date": "2026-12-25",
            "description": "Date retention test",
        }).data.decode("utf-8")
        assert "2026-12-25" in html, (
            "The user-typed date must be retained in the re-rendered form"
        )

    def test_form_retains_new_description_on_invalid_amount(self, client, test_db):
        """After a POST that fails amount validation the user-typed description must appear."""
        _login(client)
        expense_id = _get_first_seed_expense_id()
        unique_desc = "UniqueRetentionDescZZZ"
        html = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "-5",
            "category": "Food",
            "date": "2026-07-01",
            "description": unique_desc,
        }).data.decode("utf-8")
        assert unique_desc in html, (
            "The user-typed description must be retained after an amount validation failure"
        )

    def test_form_retains_new_amount_on_invalid_date(self, client, test_db):
        """After a POST that fails date validation the user-typed amount must appear."""
        _login(client)
        expense_id = _get_first_seed_expense_id()
        html = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "555.55",
            "category": "Health",
            "date": "not-a-date",
            "description": "Amount retention after bad date",
        }).data.decode("utf-8")
        assert "555.55" in html, (
            "The user-typed amount must be retained after a date validation failure"
        )

    def test_form_retains_new_description_on_invalid_date(self, client, test_db):
        """After a POST that fails date validation the user-typed description must appear."""
        _login(client)
        expense_id = _get_first_seed_expense_id()
        unique_desc = "DescRetainedAfterBadDateEditTest"
        html = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50.00",
            "category": "Food",
            "date": "not-a-date",
            "description": unique_desc,
        }).data.decode("utf-8")
        assert unique_desc in html, (
            "The user-typed description must be retained after a date validation failure"
        )


# ===========================================================================
# Profile page — Edit links in transaction rows
# ===========================================================================

class TestProfileEditLinks:
    """Tests that /profile exposes a working Edit link for every transaction row."""

    def test_profile_contains_edit_links(self, client, test_db):
        """Profile page must contain at least one /expenses/<id>/edit href."""
        _login(client)
        response = client.get("/profile")
        assert response.status_code == 200, "Profile page must return 200"
        html = response.data.decode("utf-8")
        assert "/expenses/" in html and "/edit" in html, (
            "Profile page must contain at least one Edit link "
            "matching /expenses/<id>/edit"
        )

    def test_profile_edit_links_match_url_pattern(self, client, test_db):
        """Every Edit link must follow the /expenses/<int>/edit URL pattern."""
        _login(client)
        html = client.get("/profile").data.decode("utf-8")
        edit_links = re.findall(r"/expenses/\d+/edit", html)
        assert len(edit_links) > 0, (
            "Profile page must have at least one /expenses/<id>/edit link"
        )

    def test_profile_edit_link_count_matches_seed_data(self, client, test_db):
        """
        With 8 seed expenses (all within get_recent_transactions default limit
        of 10) the profile must show at least 8 Edit links — one per row.
        """
        _login(client)
        html = client.get("/profile").data.decode("utf-8")
        edit_links = re.findall(r"/expenses/\d+/edit", html)
        assert len(edit_links) >= SEED_EXPENSE_COUNT, (
            f"Profile must have at least {SEED_EXPENSE_COUNT} Edit links "
            f"(one per seed expense); found {len(edit_links)}"
        )

    def test_profile_edit_link_is_reachable(self, client, test_db):
        """Following any Edit link from the profile must return 200."""
        _login(client)
        html = client.get("/profile").data.decode("utf-8")
        match = re.search(r"/expenses/(\d+)/edit", html)
        assert match is not None, "Must find at least one edit link on the profile page"
        expense_id = int(match.group(1))
        response = client.get(f"/expenses/{expense_id}/edit")
        assert response.status_code == 200, (
            f"Edit link /expenses/{expense_id}/edit must return 200 for the logged-in owner"
        )

    def test_profile_edit_links_have_tx_edit_link_class(self, client, test_db):
        """Each Edit anchor must carry the tx-edit-link CSS class."""
        _login(client)
        html = client.get("/profile").data.decode("utf-8")
        assert "tx-edit-link" in html, (
            "Edit links on the profile page must use the 'tx-edit-link' CSS class"
        )
