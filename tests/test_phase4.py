"""
Phase 4 tests — dashboard stats, history page, and API historical data.

Each test gets a fresh in-memory SQLite DB and an isolated temp upload
directory via the function-scoped fixtures in conftest.py.
"""

from datetime import date
from io import BytesIO

import openpyxl
import pytest

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ── Helpers ────────────────────────────────────────────────────────────────

def make_ts_excel(n=12):
    """Return BytesIO with a monthly time-series: columns [period, revenue]."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["period", "revenue"])
    for i in range(n):
        year = 2023 + (i // 12)
        month = (i % 12) + 1
        ws.append([date(year, month, 1).strftime("%Y-%m-%d"), float(1000 + i * 50)])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def register_and_login(client, email="user@example.com", password="password123"):
    client.post("/register", data={"email": email, "password": password})


def do_upload(client, buf=None, filename="data.xlsx"):
    if buf is None:
        buf = make_ts_excel()
    return client.post(
        "/upload",
        data={"file": (buf, filename, XLSX_MIME)},
        content_type="multipart/form-data",
        follow_redirects=False,
    )


def get_first_upload_id(app):
    with app.app_context():
        from app.models.upload import FileUpload
        rec = FileUpload.query.first()
        return rec.id if rec else None


def do_run(client, upload_id, horizon=3):
    return client.post(
        "/forecast/run",
        data={
            "upload_id": upload_id,
            "date_column": "period",
            "value_column": "revenue",
            "horizon": horizon,
        },
        follow_redirects=False,
    )


def get_first_run_id(app):
    with app.app_context():
        from app.models.forecast import ForecastRun
        run = ForecastRun.query.first()
        return run.id if run else None


# ── History page ───────────────────────────────────────────────────────────

def test_history_requires_login(client):
    resp = client.get("/history", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_history_empty_state(client):
    register_and_login(client)
    resp = client.get("/history")
    assert resp.status_code == 200
    assert b"No forecast runs yet" in resp.data


def test_history_shows_own_runs(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id)

    resp = client.get("/history")
    assert resp.status_code == 200
    assert b"data.xlsx" in resp.data
    assert b"period" in resp.data
    assert b"revenue" in resp.data


def test_history_excludes_other_users_runs(client, app):
    """User A's runs must not appear when User B views /history."""
    # User A uploads and runs
    register_and_login(client, email="a@example.com")
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id)

    # Log out User A, register + login User B
    client.get("/logout")
    register_and_login(client, email="b@example.com")

    resp = client.get("/history")
    assert resp.status_code == 200
    # User B has no runs — should see empty state
    assert b"No forecast runs yet" in resp.data


def test_history_lists_multiple_runs(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id, horizon=2)
    do_run(client, upload_id, horizon=4)

    resp = client.get("/history")
    assert resp.status_code == 200
    # Both runs for this file should appear
    assert resp.data.count(b"data.xlsx") >= 2


# ── Dashboard stats ────────────────────────────────────────────────────────

def test_dashboard_requires_login(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_dashboard_shows_upload_count(client, app):
    register_and_login(client)
    resp = client.get("/")
    assert resp.status_code == 200
    # Initially 0 uploads
    assert b"0" in resp.data

    do_upload(client)
    resp = client.get("/")
    assert b"1" in resp.data


def test_dashboard_shows_run_count(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id)

    resp = client.get("/")
    assert resp.status_code == 200
    assert b"1" in resp.data


def test_dashboard_scoped_to_current_user(client, app):
    """User A's upload/run counts must not bleed into User B's dashboard."""
    # User A: 1 upload, 1 run
    register_and_login(client, email="a@example.com")
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id)

    # Switch to User B
    client.get("/logout")
    register_and_login(client, email="b@example.com")

    resp = client.get("/")
    assert resp.status_code == 200
    # User B should see 0 uploads and 0 runs — "0" appears in stat cards
    assert b"0" in resp.data


def test_dashboard_shows_recent_uploads(client, app):
    register_and_login(client)
    do_upload(client, filename="sales.xlsx")

    resp = client.get("/")
    assert resp.status_code == 200
    assert b"sales.xlsx" in resp.data


def test_dashboard_shows_recent_forecasts(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id)

    resp = client.get("/")
    assert resp.status_code == 200
    assert b"data.xlsx" in resp.data


# ── API historical data ────────────────────────────────────────────────────

def test_api_includes_historical_key(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id)
    run_id = get_first_run_id(app)

    resp = client.get(f"/api/forecast/{run_id}/data")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "historical" in data


def test_api_historical_has_correct_structure(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id, horizon=3)
    run_id = get_first_run_id(app)

    resp = client.get(f"/api/forecast/{run_id}/data")
    data = resp.get_json()
    historical = data["historical"]

    assert isinstance(historical, list)
    assert len(historical) > 0
    # Each entry must have label and value keys
    for entry in historical:
        assert "label" in entry
        assert "value" in entry
        assert isinstance(entry["value"], (int, float))


def test_api_historical_has_12_rows(client, app):
    """make_ts_excel() produces 12 rows — all should appear in historical."""
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id, horizon=3)
    run_id = get_first_run_id(app)

    resp = client.get(f"/api/forecast/{run_id}/data")
    data = resp.get_json()
    assert len(data["historical"]) == 12


def test_api_historical_empty_when_file_missing(client, app):
    """If the file is deleted after the run, historical returns [] gracefully."""
    import os

    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id, horizon=2)
    run_id = get_first_run_id(app)

    # Delete the stored file
    with app.app_context():
        from app.extensions import db
        from app.models.upload import FileUpload
        upload = db.session.get(FileUpload, upload_id)
        if upload and os.path.exists(upload.upload_path):
            os.remove(upload.upload_path)

    resp = client.get(f"/api/forecast/{run_id}/data")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["historical"] == []


def test_api_historical_requires_login(client, app):
    resp = client.get("/api/forecast/1/data", follow_redirects=False)
    assert resp.status_code in (302, 401, 403)


def test_api_cross_user_historical_forbidden(client, app):
    """User B must not access User A's run API endpoint."""
    register_and_login(client, email="a@example.com")
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id)
    run_id = get_first_run_id(app)

    client.get("/logout")
    register_and_login(client, email="b@example.com")

    resp = client.get(f"/api/forecast/{run_id}/data")
    assert resp.status_code == 403
