# Spec: Add Expense

## Overview
Step 7 gives logged-in users the ability to record a new expense through a
dedicated form page at `/expenses/add`. The user fills in an amount (in ₹),
selects a category, picks a date, and optionally adds a description. On valid
submission the expense is inserted into the `expenses` table and the user is
redirected to their profile page where the new transaction immediately appears.
This is the first write path for expense data and replaces the current stub
that returns a plain string.

## Depends on
- Step 1: Database setup (`expenses` table exists with `user_id`, `amount`,
  `category`, `date`, `description` columns)
- Step 3: Login / Logout (`session["user_id"]` is set on login; unauthenticated
  users must be redirected to `/login`)
- Step 5: Backend routes for profile page (profile page exists and will show
  the newly added expense after redirect)

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in only
- `POST /expenses/add` — validate and insert the expense, redirect to profile — logged-in only

## Database changes
No new tables or columns. The `expenses` table already has all required columns.

A new DB helper must be added to `database/db.py`:
- `insert_expense(user_id, amount, category, date, description)` — inserts one
  row into `expenses` using a parameterised query and commits.

## Templates
- **Create:** `templates/add_expense.html`
  - Extends `base.html`
  - Contains a single `<form method="POST" action="{{ url_for('add_expense') }}">`
  - Fields:
    - Amount (`<input type="number" step="0.01" min="0.01" name="amount">`) — required
    - Category (`<select name="category">`) — required; options: Food, Transport,
      Bills, Health, Entertainment, Shopping, Other
    - Date (`<input type="date" name="date">`) — required; defaults to today
    - Description (`<input type="text" name="description">`) — optional
  - Shows an inline error message (passed as `error` from the route) when
    validation fails; the form retains previously entered values
  - A "Save Expense" submit button and a "Cancel" link back to `/profile`

## Files to change
- `app.py`
  - Change `add_expense()` route to accept `methods=["GET", "POST"]`
  - Import `insert_expense` from `database.db`
  - On GET: render `add_expense.html` with today's date pre-filled
  - On POST:
    1. Read `amount`, `category`, `date`, `description` from `request.form`
    2. Validate: amount is a positive number, category is one of the seven
       allowed values, date is a valid `YYYY-MM-DD` string — re-render the
       form with an error message if any check fails
    3. Call `insert_expense(user_id, amount, category, date, description)`
    4. Redirect to `url_for("profile")`
  - Guard the route: if `session.get("user_id")` is falsy, redirect to login

- `database/db.py`
  - Add `insert_expense(user_id, amount, category, date, description)` helper
    using a parameterised `INSERT INTO expenses ...` query

## Files to create
- `templates/add_expense.html` — the add-expense form page
- `static/css/add_expense.css` — page-specific styles for the form

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never f-strings or `.format()` in SQL
- No passwords involved; werkzeug not needed here
- Use CSS variables — never hardcode hex values in `add_expense.css`
- All templates extend `base.html`
- No inline `<style>` tags — all styles go in `static/css/add_expense.css`
- Vanilla JS only — JS may be used to default the date input to today's date,
  but the form must work without JS (use `value="{{ today }}"` from the route)
- Allowed categories are exactly: Food, Transport, Bills, Health, Entertainment,
  Shopping, Other — reject anything else server-side
- Amount must be a positive float; reject zero or negative values
- Currency symbol ₹ must appear next to the amount field label — never $ or £
- After a successful POST always redirect (POST/Redirect/GET pattern) — never
  render the template directly on success
- `abort(401)` if a non-logged-in user reaches either GET or POST (or redirect
  to login — be consistent with the rest of the app which uses redirect)

## Definition of done
- [ ] `GET /expenses/add` redirects to `/login` when the user is not logged in
- [ ] `GET /expenses/add` renders the form with today's date pre-filled when logged in
- [ ] Submitting the form with all valid fields inserts one row into `expenses`
      and redirects to `/profile`
- [ ] The new expense appears in the transaction list on `/profile` immediately
      after redirect
- [ ] Submitting with a blank amount shows an inline error and does not insert a row
- [ ] Submitting with amount = 0 or a negative number shows an inline error
- [ ] Submitting with an invalid or missing date shows an inline error
- [ ] Submitting with a category not in the allowed list shows an inline error
- [ ] The form retains the user's previously entered values when validation fails
- [ ] Description is optional — submitting without it succeeds
- [ ] Amount is stored and displayed with ₹ symbol (e.g. ₹42.50)
- [ ] The "Cancel" link returns to `/profile` without inserting any data
