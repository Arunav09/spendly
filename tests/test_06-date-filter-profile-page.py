"""
tests/test_06-date-filter-profile-page.py

Pytest tests for the Spendly date-filter feature (Step 06 spec).

Coverage:
  - GET /profile auth guard (with and without date params)
  - GET /profile with no params — full unfiltered baseline
  - GET /profile?from=2026-06-01&to=2026-06-10 — 5-expense filtered view
  - GET /profile?from=&to= — empty string params treated as "All Time"
  - Invalid date param handling — silently ignored, full view returned, no 500
  - Date range with no matching expenses — ₹0.00 total, 0 transactions, empty breakdown
  - Unit tests for get_summary_stats with and without date_from / date_to
  - Unit tests for get_recent_transactions with and without date_from / date_to
  - Unit tests for get_category_breakdown with and without date_from / date_to

Fixtures test_db and client are defined in tests/conftest.py.
test_db monkeypatches database.db.DB_PATH to a per-test tmp file, calls
init_db() and seed_db(), and returns the db path.
client consumes test_db so every test gets a fresh isolated database.
"""

import pytest

from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)

# ---------------------------------------------------------------------------
# Constants derived from seed data
# ---------------------------------------------------------------------------

DEMO_USER_ID = 1  # seed_db() always inserts the demo user first

# Descriptions grouped by whether they fall inside 2026-06-01 to 2026-06-10
IN_RANGE_JUN01_10 = [
    "Grocery run",             # 2026-06-01  Food        ₹42.50
    "Bus pass top-up",         # 2026-06-03  Transport   ₹18.00
    "Electricity bill",        # 2026-06-05  Bills       ₹120.00
    "Pharmacy",                # 2026-06-08  Health      ₹35.00
    "Streaming subscription",  # 2026-06-10  Entertainment ₹15.99
]

OUT_OF_RANGE_JUN01_10 = [
    "New headphones",  # 2026-06-14  Shopping  ₹89.95
    "Miscellaneous",   # 2026-06-18  Other     ₹25.00
    "Lunch takeout",   # 2026-06-20  Food      ₹11.50
]

ALL_DESCRIPTIONS = IN_RANGE_JUN01_10 + OUT_OF_RANGE_JUN01_10

# Pre-computed monetary totals (hand-verified against seed data)
# All 8:     42.50+18.00+120.00+35.00+15.99+89.95+25.00+11.50 = 357.94
# Jun01-10:  42.50+18.00+120.00+35.00+15.99                   = 231.49
# Jun14+:    89.95+25.00+11.50                                 = 126.45
# to Jun05:  42.50+18.00+120.00                               = 180.50
TOTAL_ALL       = "₹357.94"
TOTAL_JUN01_10  = "₹231.49"
TOTAL_JUN14_ON  = "₹126.45"
TOTAL_UPTO_JUN05 = "₹180.50"


# ===========================================================================
# Route-level tests — GET /profile
# ===========================================================================

