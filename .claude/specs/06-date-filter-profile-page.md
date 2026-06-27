# Spec: Date Filter for Profile Page

## Overview
Step 6 adds a date-range filter to the profile page so users can narrow the
transaction history, summary stats, and category breakdown to a chosen period.
The filter exposes four preset quick-select options (All Time, This Month, Last
Month, This Week) plus two date inputs for a fully custom range. Selecting any
option re-requests `GET /profile` with `?from=YYYY-MM-DD&to=YYYY-MM-DD` query
parameters; the route reads those bounds, passes them to the query helpers, and
re-renders the same template with filtered data. This builds directly on the
live DB wiring from Step 5 without touching the auth or expense-CRUD layers.

## Depends on
- Step 1: Database setup (`expenses` table with a `date TEXT` column exists)
- Step 3: Login / Logout (`session["user_id"]` is set on login)
- Step 5: Backend routes for profile page (all three query helpers exist in
  `database/queries.py` and are wired to the `/profile` route)

## Routes
No new routes. The existing `GET /profile` route is modified to read optional
`from` and `to` query-string parameters.

- `GET /profile?from=YYYY-MM-DD&to=YYYY-MM-DD` — filtered view — logged-in only
- `GET /profile` (no params) — unchanged behaviour, shows all expenses

## Database changes
No database changes. The `expenses.date` column (`TEXT`, stored as `YYYY-MM-DD`)
already supports range filtering via SQL `BETWEEN`.

## Templates
- **Modify**: `templates/profile.html`
  - Add a date-filter bar above the Transaction History section.
  - The bar contains four preset buttons (All Time, This Week, This Month,
    Last Month) and two `<input type="date">` fields (From / To) inside a
    `<form method="GET" action="{{ url_for('profile') }}">`.
  - The currently active preset button receives an `active` CSS class so it
    is visually highlighted.
  - Submitting the form re-requests `/profile` with `from` and `to` params.
  - The From and To inputs must be pre-populated with the current filter values
    so the user can see what range is active.

## Files to change
- `app.py`
  - In the `profile()` view: read `request.args.get("from")` and
    `request.args.get("to")`, validate that both are valid `YYYY-MM-DD` strings
    (or absent), then pass them as `date_from` / `date_to` to the three query
    helpers.
  - Pass `date_from` and `date_to` back to the template so the filter UI can
    reflect the active range.
- `database/queries.py`
  - Add optional `date_from=None` and `date_to=None` keyword arguments to
    `get_summary_stats`, `get_recent_transactions`, and `get_category_breakdown`.
  - When both are provided, append `AND date BETWEEN ? AND ?` to each query's
    WHERE clause. When absent, queries behave exactly as before.
- `templates/profile.html`
  - Add the date-filter bar (see Templates section above).
- `static/css/profile.css`
  - Add styles for `.date-filter-bar`, `.preset-btn`, `.preset-btn.active`,
    `.date-range-inputs`. Use CSS variables only — no hardcoded hex values.

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline `<style>` tags — all styles go in `profile.css`
- Vanilla JS only — the preset buttons set the hidden `from`/`to` inputs and
  submit the form; no external libraries
- Date validation in the route: if either param is present but not a valid
  `YYYY-MM-DD` string, ignore both and treat as no filter (do not abort or
  raise an error)
- The `date_from` / `date_to` bounds are inclusive on both ends
  (`BETWEEN date_from AND date_to`)
- Summary stats, transaction list, and category breakdown must all respect the
  same active date range — no section should show unfiltered data when a range
  is active
- The filter UI must degrade gracefully when JS is disabled: the date inputs
  and a submit button must work without JS; the preset buttons are a JS
  enhancement only
- Currency must always display as ₹ — never £ or $

## Definition of done
- [ ] Visiting `/profile` with no query params shows all expenses (same as Step 5)
- [ ] Visiting `/profile?from=2026-06-01&to=2026-06-10` shows only the 3 seed
      expenses dated 01 Jun–10 Jun; total spent, transaction count, and category
      breakdown reflect only those 3 expenses
- [ ] Clicking "This Month" preset re-requests the page with the correct `from`
      and `to` values for the current calendar month
- [ ] Clicking "Last Month" preset re-requests the page with the correct `from`
      and `to` values for the previous calendar month
- [ ] Clicking "This Week" preset re-requests the page with the correct `from`
      and `to` values for the current Mon–Sun week
- [ ] Clicking "All Time" clears the filter and shows all expenses
- [ ] The active preset button is visually distinguished from inactive ones
- [ ] The From and To date inputs display the currently active range
- [ ] Submitting a custom date range via the date inputs filters all three
      sections correctly
- [ ] An invalid or missing date param (`?from=bad`) is silently ignored and
      the page renders all expenses without a 500 error
- [ ] A user with no expenses in the selected range sees ₹0.00 total, 0
      transactions, and an empty category breakdown — no errors
