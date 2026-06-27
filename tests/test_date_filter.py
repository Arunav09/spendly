"""
tests/test_date_filter.py

Pytest tests for the Spendly date-filter feature (Step 06).

Covers:
  - Unit tests for get_summary_stats, get_recent_transactions,
    get_category_breakdown with date_from / date_to combinations.
  - Route tests for GET /profile with ?from=&to= query params,
    auth guard, invalid-param resilience, and partial (one-sided) filters.

Fixtures `test_db` and `client` are inherited from tests/conftest.py.
`test_db` monkeypatches DB_PATH to a per-test temp file, calls init_db()
and seed_db(), and returns the path. `client` consumes `test_db` so every
test gets an isolated SQLite DB pre-loaded with the 8 seed expenses.
"""

import pytest

from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)

# ---------------------------------------------------------------------------
# Seed-data constants
# ---------------------------------------------------------------------------
# seed_db() inserts the demo user first; their id is always 1.
DEMO_USER_ID = 1

# All 8 seed expense descriptions grouped by expected filter membership.
# Used in route tests to assert presence / absence in rendered HTML.
IN_RANGE_JUN01_10 = [
    "Grocery run",             # 2026-06-01
    "Bus pass top-up",         # 2026-06-03
    "Electricity bill",        # 2026-06-05
    "Pharmacy",                # 2026-06-08
    "Streaming subscription",  # 2026-06-10
]
OUT_OF_RANGE_JUN01_10 = [
    "New headphones",  # 2026-06-14
    "Miscellaneous",   # 2026-06-18
    "Lunch takeout",   # 2026-06-20
]
ALL_DESCRIPTIONS = IN_RANGE_JUN01_10 + OUT_OF_RANGE_JUN01_10

# Pre-computed totals (verified by hand from seed data).
#   All 8:     42.50+18.00+120.00+35.00+15.99+89.95+25.00+11.50 = 357.94
#   Jun01-10:  42.50+18.00+120.00+35.00+15.99                   = 231.49
#   Jun14+:    89.95+25.00+11.50                                 = 126.45
#   To Jun05:  42.50+18.00+120.00                               = 180.50
TOTAL_ALL         = "₹357.94"
TOTAL_JUN01_10    = "₹231.49"
TOTAL_AFTER_JUN14 = "₹126.45"
TOTAL_UPTO_JUN05  = "₹180.50"


# ===========================================================================
# Unit tests — get_summary_stats
# ===========================================================================

class TestGetSummaryStats:

    def test_no_filter_returns_all_expenses(self, test_db):
        result = get_summary_stats(DEMO_USER_ID)
        assert result["total_spent"] == TOTAL_ALL, "All-time total must be ₹357.94"
        assert result["transaction_count"] == 8, "8 seed expenses must be counted"
        assert result["top_category"] == "Bills", "Bills (₹120.00) is the largest category"

    def test_date_range_jun01_to_jun10_five_expenses(self, test_db):
        result = get_summary_stats(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-10",
        )
        assert result["transaction_count"] == 5, "Exactly 5 expenses fall in Jun 01-10"
        assert result["total_spent"] == TOTAL_JUN01_10, "Total for Jun 01-10 is ₹231.49"
        assert result["top_category"] == "Bills", "Bills (₹120.00) is top in that range"

    def test_date_range_start_boundary_is_inclusive(self, test_db):
        """An expense exactly on date_from must be included."""
        result = get_summary_stats(
            DEMO_USER_ID,
            date_from="2026-06-20",
            date_to="2026-06-20",
        )
        assert result["transaction_count"] == 1, "Jun 20 has exactly one expense"
        assert result["total_spent"] == "₹11.50"

    def test_date_range_end_boundary_is_inclusive(self, test_db):
        """An expense exactly on date_to must be included."""
        result = get_summary_stats(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-01",
        )
        assert result["transaction_count"] == 1, "Jun 01 has exactly one expense"
        assert result["total_spent"] == "₹42.50"

    def test_empty_range_returns_zero_state_dict(self, test_db):
        result = get_summary_stats(
            DEMO_USER_ID,
            date_from="2026-07-01",
            date_to="2026-07-31",
        )
        assert result == {
            "total_spent": "₹0.00",
            "transaction_count": 0,
            "top_category": "—",
        }, "Empty range must return the zero-state sentinel dict"

    def test_only_date_from_filters_lower_bound(self, test_db):
        """date_from without date_to: expenses on/after Jun 14 (3 expenses)."""
        result = get_summary_stats(DEMO_USER_ID, date_from="2026-06-14")
        assert result["transaction_count"] == 3
        assert result["total_spent"] == TOTAL_AFTER_JUN14
        assert result["top_category"] == "Shopping", "Shopping (₹89.95) is largest after Jun 14"

    def test_only_date_to_filters_upper_bound(self, test_db):
        """date_to without date_from: expenses on/before Jun 05 (3 expenses)."""
        result = get_summary_stats(DEMO_USER_ID, date_to="2026-06-05")
        assert result["transaction_count"] == 3
        assert result["total_spent"] == TOTAL_UPTO_JUN05
        assert result["top_category"] == "Bills", "Bills (₹120.00) is largest up to Jun 05"

    def test_single_day_range(self, test_db):
        """date_from == date_to should return only that day's single expense."""
        result = get_summary_stats(
            DEMO_USER_ID,
            date_from="2026-06-05",
            date_to="2026-06-05",
        )
        assert result["transaction_count"] == 1
        assert result["total_spent"] == "₹120.00"
        assert result["top_category"] == "Bills"