class TestProfileDateFilterRoute:
    """Integration tests for GET /profile with date-range query parameters."""

    def _login_demo_user(self, client):
        """Inject the demo user's session without going through the login form."""
        with client.session_transaction() as sess:
            sess["user_id"] = DEMO_USER_ID

    # -----------------------------------------------------------------------
    # Auth guard
    # -----------------------------------------------------------------------

    def test_unauthenticated_get_profile_redirects_to_login(self, client):
        """Un-authed /profile must 302 to /login regardless of query params."""
        response = client.get("/profile")
        assert response.status_code == 302, (
            "Unauthenticated /profile must redirect, got status "
            f"{response.status_code}"
        )
        assert "/login" in response.headers["Location"], (
            "Redirect target must be /login"
        )

    def test_unauthenticated_get_profile_with_date_params_redirects_to_login(self, client):
        """Adding date params must not bypass the auth guard."""
        response = client.get("/profile?from=2026-06-01&to=2026-06-10")
        assert response.status_code == 302, (
            "Un-authed filtered /profile must still redirect"
        )
        assert "/login" in response.headers["Location"]

    # -----------------------------------------------------------------------
    # No-filter baseline — all expenses shown
    # -----------------------------------------------------------------------

    def test_no_filter_returns_200(self, client):
        self._login_demo_user(client)
        response = client.get("/profile")
        assert response.status_code == 200, (
            "Authenticated /profile with no params must return 200"
        )

    def test_no_filter_shows_rupee_symbol_in_response(self, client):
        self._login_demo_user(client)
        html = client.get("/profile").data.decode("utf-8")
        assert "₹" in html, "Profile page must display INR currency symbol ₹"

    def test_no_filter_shows_all_time_total(self, client):
        self._login_demo_user(client)
        html = client.get("/profile").data.decode("utf-8")
        assert TOTAL_ALL in html, (
            f"Unfiltered profile must show total {TOTAL_ALL} for all 8 seed expenses"
        )

    def test_no_filter_shows_all_seed_descriptions(self, client):
        self._login_demo_user(client)
        html = client.get("/profile").data.decode("utf-8")
        for description in ALL_DESCRIPTIONS:
            assert description in html, (
                f"Unfiltered profile must display expense '{description}'"
            )

    # -----------------------------------------------------------------------
    # Jun 01-10 filter — 5 expenses, ₹231.49
    # -----------------------------------------------------------------------

    def test_jun01_to_jun10_filter_returns_200(self, client):
        self._login_demo_user(client)
        response = client.get("/profile?from=2026-06-01&to=2026-06-10")
        assert response.status_code == 200, (
            "Date-filtered /profile must return 200"
        )

    def test_jun01_to_jun10_filter_shows_correct_total(self, client):
        self._login_demo_user(client)
        html = client.get("/profile?from=2026-06-01&to=2026-06-10").data.decode("utf-8")
        assert TOTAL_JUN01_10 in html, (
            f"Jun 01-10 filter must show total {TOTAL_JUN01_10}"
        )

    def test_jun01_to_jun10_filter_does_not_show_all_time_total(self, client):
        """Filtered total must not show the unfiltered all-time figure."""
        self._login_demo_user(client)
        html = client.get("/profile?from=2026-06-01&to=2026-06-10").data.decode("utf-8")
        assert TOTAL_ALL not in html, (
            f"Filtered page must not display all-time total {TOTAL_ALL}"
        )

    def test_jun01_to_jun10_filter_shows_in_range_descriptions(self, client):
        self._login_demo_user(client)
        html = client.get("/profile?from=2026-06-01&to=2026-06-10").data.decode("utf-8")
        for description in IN_RANGE_JUN01_10:
            assert description in html, (
                f"In-range expense '{description}' must appear in filtered view"
            )

    def test_jun01_to_jun10_filter_hides_out_of_range_descriptions(self, client):
        self._login_demo_user(client)
        html = client.get("/profile?from=2026-06-01&to=2026-06-10").data.decode("utf-8")
        for description in OUT_OF_RANGE_JUN01_10:
            assert description not in html, (
                f"Out-of-range expense '{description}' must not appear in filtered view"
            )

    def test_jun01_to_jun10_filter_shows_only_in_range_categories(self, client):
        """Category breakdown must only include categories present in the date range."""
        self._login_demo_user(client)
        html = client.get("/profile?from=2026-06-01&to=2026-06-10").data.decode("utf-8")
        # In-range categories (Jun 01-10)
        for category in ("Bills", "Food", "Transport", "Health", "Entertainment"):
            assert category in html, (
                f"In-range category '{category}' must appear in filtered breakdown"
            )
        # Out-of-range categories (Jun 14, 18, 20)
        assert "Shopping" not in html, (
            "Shopping (Jun 14) must not appear in Jun 01-10 category breakdown"
        )
        assert "Other" not in html, (
            "Other (Jun 18) must not appear in Jun 01-10 category breakdown"
        )

    # -----------------------------------------------------------------------
    # "All Time" — empty string params treated as no filter
    # -----------------------------------------------------------------------

    def test_empty_string_from_and_to_params_shows_all_expenses(self, client):
        """`?from=&to=` must behave identically to no params — no filter applied."""
        self._login_demo_user(client)
        response = client.get("/profile?from=&to=")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert TOTAL_ALL in html, (
            f"Empty-string params must fall back to all-time total {TOTAL_ALL}"
        )

    def test_empty_string_params_shows_all_seed_descriptions(self, client):
        self._login_demo_user(client)
        html = client.get("/profile?from=&to=").data.decode("utf-8")
        for description in ALL_DESCRIPTIONS:
            assert description in html, (
                f"'{description}' must appear when filter params are empty strings"
            )

    # -----------------------------------------------------------------------
    # Invalid date params — silently ignored, page still renders
    # -----------------------------------------------------------------------

    def test_invalid_from_param_returns_200_not_500(self, client):
        """A non-date value for `from` must be silently discarded, never raise 500."""
        self._login_demo_user(client)
        response = client.get("/profile?from=bad&to=2026-06-30")
        assert response.status_code == 200, (
            "Invalid ?from param must not cause a server error"
        )

    def test_invalid_from_param_shows_all_expenses(self, client):
        """When `from` is invalid both params are dropped — full unfiltered view."""
        self._login_demo_user(client)
        html = client.get("/profile?from=bad&to=2026-06-30").data.decode("utf-8")
        assert TOTAL_ALL in html, (
            f"Invalid ?from must fall back to unfiltered total {TOTAL_ALL}"
        )

    def test_invalid_to_param_returns_200_not_500(self, client):
        self._login_demo_user(client)
        response = client.get("/profile?from=2026-06-01&to=not-a-date")
        assert response.status_code == 200, (
            "Invalid ?to param must not cause a server error"
        )

    def test_invalid_to_param_shows_all_expenses(self, client):
        """When `to` is invalid both params are dropped — full unfiltered view."""
        self._login_demo_user(client)
        html = client.get("/profile?from=2026-06-01&to=not-a-date").data.decode("utf-8")
        assert TOTAL_ALL in html, (
            f"Invalid ?to must fall back to unfiltered total {TOTAL_ALL}"
        )

    def test_both_params_invalid_returns_200_and_shows_all_expenses(self, client):
        self._login_demo_user(client)
        response = client.get("/profile?from=foo&to=bar")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert TOTAL_ALL in html, (
            "Both params invalid must still render full unfiltered view"
        )

    def test_non_iso_date_format_is_silently_ignored(self, client):
        """DD/MM/YYYY is not a valid YYYY-MM-DD string — both params must be dropped."""
        self._login_demo_user(client)
        response = client.get("/profile?from=01/06/2026&to=10/06/2026")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert TOTAL_ALL in html, (
            "Non-ISO date format must be ignored and fall back to all-time view"
        )

    # -----------------------------------------------------------------------
    # No expenses in the selected range — zero state
    # -----------------------------------------------------------------------

    def test_empty_range_for_user_returns_200(self, client):
        """A range that contains no expenses for the demo user must still render."""
        self._login_demo_user(client)
        response = client.get("/profile?from=2026-07-01&to=2026-07-31")
        assert response.status_code == 200, (
            "Empty date range must return 200, not an error"
        )

    def test_empty_range_shows_zero_total(self, client):
        self._login_demo_user(client)
        html = client.get("/profile?from=2026-07-01&to=2026-07-31").data.decode("utf-8")
        assert "₹0.00" in html, (
            "Date range with no expenses must display ₹0.00 total"
        )

    def test_empty_range_shows_no_transaction_descriptions(self, client):
        self._login_demo_user(client)
        html = client.get("/profile?from=2026-07-01&to=2026-07-31").data.decode("utf-8")
        for description in ALL_DESCRIPTIONS:
            assert description not in html, (
                f"'{description}' must not appear when the date range has no matching expenses"
            )


