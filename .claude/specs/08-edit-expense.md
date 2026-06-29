# Spec: Edit Expense

## Overview
Step 8 lets logged-in users correct or update an existing expense. A user
clicks an Edit link in the Transaction History table on their profile page,
lands on a pre-filled form at `/expenses/<id>/edit`, makes changes, and
submits. The app validates the updated values using the same rules as Add
Expense, writes the change to the database, and redirects back to the profile
page. Ownership is enforced: a user can only edit their own expenses — attempts
to access another user's expense return a 403. This step replaces the current
stub that returns a plain string.

## Depends on
- Step 1: Database setup (`expenses` table exists)
- Step 3: Login / Logout (`session["user_id"]` available)
- Step 5: Backend routes for profile page (profile page renders the transaction list)
- Step 7: Add Expense (`_validate_expense_form()` helper and `EXPENSE_CATEGORIES` constant are in `app.py`)

## Routes
- `GET /expenses/<int:id>/edit` — render edit form pre-filled with the expense's current values — logged-in only
- `POST /expenses/<int:id>/edit` — validate updated values, write to DB, redirect to profile — logged-in only

## Database changes
No new tables or columns. Two new helpers are needed in `database/db.py`:

- `get_expense_by_id(expense_id)` — fetches a single row from `expenses` by
  primary key; returns `None` if not found.
- `update_expense(expense_id, amount, category, date, description)` — updates
  `amount`, `category`, `date`, and `description` for the given row using a
  parameterised `UPDATE` query and commits.

`database/queries.py` must also be updated:

- `get_recent_transactions()` — add `id` to the `SELECT` list and include it
  in each result dict so the profile template can build edit links.

## Templates
- **Create:** `templates/edit_expense.html`
  - Extends `base.html`
  - Contains a single `<form method="POST" action="{{ url_for('edit_expense', id=expense.id) }}">`
  - Fields (identical to add_expense.html, pre-filled with current values):
    - Amount (`<input type="number" step="0.01" min="0.01" name="amount">`) — required
    - Category (`<select name="category">`) — required; options: Food, Transport,
      Bills, Health, Entertainment, Shopping, Other; selected option matches current value
    - Date (`<input type="date" name="date">`) — required; pre-filled with existing date
    - Description (`<input type="text" name="description">`) — optional
  - Shows an inline error message (passed as `error`) when validation fails;
    form retains the values the user just entered (not the original DB values)
  - A "Save Changes" submit button and a "Cancel" link back to `/profile`

- **Modify:** `templates/profile.html`
  - Add an "Actions" `<th>` column header to the transaction table
  - In the `{% for tx in transactions %}` loop, add a `<td>` with an Edit link:
    `<a href="{{ url_for('edit_expense', id=tx.id) }}" class="tx-edit-link">Edit</a>`

## Files to change
- `app.py`
  - Change `edit_expense(id)` to accept `methods=["GET", "POST"]`
  - Import `get_expense_by_id`, `update_expense` from `database.db`
  - Auth guard: if `session.get("user_id")` is falsy, redirect to login
  - Fetch the expense with `get_expense_by_id(id)`; if `None`, `abort(404)`
  - Ownership check: if `expense["user_id"] != session["user_id"]`, `abort(403)`
  - On GET: render `edit_expense.html` with the expense data and categories list
  - On POST:
    1. Read `amount`, `category`, `date`, `description` from `request.form`
    2. Validate with `_validate_expense_form()` — re-render form with error on failure
    3. Call `update_expense(id, amount, category, date, description)`
    4. Redirect to `url_for("profile")`

- `database/db.py`
  - Add `get_expense_by_id(expense_id)` helper
  - Add `update_expense(expense_id, amount, category, date, description)` helper

- `database/queries.py`
  - In `get_recent_transactions()`, add `id` to the `SELECT` clause and include
    `"id": r["id"]` in the result dict

- `templates/profile.html`
  - Add "Actions" column header and Edit link cell to the transaction table

## Files to create
- `templates/edit_expense.html` — edit form, pre-filled
- `static/css/edit_expense.css` — page-specific styles (reuse patterns from `add_expense.css`)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never f-strings or `.format()` in SQL
- Passwords not involved; werkzeug not needed here
- Use CSS variables — never hardcode hex values in `edit_expense.css`
- All templates extend `base.html`
- No inline `<style>` tags — all styles go in `static/css/edit_expense.css`
- Ownership must be enforced server-side — `abort(403)` if `expense["user_id"] != session["user_id"]`
- Reuse `_validate_expense_form()` from `app.py` — do not duplicate validation logic
- Amount must use ₹ symbol next to the label — never $ or £
- After a successful POST always redirect (POST/Redirect/GET) — never render the template on success
- On validation failure, show the values the user just typed (not the original DB values)

## Definition of done
- [ ] `GET /expenses/<id>/edit` redirects to `/login` when the user is not logged in
- [ ] `GET /expenses/<id>/edit` returns 404 for a non-existent expense id
- [ ] `GET /expenses/<id>/edit` returns 403 when the expense belongs to a different user
- [ ] `GET /expenses/<id>/edit` renders the form with all four fields pre-filled with the current expense values
- [ ] Submitting with all valid fields updates the row in the database and redirects to `/profile`
- [ ] The updated values appear in the Transaction History table on `/profile` after redirect
- [ ] Submitting with a blank amount shows an inline error and does not update the row
- [ ] Submitting with amount = 0 or a negative number shows an inline error
- [ ] Submitting with an invalid date shows an inline error
- [ ] Submitting with an invalid category shows an inline error
- [ ] The form retains the user's just-entered values (not original DB values) when validation fails
- [ ] The "Cancel" link returns to `/profile` without modifying any data
- [ ] Each row in the Transaction History table on `/profile` has a working Edit link
