import re
import pytest
from database.db import get_db
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def insert_empty_user(test_db):
    """Insert a second user with no expenses; return their id."""
    conn = get_db()
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Empty User", "empty@spendly.com", "hash"),
    )
    conn.commit()
    user_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("empty@spendly.com",)
    ).fetchone()[0]
    conn.close()
    return user_id


# ------------------------------------------------------------------ #
# get_user_by_id                                                      #
# ------------------------------------------------------------------ #

def test_get_user_by_id_valid(test_db):
    result = get_user_by_id(1)
    assert result is not None
    assert result["name"] == "Demo User"
    assert result["email"] == "demo@spendly.com"
    assert re.match(r"^[A-Za-z]+ \d{4}$", result["member_since"])


def test_get_user_by_id_nonexistent(test_db):
    assert get_user_by_id(9999) is None


# ------------------------------------------------------------------ #
# get_summary_stats                                                   #
# ------------------------------------------------------------------ #

def test_get_summary_stats_with_expenses(test_db):
    result = get_summary_stats(1)
    assert result["total_spent"] == "₹357.94"
    assert result["transaction_count"] == 8
    assert result["top_category"] == "Bills"


def test_get_summary_stats_no_expenses(test_db):
    uid = insert_empty_user(test_db)
    result = get_summary_stats(uid)
    assert result == {"total_spent": "₹0.00", "transaction_count": 0, "top_category": "—"}


# ------------------------------------------------------------------ #
# get_recent_transactions                                             #
# ------------------------------------------------------------------ #

def test_get_recent_transactions_with_expenses(test_db):
    result = get_recent_transactions(1)
    assert len(result) == 8
    for tx in result:
        assert "date" in tx
        assert "description" in tx
        assert "category" in tx
        assert "amount" in tx
        assert tx["amount"].startswith("₹")
    # newest date first: 2026-06-20 → "20 Jun 2026"
    assert result[0]["date"] == "20 Jun 2026"


def test_get_recent_transactions_no_expenses(test_db):
    uid = insert_empty_user(test_db)
    assert get_recent_transactions(uid) == []


# ------------------------------------------------------------------ #
# get_category_breakdown                                              #
# ------------------------------------------------------------------ #

def test_get_category_breakdown_with_expenses(test_db):
    result = get_category_breakdown(1)
    assert len(result) == 7
    # sorted by amount descending — Bills (120.00) should be first
    assert result[0]["name"] == "Bills"
    for item in result:
        assert isinstance(item["pct"], int)
        assert item["amount"].startswith("₹")
    assert sum(item["pct"] for item in result) == 100


def test_get_category_breakdown_no_expenses(test_db):
    uid = insert_empty_user(test_db)
    assert get_category_breakdown(uid) == []


# ------------------------------------------------------------------ #
# GET /profile route                                                  #
# ------------------------------------------------------------------ #

def test_profile_unauthenticated(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_authenticated(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1

    response = client.get("/profile")
    html = response.data.decode("utf-8")

    assert response.status_code == 200
    assert "Demo User" in html
    assert "demo@spendly.com" in html
    assert "₹" in html
    assert "₹357.94" in html
    assert "Bills" in html
    # 8 transaction rows — count <tr> tags inside tbody (each expense = one <tr>)
    assert html.count("<tr>") >= 9  # 1 header row + 8 data rows