# ===========================================================================
# Unit tests — get_summary_stats
# ===========================================================================

class TestGetSummaryStats:

    def test_no_filter_returns_all_expense_total(self, test_db):
        result = get_summary_stats(DEMO_USER_ID)
        assert result["total_spent"] == TOTAL_ALL, (
            f"Unfiltered total must be {TOTAL_ALL}"
        )

    def test_no_filter_returns_correct_transaction_count(self, test_db):
        result = get_summary_stats(DEMO_USER_ID)
        assert result["transaction_count"] == 8, (
            "Unfiltered summary must count all 8 seed expenses"
        )

    def test_no_filter_identifies_bills_as_top_category(self, test_db):
        result = get_summary_stats(DEMO_USER_ID)
        assert result["top_category"] == "Bills", (
            "Bills (₹120.00) is the highest-spending category across all seed data"
        )

    def test_jun01_to_jun10_returns_five_transactions(self, test_db):
        result = get_summary_stats(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-10",
        )
        assert result["transaction_count"] == 5, (
            "5 seed expenses fall within Jun 01-10 (inclusive)"
        )

    def test_jun01_to_jun10_returns_correct_total(self, test_db):
        result = get_summary_stats(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-10",
        )
        assert result["total_spent"] == TOTAL_JUN01_10, (
            f"Jun 01-10 total must be {TOTAL_JUN01_10}"
        )

    def test_jun01_to_jun10_identifies_bills_as_top_category(self, test_db):
        result = get_summary_stats(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-10",
        )
        assert result["top_category"] == "Bills", (
            "Bills (₹120.00) is still the largest category within Jun 01-10"
        )

    def test_date_from_boundary_is_inclusive(self, test_db):
        """An expense on exactly date_from must be counted."""
        result = get_summary_stats(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-01",
        )
        assert result["transaction_count"] == 1, (
            "Expense on exactly date_from (Jun 01) must be included"
        )
        assert result["total_spent"] == "₹42.50"

    def test_date_to_boundary_is_inclusive(self, test_db):
        """An expense on exactly date_to must be counted."""
        result = get_summary_stats(
            DEMO_USER_ID,
            date_from="2026-06-20",
            date_to="2026-06-20",
        )
        assert result["transaction_count"] == 1, (
            "Expense on exactly date_to (Jun 20) must be included"
        )
        assert result["total_spent"] == "₹11.50"

    def test_empty_date_range_returns_zero_state(self, test_db):
        """A range with no matching expenses must return the sentinel zero-state dict."""
        result = get_summary_stats(
            DEMO_USER_ID,
            date_from="2026-07-01",
            date_to="2026-07-31",
        )
        assert result == {
            "total_spent": "₹0.00",
            "transaction_count": 0,
            "top_category": "—",
        }, "Empty range must return the zero-state sentinel dict exactly"

    def test_only_date_from_filters_lower_bound(self, test_db):
        """date_from without date_to: expenses on/after Jun 14 (3 expenses)."""
        result = get_summary_stats(DEMO_USER_ID, date_from="2026-06-14")
        assert result["transaction_count"] == 3, (
            "3 expenses fall on or after Jun 14"
        )
        assert result["total_spent"] == TOTAL_JUN14_ON

    def test_only_date_to_filters_upper_bound(self, test_db):
        """date_to without date_from: expenses on/before Jun 05 (3 expenses)."""
        result = get_summary_stats(DEMO_USER_ID, date_to="2026-06-05")
        assert result["transaction_count"] == 3, (
            "3 expenses fall on or before Jun 05"
        )
        assert result["total_spent"] == TOTAL_UPTO_JUN05

    def test_single_day_range(self, test_db):
        """date_from == date_to returns only that single day's expense."""
        result = get_summary_stats(
            DEMO_USER_ID,
            date_from="2026-06-05",
            date_to="2026-06-05",
        )
        assert result["transaction_count"] == 1
        assert result["total_spent"] == "₹120.00"
        assert result["top_category"] == "Bills"

    def test_total_spent_is_rupee_prefixed(self, test_db):
        result = get_summary_stats(DEMO_USER_ID)
        assert result["total_spent"].startswith("₹"), (
            "total_spent must always be formatted as INR (₹-prefixed)"
        )


