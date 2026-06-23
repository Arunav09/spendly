# Spec: Login and Logout

## Overview
Implement the `POST /login` handler so existing users can authenticate with their
email and password, and implement `GET /logout` so they can end their session.
This step replaces both stubs with real logic: login verifies credentials against
the hashed password stored in the database, opens a Flask session on success, and
redirects to the landing page; logout clears the session and redirects to the login
page. The navbar in `base.html` is also updated to show a "Sign out" link when a
session is active.

## Depends on
- Step 01 — Database setup (`database/db.py` with `get_db()`, `users` table)
- Step 02 — Registration (`create_user()`, `get_user_by_email()`, `app.secret_key`,
  `session['user_id']` convention)

## Routes
- `POST /login` — verify credentials, open session, redirect to landing — public
- `GET /logout` — clear session, redirect to `/login` — public (no login guard needed)

The existing `GET /login` stub already renders `login.html`; only the POST handler
and the logout route body are added in this step.

## Database changes
No schema changes. No new helper functions needed — `get_user_by_email()` from
Step 02 is sufficient for login.

## Templates
- **Modify** `templates/login.html`: change `action="/login"` →
  `action="{{ url_for('login') }}"` to comply with the no-hardcoded-URLs rule.
- **Modify** `templates/base.html`: update the `nav-links` section to show a
  "Sign out" link (pointing to `url_for('logout')`) when `session['user_id']` is
  set, and the existing "Sign in" / "Get started" links when it is not.

## Files to change
- `app.py` — add `check_password_hash` to the `werkzeug.security` import, convert
  `GET /login` stub to a `GET, POST` route with a POST handler, replace the
  `GET /logout` stub body with session-clearing logic
- `templates/login.html` — fix hardcoded form action URL
- `templates/base.html` — make navbar session-aware

## Files to create
None.

## New dependencies
No new pip packages. `werkzeug.security.check_password_hash` is part of the
already-installed `werkzeug` package.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only
- Parameterised queries only (`?` placeholders) — never f-strings in SQL
- Verify the submitted password with `werkzeug.security.check_password_hash`
  against the `password_hash` column — never compare plaintext
- On failed login (wrong email or wrong password) render the form again with a
  generic `error="Invalid email or password."` — do not reveal which field was wrong
- On successful login: set `session['user_id'] = user['id']` then redirect to
  `url_for('landing')`
- `GET /logout` must call `session.clear()` (not `session.pop`) then redirect to
  `url_for('login')`
- Use CSS variables — never hardcode hex values in any new or modified styles
- All templates extend `base.html`
- Use `url_for()` for every internal link — never hardcode URLs

## Definition of done
- [ ] Submitting a valid email and correct password sets `session['user_id']` and
      redirects to the landing page
- [ ] Submitting an unrecognised email re-renders the login form with the error
      "Invalid email or password." and does not set a session
- [ ] Submitting a recognised email with the wrong password re-renders the login
      form with the same generic error and does not set a session
- [ ] Visiting `/logout` clears the session and redirects to `/login`
- [ ] After logout, visiting `/logout` again also redirects to `/login` without error
- [ ] The login form `action` attribute uses `url_for('login')`, not a hardcoded URL
- [ ] The navbar shows "Sign out" when a session is active and "Sign in" / "Get
      started" when it is not
- [ ] `GET /login` still works (renders the empty form with no error)
