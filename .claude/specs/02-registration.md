# Spec: Registration

## Overview
Implement the `POST /register` handler so users can create a Spendly account.
The form already exists in `register.html`; this step wires it to the database,
hashes the submitted password, opens a Flask session for the new user, and
redirects to the landing page. It also introduces `app.secret_key` (required
for sessions) and two new DB helpers: `create_user()` and `get_user_by_email()`.

## Depends on
- Step 01 — Database setup (`database/db.py` with `get_db()`, `init_db()`, `users` table)

## Routes
- `POST /register` — process registration form — public

The existing `GET /register` route is already implemented; only the POST handler
is added in this step.

## Database changes
No schema changes — the `users` table from Step 01 covers all required columns.

Two new helper functions must be added to `database/db.py`:

- `create_user(name, email, password_hash)` — inserts a row into `users`,
  commits, closes connection, returns nothing.
- `get_user_by_email(email)` — queries `users` by email, returns the row as
  `sqlite3.Row` (or `None` if not found), closes connection.

## Templates
- **Modify** `templates/register.html`: change `action="/register"` →
  `action="{{ url_for('register') }}"` to comply with the no-hardcoded-URLs rule.

## Files to change
- `app.py` — add `secret_key`, update imports, add `POST /register` route
- `database/db.py` — add `create_user()` and `get_user_by_email()`
- `templates/register.html` — fix hardcoded form action URL

## Files to create
None.

## New dependencies
No new pip packages. `werkzeug.security` is already installed.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only
- Parameterised queries only (`?` placeholders) — never f-strings in SQL
- Hash the password with `werkzeug.security.generate_password_hash` before
  passing it to `create_user()`; never store plaintext
- `app.secret_key` must be set before any route uses `session`; use a fixed
  development string (e.g. `"dev-secret-change-in-prod"`) — do not read from
  env in this step
- Validate all three fields (name, email, password) are non-empty; return the
  form with an `error=` message if any are blank
- Check minimum password length of 8 characters server-side; return form with
  `error=` if too short
- Call `get_user_by_email()` before inserting; if a row is returned, render the
  form again with `error="An account with that email already exists."`
- On success: call `create_user()`, fetch the new user with
  `get_user_by_email()`, set `session['user_id']`, redirect to `url_for('landing')`
- Use `abort(400)` only for truly malformed requests; prefer re-rendering the
  form with an `error=` variable for expected validation failures
- Use CSS variables — never hardcode hex values in any new styles
- All templates must extend `base.html`

## Definition of done
- [ ] Submitting valid name / email / password creates a row in `users` with a
      hashed (not plaintext) `password_hash`
- [ ] After successful registration, `session['user_id']` is set and the browser
      is redirected to the landing page
- [ ] Submitting a duplicate email re-renders the form with a visible error
      message and does not create a second row
- [ ] Submitting with any blank field re-renders the form with a visible error
      message
- [ ] Submitting a password shorter than 8 characters re-renders the form with a
      visible error message
- [ ] The form `action` attribute uses `url_for('register')`, not a hardcoded URL
- [ ] `app.secret_key` is set and the app starts without errors
- [ ] `GET /register` still works (renders the empty form)