# ===========================================================================
# Unit tests — get_recent_transactions
# ===========================================================================

class TestGetRecentTransactions:

    def test_no_filter_returns_all_eight_expenses(self, test_db):
        result = get_recent_transactions(DEMO_USER_ID)
        assert len(result) == 8, (
            "Without a filter, all 8 seed expenses must be returned"
        )

    def test_no_filter_order_is_newest_first(self, test_db):
        result = get_recent_transactions(DEMO_USER_ID)
        assert result[0]["date"] == "20 Jun 2026", (
            "Most recent expense (Jun 20) must appear first"
        )
        assert result[0]["description"] == "Lunch takeout"

    def test_no_filter_oldest_expense_is_last(self, test_db):
        result = get_recent_transactions(DEMO_USER_ID)
        assert result[-1]["date"] == "01 Jun 2026", (
            "Oldest expense (Jun 01) must appear last"
        )
        assert result[-1]["description"] == "Grocery run"

    def test_each_transaction_has_required_fields(self, test_db):
        result = get_recent_transactions(DEMO_USER_ID)
        required_keys = ("date", "description", "category", "amount")
        for tx in result:
            for key in required_keys:
                assert key in tx, (
                    f"Each transaction dict must contain the key '{key}'"
                )

    def test_each_transaction_amount_is_rupee_prefixed(self, test_db):
        result = get_recent_transactions(DEMO_USER_ID)
        for tx in result:
            assert tx["amount"].startswith("₹"), (
                f"Amount must be INR-prefixed; got '{tx['amount']}'"
            )

    def test_jun01_to_jun10_returns_five_transactions(self, test_db):
        result = get_recent_transactions(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-10",
        )
        assert len(result) == 5, (
            "5 seed expenses fall within Jun 01-10 (inclusive)"
        )

    def test_jun01_to_jun10_order_is_newest_first(self, test_db):
        """Within the filtered range the newest expense must still come first."""
        result = get_recent_transactions(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-10",
        )
        assert result[0]["date"] == "10 Jun 2026", (
            "Entertainment (Jun 10) is the newest in-range expense and must be first"
        )
        assert result[-1]["date"] == "01 Jun 2026", (
            "Grocery run (Jun 01) is the oldest in-range expense and must be last"
        )

    def test_date_from_boundary_is_inclusive(self, test_db):
        result = get_recent_transactions(
            DEMO_USER_ID,
            date_from="2026-06-20",
            date_to="2026-06-20",
        )
        assert len(result) == 1, "Expense on exactly date_from must be included"
        assert result[0]["description"] == "Lunch takeout"

    def test_date_to_boundary_is_inclusive(self, test_db):
        result = get_recent_transactions(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-01",
        )
        assert len(result) == 1, "Expense on exactly date_to must be included"
        assert result[0]["description"] == "Grocery run"

    def test_empty_date_range_returns_empty_list(self, test_db):
        result = get_recent_transactions(
            DEMO_USER_ID,
            date_from="2026-07-01",
            date_to="2026-07-31",
        )
        assert result == [], (
            "A date range with no matching expenses must return an empty list"
        )

    def test_only_date_from_filters_lower_bound(self, test_db):
        """date_from=2026-06-18 yields Miscellaneous (Jun 18) + Lunch takeout (Jun 20)."""
        result = get_recent_transactions(DEMO_USER_ID, date_from="2026-06-18")
        assert len(result) == 2
        descriptions = {tx["description"] for tx in result}
        assert "Miscellaneous" in descriptions
        assert "Lunch takeout" in descriptions

    def test_only_date_to_filters_upper_bound(self, test_db):
        """date_to=2026-06-03 yields Grocery run (Jun 01) + Bus pass top-up (Jun 03)."""
        result = get_recent_transactions(DEMO_USER_ID, date_to="2026-06-03")
        assert len(result) == 2
        descriptions = {tx["description"] for tx in result}
        assert "Grocery run" in descriptions
        assert "Bus pass top-up" in descriptions