# ===========================================================================
# Unit tests — get_recent_transactions
# ===========================================================================

class TestGetRecentTransactions:

    def test_no_filter_returns_all_eight_expenses(self, test_db):
        result = get_recent_transactions(DEMO_USER_ID)
        assert len(result) == 8, "All 8 seed expenses must be returned without a filter"

    def test_no_filter_order_is_newest_first(self, test_db):
        result = get_recent_transactions(DEMO_USER_ID)
        assert result[0]["date"] == "20 Jun 2026", "Newest expense (Jun 20) must be first"
        assert result[0]["description"] == "Lunch takeout"
        assert result[-1]["date"] == "01 Jun 2026", "Oldest expense (Jun 01) must be last"
        assert result[-1]["description"] == "Grocery run"

    def test_each_transaction_has_required_fields_and_rupee_prefix(self, test_db):
        result = get_recent_transactions(DEMO_USER_ID)
        for tx in result:
            assert "date" in tx, "Each transaction must have a 'date' key"
            assert "description" in tx, "Each transaction must have a 'description' key"
            assert "category" in tx, "Each transaction must have a 'category' key"
            assert "amount" in tx, "Each transaction must have an 'amount' key"
            assert tx["amount"].startswith("₹"), "Amount must be INR-prefixed"

    def test_date_range_jun05_to_jun10_returns_three_rows(self, test_db):
        """Jun 05-10 contains Bills, Health, Entertainment (3 rows)."""
        result = get_recent_transactions(
            DEMO_USER_ID,
            date_from="2026-06-05",
            date_to="2026-06-10",
        )
        assert len(result) == 3, "3 expenses fall in Jun 05-10"

    def test_date_range_jun05_to_jun10_is_sorted_newest_first(self, test_db):
        result = get_recent_transactions(
            DEMO_USER_ID,
            date_from="2026-06-05",
            date_to="2026-06-10",
        )
        assert result[0]["date"] == "10 Jun 2026", "Entertainment (Jun 10) must be first"
        assert result[0]["category"] == "Entertainment"
        assert result[1]["date"] == "08 Jun 2026", "Health (Jun 08) must be second"
        assert result[1]["category"] == "Health"
        assert result[2]["date"] == "05 Jun 2026", "Bills (Jun 05) must be third"
        assert result[2]["category"] == "Bills"

    def test_date_from_boundary_is_inclusive(self, test_db):
        """Expense on exactly date_from must appear in results."""
        result = get_recent_transactions(
            DEMO_USER_ID,
            date_from="2026-06-20",
            date_to="2026-06-20",
        )
        assert len(result) == 1
        assert result[0]["description"] == "Lunch takeout"

    def test_date_to_boundary_is_inclusive(self, test_db):
        """Expense on exactly date_to must appear in results."""
        result = get_recent_transactions(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-01",
        )
        assert len(result) == 1
        assert result[0]["description"] == "Grocery run"

    def test_empty_range_returns_empty_list(self, test_db):
        result = get_recent_transactions(
            DEMO_USER_ID,
            date_from="2026-07-01",
            date_to="2026-07-31",
        )
        assert result == [], "No expenses in July must return empty list"

    def test_only_date_from_returns_correct_subset(self, test_db):
        """date_from=2026-06-18 yields Miscellaneous (Jun 18) + Lunch takeout (Jun 20)."""
        result = get_recent_transactions(DEMO_USER_ID, date_from="2026-06-18")
        assert len(result) == 2
        descriptions = {tx["description"] for tx in result}
        assert "Miscellaneous" in descriptions
        assert "Lunch takeout" in descriptions

    def test_only_date_to_returns_correct_subset(self, test_db):
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
        assert len(result) == 7, "7 distinct categories exist in seed data"

    def test_no_filter_bills_is_first_by_spend(self, test_db):
        result = get_category_breakdown(DEMO_USER_ID)
        assert result[0]["name"] == "Bills", "Bills (₹120.00) is the highest-spend category"

    def test_no_filter_percentages_sum_to_100(self, test_db):
        result = get_category_breakdown(DEMO_USER_ID)
        total_pct = sum(item["pct"] for item in result)
        assert total_pct == 100, "Category percentages must sum to exactly 100"

    def test_no_filter_amounts_are_rupee_formatted_and_pct_is_int(self, test_db):
        result = get_category_breakdown(DEMO_USER_ID)
        for item in result:
            assert item["amount"].startswith("₹"), "Amount must be INR-prefixed"
            assert isinstance(item["pct"], int), "pct must be an integer"

    def test_single_day_range_returns_one_category_at_100_pct(self, test_db):
        """2026-06-05 only: Bills (₹120.00) is the single entry with a 100% share."""
        result = get_category_breakdown(
            DEMO_USER_ID,
            date_from="2026-06-05",
            date_to="2026-06-05",
        )
        assert len(result) == 1
        assert result[0]["name"] == "Bills"
        assert result[0]["amount"] == "₹120.00"
        assert result[0]["pct"] == 100

    def test_date_range_jun01_to_jun10_returns_five_categories(self, test_db):
        result = get_category_breakdown(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-10",
        )
        assert len(result) == 5, "5 distinct categories in Jun 01-10"
        category_names = {item["name"] for item in result}
        assert category_names == {"Bills", "Food", "Transport", "Health", "Entertainment"}

    def test_date_range_jun01_to_jun10_excludes_later_categories(self, test_db):
        result = get_category_breakdown(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-10",
        )
        category_names = {item["name"] for item in result}
        assert "Shopping" not in category_names, "Shopping (Jun 14) must not appear"
        assert "Other" not in category_names, "Other (Jun 18) must not appear"

    def test_filtered_percentages_still_sum_to_100(self, test_db):
        """After filtering, the remaining category percentages must still sum to 100."""
        result = get_category_breakdown(
            DEMO_USER_ID,
            date_from="2026-06-01",
            date_to="2026-06-10",
        )
        assert sum(item["pct"] for item in result) == 100

    def test_empty_range_returns_empty_list(self, test_db):
        result = get_category_breakdown(
            DEMO_USER_ID,
            date_from="2026-07-01",
            date_to="2026-07-31",
        )
        assert result == [], "Empty date range must return empty list"

    def test_only_date_from_returns_correct_categories(self, test_db):
        """date_from=2026-06-14 yields Shopping, Other, Food only."""
        result = get_category_breakdown(DEMO_USER_ID, date_from="2026-06-14")
        category_names = {item["name"] for item in result}
        assert "Shopping" in category_names
        assert "Other" in category_names
        assert "Food" in category_names
        assert "Bills" not in category_names, "Bills (Jun 05) must be excluded"
        assert "Health" not in category_names, "Health (Jun 08) must be excluded"

    def test_only_date_to_returns_correct_categories(self, test_db):
        """date_to=2026-06-03 yields Food and Transport only."""
        result = get_category_breakdown(DEMO_USER_ID, date_to="2026-06-03")
        category_names = {item["name"] for item in result}
        assert "Food" in category_names
        assert "Transport" in category_names
        assert "Bills" not in category_names, "Bills (Jun 05) must be excluded"
        assert "Shopping" not in category_names, "Shopping (Jun 14) must be excluded"


