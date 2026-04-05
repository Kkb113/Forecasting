"""
Phase 1 authentication tests.

Each test function receives a fresh `client` fixture (function-scoped) backed
by an in-memory SQLite database, so there is no state leakage between tests.

Registration auto-logs the user in; tests that need an anonymous session call
/logout first before testing login or duplicate-email behaviour.
"""


# ── Page load ──────────────────────────────────────────────────────────────


def test_register_page_loads(client):
    rv = client.get("/register")
    assert rv.status_code == 200
    assert b"Create Account" in rv.data


def test_login_page_loads(client):
    rv = client.get("/login")
    assert rv.status_code == 200
    assert b"Sign In" in rv.data


# ── Registration ───────────────────────────────────────────────────────────


def test_successful_registration(client):
    rv = client.post(
        "/register",
        data={"email": "alice@example.com", "password": "securepass"},
        follow_redirects=True,
    )
    assert rv.status_code == 200
    assert b"Dashboard" in rv.data


def test_duplicate_email_rejected(client):
    # First registration succeeds and auto-logs in
    client.post("/register", data={"email": "bob@example.com", "password": "password1"})
    # Log out so the /register route doesn't redirect away immediately
    client.get("/logout")
    # Second attempt with same email
    rv = client.post(
        "/register",
        data={"email": "bob@example.com", "password": "password1"},
        follow_redirects=True,
    )
    assert rv.status_code == 200
    assert b"already exists" in rv.data


def test_short_password_rejected(client):
    rv = client.post(
        "/register",
        data={"email": "carol@example.com", "password": "short"},
        follow_redirects=True,
    )
    assert rv.status_code == 200
    assert b"8 characters" in rv.data


def test_missing_email_rejected(client):
    rv = client.post(
        "/register",
        data={"email": "", "password": "validpassword"},
        follow_redirects=True,
    )
    assert rv.status_code == 200
    assert b"Email is required" in rv.data


def test_missing_password_rejected(client):
    rv = client.post(
        "/register",
        data={"email": "dave@example.com", "password": ""},
        follow_redirects=True,
    )
    assert rv.status_code == 200
    assert b"Password is required" in rv.data


# ── Login ──────────────────────────────────────────────────────────────────


def test_successful_login(client):
    # Register (auto-logs in), then log out, then log back in
    client.post("/register", data={"email": "eve@example.com", "password": "mypassword"})
    client.get("/logout")
    rv = client.post(
        "/login",
        data={"email": "eve@example.com", "password": "mypassword"},
        follow_redirects=True,
    )
    assert rv.status_code == 200
    assert b"Dashboard" in rv.data


def test_wrong_password_rejected(client):
    client.post("/register", data={"email": "frank@example.com", "password": "correctpass"})
    client.get("/logout")
    rv = client.post(
        "/login",
        data={"email": "frank@example.com", "password": "wrongpass"},
        follow_redirects=True,
    )
    assert rv.status_code == 200
    assert b"Invalid email or password" in rv.data


def test_unknown_email_rejected(client):
    rv = client.post(
        "/login",
        data={"email": "nobody@example.com", "password": "somepassword"},
        follow_redirects=True,
    )
    assert rv.status_code == 200
    assert b"Invalid email or password" in rv.data


def test_missing_login_fields_rejected(client):
    rv = client.post(
        "/login",
        data={"email": "", "password": ""},
        follow_redirects=True,
    )
    assert rv.status_code == 200
    assert b"Invalid email or password" in rv.data


# ── Dashboard protection ───────────────────────────────────────────────────


def test_dashboard_redirects_unauthenticated(client):
    rv = client.get("/", follow_redirects=False)
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


# ── Logout ─────────────────────────────────────────────────────────────────


def test_logout_works(client):
    # Register so we are logged in
    client.post("/register", data={"email": "grace@example.com", "password": "password123"})
    # Logout
    rv = client.get("/logout", follow_redirects=True)
    assert rv.status_code == 200
    # Dashboard now requires login again
    rv2 = client.get("/", follow_redirects=False)
    assert rv2.status_code == 302
    assert "/login" in rv2.headers["Location"]