# ===========================================================================
# Unit tests — get_category_breakdown
# ===========================================================================

class TestGetCategoryBreakdown:

    def test_no_filter_returns_all_seven_categories(self, test_db):
        result = get_category_breakdown(DEMO_USER_ID)
        assert len(result) == 7, (
            "7 distinct categories exist in the seed data"
        )

    def test_no_filter_bills_is_first_by_spend(self, test_db):
        result = get_category_breakdown(DEMO_USER_ID)
        assert result[0]["name"] == "Bills", (
            "Bills (₹120.00) is the highest-spending category and must appear first"
        )

    def test_no_filter_percentages_sum_to_100(self, test_db):
        result = get_category_breakdown(DEMO_USER_ID)
        total_pct = sum(item["pct"] for item in result)
        assert total_pct == 100, (
            "Category percentages must sum to exactly 100"
        )

    def test_no_filter_each_item_has_name_amount_pct(self, test_db):
        result = get_category_breakdown(DEMO_USER_ID)
        for item in result:
            assert "name" in item
            assert "amount" in item
            assert "pct" in item

    def test_no_filter_pct_is_integer(self, test_db):
        result = get_category_breakdown(DEMO_USER_ID)
        for item in result:
            assert isinstance(item["pct"], int), (
                f"pct must be an integer, got {type(item['pct'])} for {item['name']}"
            )

    def test_no_filter_amounts_are_rupee_prefixed(self, test_db):
        result = get_category_breakdown(DEMO_USER_ID)
        for item in result:
            assert item["amount"].startswith("₹"), (
                f"Category amount must be INR-prefixed; got '{item['amount']}'"
            )

    def test_jun01_to_jun10_returns_five_categories(self, test_db):
        result = get_category_breakdown(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-10",
        )
        assert len(result) == 5, (
            "5 distinct categories appear in the Jun 01-10 date range"
        )

    def test_jun01_to_jun10_contains_correct_category_names(self, test_db):
        result = get_category_breakdown(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-10",
        )
        names = {item["name"] for item in result}
        assert names == {"Bills", "Food", "Transport", "Health", "Entertainment"}, (
            "Only the 5 in-range categories must appear in the breakdown"
        )

    def test_jun01_to_jun10_excludes_out_of_range_categories(self, test_db):
        result = get_category_breakdown(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-10",
        )
        names = {item["name"] for item in result}
        assert "Shopping" not in names, (
            "Shopping (Jun 14) must not appear in Jun 01-10 breakdown"
        )
        assert "Other" not in names, (
            "Other (Jun 18) must not appear in Jun 01-10 breakdown"
        )

    def test_filtered_percentages_sum_to_100(self, test_db):
        """After applying a date filter the remaining percentages must still sum to 100."""
        result = get_category_breakdown(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-10",
        )
        assert sum(item["pct"] for item in result) == 100, (
            "Filtered category percentages must still sum to exactly 100"
        )

    def test_single_category_in_range_gets_100_percent(self, test_db):
        """A single-day range with one category must show pct == 100."""
        result = get_category_breakdown(
            DEMO_USER_ID,
            date_from="2026-06-05",
            date_to="2026-06-05",
        )
        assert len(result) == 1
        assert result[0]["name"] == "Bills"
        assert result[0]["amount"] == "₹120.00"
        assert result[0]["pct"] == 100, (
            "A single category must receive 100% share"
        )

    def test_empty_date_range_returns_empty_list(self, test_db):
        result = get_category_breakdown(
            DEMO_USER_ID,
            date_from="2026-07-01",
            date_to="2026-07-31",
        )
        assert result == [], (
            "A date range with no matching expenses must return an empty list"
        )

    def test_only_date_from_returns_correct_categories(self, test_db):
        """date_from=2026-06-14 yields Shopping, Other, and Food (second Food entry)."""
        result = get_category_breakdown(DEMO_USER_ID, date_from="2026-06-14")
        names = {item["name"] for item in result}
        assert "Shopping" in names
        assert "Other" in names
        assert "Food" in names
        assert "Bills" not in names, (
            "Bills (Jun 05) must be excluded when date_from is Jun 14"
        )
        assert "Health" not in names, (
            "Health (Jun 08) must be excluded when date_from is Jun 14"
        )

    def test_only_date_to_returns_correct_categories(self, test_db):
        """date_to=2026-06-03 yields Food (Jun 01) and Transport (Jun 03) only."""
        result = get_category_breakdown(DEMO_USER_ID, date_to="2026-06-03")
        names = {item["name"] for item in result}
        assert "Food" in names
        assert "Transport" in names
        assert "Bills" not in names, (
            "Bills (Jun 05) must be excluded when date_to is Jun 03"
        )
        assert "Shopping" not in names, (
            "Shopping (Jun 14) must be excluded when date_to is Jun 03"
        )