# ===========================================================================
# Route tests — GET /profile with date filter query params
# ===========================================================================

class TestDateFilterRoute:
    """Integration tests for the /profile route date filter feature."""

    def _authenticate(self, client):
        """Inject the demo user's id into the session without touching the login form."""
        with client.session_transaction() as sess:
            sess["user_id"] = DEMO_USER_ID

    # ---- Auth guard --------------------------------------------------------

    def test_unauthenticated_request_redirects_to_login(self, client):
        response = client.get("/profile")
        assert response.status_code == 302, "Unauthenticated /profile must redirect"
        assert "/login" in response.headers["Location"]

    def test_unauthenticated_request_with_filter_params_also_redirects(self, client):
        response = client.get("/profile?from=2026-06-01&to=2026-06-10")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    # ---- No filter: all expenses visible -----------------------------------

    def test_no_filter_returns_200(self, client):
        self._authenticate(client)
        response = client.get("/profile")
        assert response.status_code == 200

    def test_no_filter_shows_all_time_total(self, client):
        self._authenticate(client)
        html = client.get("/profile").data.decode("utf-8")
        assert "₹357.94" in html, "Unfiltered profile must show all-time total ₹357.94"

    def test_no_filter_shows_rupee_symbol(self, client):
        self._authenticate(client)
        html = client.get("/profile").data.decode("utf-8")
        assert "₹" in html

    def test_no_filter_shows_all_transaction_descriptions(self, client):
        self._authenticate(client)
        html = client.get("/profile").data.decode("utf-8")
        for description in ALL_DESCRIPTIONS:
            assert description in html, (
                f"Unfiltered profile must contain '{description}'"
            )

    # ---- Jun 01-10 filter: 5 expenses, ₹231.49 ----------------------------

    def test_jun01_to_jun10_returns_200(self, client):
        self._authenticate(client)
        response = client.get("/profile?from=2026-06-01&to=2026-06-10")
        assert response.status_code == 200

    def test_jun01_to_jun10_shows_correct_filtered_total(self, client):
        self._authenticate(client)
        html = client.get("/profile?from=2026-06-01&to=2026-06-10").data.decode("utf-8")
        assert "₹231.49" in html, "Filtered total must be ₹231.49 for Jun 01-10"

    def test_jun01_to_jun10_shows_in_range_descriptions(self, client):
        self._authenticate(client)
        html = client.get("/profile?from=2026-06-01&to=2026-06-10").data.decode("utf-8")
        for description in IN_RANGE_JUN01_10:
            assert description in html, (
                f"In-range expense '{description}' must appear in filtered view"
            )

    def test_jun01_to_jun10_excludes_out_of_range_descriptions(self, client):
        self._authenticate(client)
        html = client.get("/profile?from=2026-06-01&to=2026-06-10").data.decode("utf-8")
        for description in OUT_OF_RANGE_JUN01_10:
            assert description not in html, (
                f"Out-of-range expense '{description}' must not appear in filtered view"
            )

    # ---- Jul 2026 filter: empty range, ₹0.00 ------------------------------

    def test_empty_range_returns_200(self, client):
        self._authenticate(client)
        response = client.get("/profile?from=2026-07-01&to=2026-07-31")
        assert response.status_code == 200

    def test_empty_range_shows_zero_total(self, client):
        self._authenticate(client)
        html = client.get("/profile?from=2026-07-01&to=2026-07-31").data.decode("utf-8")
        assert "₹0.00" in html, "Empty date range must show ₹0.00 total"

    def test_empty_range_shows_no_transaction_descriptions(self, client):
        self._authenticate(client)
        html = client.get("/profile?from=2026-07-01&to=2026-07-31").data.decode("utf-8")
        for description in ALL_DESCRIPTIONS:
            assert description not in html, (
                f"'{description}' must not appear when date range yields no expenses"
            )

    # ---- Invalid date params: silently ignored, full view shown ------------

    def test_invalid_from_param_does_not_cause_server_error(self, client):
        self._authenticate(client)
        response = client.get("/profile?from=bad&to=2026-06-30")
        assert response.status_code == 200, "Invalid ?from must not raise a 500"

    def test_invalid_from_param_shows_all_expenses(self, client):
        """When ?from is invalid both params are discarded and the view is unfiltered."""
        self._authenticate(client)
        html = client.get("/profile?from=bad&to=2026-06-30").data.decode("utf-8")
        assert "₹357.94" in html, "Invalid param must fall back to the unfiltered total"

    def test_invalid_to_param_does_not_cause_server_error(self, client):
        self._authenticate(client)
        response = client.get("/profile?from=2026-06-01&to=not-a-date")
        assert response.status_code == 200, "Invalid ?to must not raise a 500"

    def test_invalid_to_param_shows_all_expenses(self, client):
        """When ?to is invalid both params are discarded and the view is unfiltered."""
        self._authenticate(client)
        html = client.get("/profile?from=2026-06-01&to=not-a-date").data.decode("utf-8")
        assert "₹357.94" in html

    def test_both_params_invalid_returns_200_and_shows_all_expenses(self, client):
        self._authenticate(client)
        response = client.get("/profile?from=foo&to=bar")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "₹357.94" in html

    def test_empty_string_params_treated_as_no_filter(self, client):
        """Explicit ?from=&to= must be treated the same as no params at all."""
        self._authenticate(client)
        html = client.get("/profile?from=&to=").data.decode("utf-8")
        assert "₹357.94" in html, "Empty string params must not filter the view"

    def test_non_iso_date_format_is_rejected_and_shows_all_expenses(self, client):
        """Dates in DD/MM/YYYY format are not the expected format and must be ignored."""
        self._authenticate(client)
        response = client.get("/profile?from=01/06/2026&to=10/06/2026")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "₹357.94" in html

    # ---- Partial filter: only one param provided ---------------------------

    def test_only_from_param_returns_200(self, client):
        self._authenticate(client)
        response = client.get("/profile?from=2026-06-14")
        assert response.status_code == 200

    def test_only_from_param_shows_correct_filtered_total(self, client):
        """?from=2026-06-14 yields Shopping+Other+Food = ₹126.45 (3 expenses)."""
        self._authenticate(client)
        html = client.get("/profile?from=2026-06-14").data.decode("utf-8")
        assert "₹126.45" in html, "Only-from filter must show ₹126.45 for Jun 14+"

    def test_only_from_param_shows_on_or_after_expenses(self, client):
        self._authenticate(client)
        html = client.get("/profile?from=2026-06-14").data.decode("utf-8")
        assert "New headphones" in html, "Jun 14 expense must appear"
        assert "Miscellaneous" in html, "Jun 18 expense must appear"
        assert "Lunch takeout" in html, "Jun 20 expense must appear"

    def test_only_from_param_excludes_earlier_expenses(self, client):
        self._authenticate(client)
        html = client.get("/profile?from=2026-06-14").data.decode("utf-8")
        assert "Grocery run" not in html, "Jun 01 expense must be excluded"
        assert "Electricity bill" not in html, "Jun 05 expense must be excluded"

    def test_only_to_param_returns_200(self, client):
        self._authenticate(client)
        response = client.get("/profile?to=2026-06-05")
        assert response.status_code == 200

    def test_only_to_param_shows_correct_filtered_total(self, client):
        """?to=2026-06-05 yields Food+Transport+Bills = ₹180.50 (3 expenses)."""
        self._authenticate(client)
        html = client.get("/profile?to=2026-06-05").data.decode("utf-8")
        assert "₹180.50" in html, "Only-to filter must show ₹180.50 for up to Jun 05"

    def test_only_to_param_shows_on_or_before_expenses(self, client):
        self._authenticate(client)
        html = client.get("/profile?to=2026-06-05").data.decode("utf-8")
        assert "Grocery run" in html, "Jun 01 expense must appear"
        assert "Bus pass top-up" in html, "Jun 03 expense must appear"
        assert "Electricity bill" in html, "Jun 05 expense must appear"

    def test_only_to_param_excludes_later_expenses(self, client):
        self._authenticate(client)
        html = client.get("/profile?to=2026-06-05").data.decode("utf-8")
        assert "New headphones" not in html, "Jun 14 expense must be excluded"
        assert "Lunch takeout" not in html, "Jun 20 expense must be excluded"
