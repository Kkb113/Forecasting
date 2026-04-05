"""
Phase 3 forecasting tests.

Each test gets a fresh in-memory SQLite DB and an isolated temp upload
directory via the function-scoped fixtures in conftest.py.

Flow for most tests:
  1. register_and_login(client)    — creates + logs in user (Phase 1)
  2. do_upload(client)             — uploads a valid .xlsx (Phase 2)
  3. do_run(client, upload_id)     — POSTs to /forecast/run (Phase 3)
"""

from datetime import date
from io import BytesIO

import openpyxl
import pytest

# ── Shared helpers ─────────────────────────────────────────────────────────

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def make_excel(columns, rows):
    """Return a BytesIO containing a valid .xlsx file."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(columns)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def make_ts_excel(n=12):
    """
    Return a BytesIO with a monthly time-series: columns [period, revenue].
    Dates are the 1st of each month starting 2023-01-01 — reliably inferred
    as 'MS' (month-start) frequency by pandas.
    """
    columns = ["period", "revenue"]
    rows = []
    for i in range(n):
        year = 2023 + (i // 12)
        month = (i % 12) + 1
        d = date(year, month, 1)
        rows.append([d.strftime("%Y-%m-%d"), float(1000 + i * 50)])
    return make_excel(columns, rows)


def register_and_login(client, email="user@example.com", password="password123"):
    """Register a user — Phase 1 auto-logs them in."""
    client.post("/register", data={"email": email, "password": password})


def do_upload(client, buf=None, filename="data.xlsx"):
    """POST to /upload. Returns the response (no redirect follow)."""
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


def get_first_run(app):
    with app.app_context():
        from app.models.forecast import ForecastRun
        # Refresh from DB
        run = ForecastRun.query.first()
        if run is None:
            return None
        # Detach-safe: return plain dict
        return {
            "id": run.id,
            "status": run.status,
            "model_used": run.model_used,
            "frequency": run.frequency,
            "error_message": run.error_message,
            "horizon": run.horizon,
            "date_column": run.date_column,
            "value_column": run.value_column,
            "user_id": run.user_id,
        }


def count_predictions(app, run_id):
    with app.app_context():
        from app.models.forecast import PredictionResult
        return PredictionResult.query.filter_by(forecast_run_id=run_id).count()


def do_run(
    client,
    upload_id,
    date_col="period",
    value_col="revenue",
    horizon=6,
    follow=False,
):
    """POST to /forecast/run."""
    return client.post(
        "/forecast/run",
        data={
            "upload_id": str(upload_id),
            "date_column": date_col,
            "value_column": value_col,
            "horizon": str(horizon),
        },
        follow_redirects=follow,
    )


# ── Configure page ─────────────────────────────────────────────────────────


def test_configure_requires_login(client):
    rv = client.get("/forecast/configure/1", follow_redirects=False)
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_configure_rejects_another_users_upload(client, app):
    # User A uploads
    register_and_login(client, email="a@example.com")
    do_upload(client)
    upload_id = get_first_upload_id(app)
    client.get("/logout")

    # User B tries to configure User A's upload
    register_and_login(client, email="b@example.com")
    rv = client.get(f"/forecast/configure/{upload_id}")
    assert rv.status_code == 403


def test_configure_page_loads_with_columns(client, app):
    register_and_login(client)
    do_upload(client, buf=make_ts_excel())
    upload_id = get_first_upload_id(app)

    rv = client.get(f"/forecast/configure/{upload_id}")
    assert rv.status_code == 200
    assert b"period" in rv.data
    assert b"revenue" in rv.data


def test_configure_nonexistent_upload_returns_403(client):
    register_and_login(client)
    rv = client.get("/forecast/configure/99999")
    assert rv.status_code == 403


# ── Run route — access control ─────────────────────────────────────────────


def test_run_requires_login(client):
    rv = client.post(
        "/forecast/run",
        data={"upload_id": "1", "date_column": "period",
              "value_column": "revenue", "horizon": "6"},
        follow_redirects=False,
    )
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_run_rejects_another_users_upload(client, app):
    # User A uploads
    register_and_login(client, email="a@example.com")
    do_upload(client)
    upload_id = get_first_upload_id(app)
    client.get("/logout")

    # User B tries to run forecast against User A's upload
    register_and_login(client, email="b@example.com")
    rv = do_run(client, upload_id)
    assert rv.status_code == 403


# ── Successful forecast run ────────────────────────────────────────────────


def test_successful_run_redirects_to_results(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)

    rv = do_run(client, upload_id, horizon=6, follow=False)
    assert rv.status_code == 302
    assert "/forecast/" in rv.headers["Location"]


def test_successful_run_status_is_complete(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)

    do_run(client, upload_id, horizon=6)
    run = get_first_run(app)
    assert run is not None
    assert run["status"] == "complete"


def test_successful_run_persists_correct_horizon(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)

    do_run(client, upload_id, horizon=9)
    run = get_first_run(app)
    assert run["horizon"] == 9


def test_successful_run_persists_prediction_rows(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)

    do_run(client, upload_id, horizon=6)
    run = get_first_run(app)
    assert count_predictions(app, run["id"]) == 6


def test_successful_run_records_model_used(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)

    do_run(client, upload_id, horizon=6)
    run = get_first_run(app)
    assert run["model_used"] in ("ExponentialSmoothing", "LinearRegression")


def test_successful_run_links_correct_columns(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)

    do_run(client, upload_id, date_col="period", value_col="revenue")
    run = get_first_run(app)
    assert run["date_column"] == "period"
    assert run["value_column"] == "revenue"


# ── Input validation ───────────────────────────────────────────────────────


def test_run_invalid_date_column_rejected(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)

    rv = do_run(client, upload_id, date_col="nonexistent_col", follow=True)
    assert rv.status_code == 200
    # Flash message mentions the column or 'not found'
    assert b"not found" in rv.data or b"nonexistent_col" in rv.data


def test_run_invalid_date_column_creates_no_run(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)

    do_run(client, upload_id, date_col="nonexistent_col")
    # The route rejects before creating a run record
    with app.app_context():
        from app.models.forecast import ForecastRun
        assert ForecastRun.query.count() == 0


def test_run_invalid_value_column_rejected(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)

    rv = do_run(client, upload_id, value_col="nonexistent_col", follow=True)
    assert rv.status_code == 200
    assert b"not found" in rv.data or b"nonexistent_col" in rv.data


def test_run_horizon_too_large_rejected(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)

    rv = do_run(client, upload_id, horizon=100, follow=True)
    assert rv.status_code == 200
    assert b"60" in rv.data or b"horizon" in rv.data.lower()


def test_run_horizon_zero_rejected(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)

    rv = do_run(client, upload_id, horizon=0, follow=True)
    assert rv.status_code == 200
    assert b"60" in rv.data or b"horizon" in rv.data.lower()


def test_run_horizon_negative_rejected(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)

    rv = do_run(client, upload_id, horizon=-5, follow=True)
    assert rv.status_code == 200
    assert b"60" in rv.data or b"horizon" in rv.data.lower()


def test_run_missing_date_column_rejected(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)

    rv = do_run(client, upload_id, date_col="", follow=True)
    assert rv.status_code == 200
    assert b"date" in rv.data.lower()


def test_run_same_column_for_date_and_value_rejected(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)

    rv = do_run(client, upload_id, date_col="period", value_col="period", follow=True)
    assert rv.status_code == 200
    assert b"different" in rv.data.lower() or b"same" in rv.data.lower()


# ── Too few data rows ──────────────────────────────────────────────────────


def test_run_too_few_rows_creates_failed_run(client, app):
    register_and_login(client)
    # Only 2 rows — below MIN_ROWS=4
    do_upload(client, buf=make_ts_excel(n=2))
    upload_id = get_first_upload_id(app)

    do_run(client, upload_id)
    run = get_first_run(app)
    assert run is not None
    assert run["status"] == "failed"
    assert run["error_message"] is not None
    assert "valid" in run["error_message"].lower() or "enough" in run["error_message"].lower()


def test_run_too_few_rows_persists_no_predictions(client, app):
    register_and_login(client)
    do_upload(client, buf=make_ts_excel(n=2))
    upload_id = get_first_upload_id(app)

    do_run(client, upload_id)
    run = get_first_run(app)
    assert count_predictions(app, run["id"]) == 0


def test_run_non_numeric_value_column_creates_failed_run(client, app):
    register_and_login(client)
    # Value column contains only text — not numeric
    buf = make_excel(
        ["period", "category"],
        [["2023-01-01", "North"], ["2023-02-01", "South"],
         ["2023-03-01", "East"],  ["2023-04-01", "West"],
         ["2023-05-01", "North"], ["2023-06-01", "South"]],
    )
    do_upload(client, buf=buf)
    upload_id = get_first_upload_id(app)

    do_run(client, upload_id, value_col="category")
    run = get_first_run(app)
    assert run["status"] == "failed"
    assert run["error_message"] is not None


# ── Results page ───────────────────────────────────────────────────────────


def test_results_page_requires_login(client):
    rv = client.get("/forecast/1", follow_redirects=False)
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_results_page_rejects_another_users_run(client, app):
    # User A runs a forecast
    register_and_login(client, email="a@example.com")
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id)
    run = get_first_run(app)
    client.get("/logout")

    # User B tries to view User A's results
    register_and_login(client, email="b@example.com")
    rv = client.get(f"/forecast/{run['id']}")
    assert rv.status_code == 403


def test_results_page_shows_predictions(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id, horizon=6, follow=False)
    run = get_first_run(app)

    rv = client.get(f"/forecast/{run['id']}")
    assert rv.status_code == 200
    assert b"complete" in rv.data
    # Prediction rows render period labels
    assert b"Period" in rv.data or b"2024" in rv.data or b"2023" in rv.data


def test_results_page_shows_failed_status(client, app):
    register_and_login(client)
    do_upload(client, buf=make_ts_excel(n=2))  # too few rows → failed
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id, follow=False)
    run = get_first_run(app)

    rv = client.get(f"/forecast/{run['id']}")
    assert rv.status_code == 200
    assert b"failed" in rv.data


# ── API endpoint ───────────────────────────────────────────────────────────


def test_api_requires_login(client):
    rv = client.get("/api/forecast/1/data", follow_redirects=False)
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_api_rejects_another_users_run(client, app):
    # User A runs a forecast
    register_and_login(client, email="a@example.com")
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id)
    run = get_first_run(app)
    client.get("/logout")

    # User B tries to access User A's API data
    register_and_login(client, email="b@example.com")
    rv = client.get(f"/api/forecast/{run['id']}/data")
    assert rv.status_code == 403


def test_api_returns_correct_structure(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id, horizon=6)
    run = get_first_run(app)

    rv = client.get(f"/api/forecast/{run['id']}/data")
    assert rv.status_code == 200

    payload = rv.get_json()
    assert payload["status"] == "complete"
    assert payload["horizon"] == 6
    assert payload["date_column"] == "period"
    assert payload["value_column"] == "revenue"
    assert "model_used" in payload
    assert "predictions" in payload
    assert len(payload["predictions"]) == 6


def test_api_prediction_fields_are_present(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id, horizon=3)
    run = get_first_run(app)

    rv = client.get(f"/api/forecast/{run['id']}/data")
    payload = rv.get_json()

    for p in payload["predictions"]:
        assert "period_index" in p
        assert "period_label" in p
        assert "predicted_value" in p
        assert "lower_bound" in p   # may be null — key must exist
        assert "upper_bound" in p   # may be null — key must exist
        assert isinstance(p["predicted_value"], float)


def test_api_prediction_values_are_finite(client, app):
    register_and_login(client)
    do_upload(client)
    upload_id = get_first_upload_id(app)
    do_run(client, upload_id, horizon=6)
    run = get_first_run(app)

    rv = client.get(f"/api/forecast/{run['id']}/data")
    payload = rv.get_json()

    import math
    for p in payload["predictions"]:
        assert math.isfinite(p["predicted_value"]), \
            f"predicted_value is not finite: {p['predicted_value']}"


def test_api_nonexistent_run_returns_403(client):
    register_and_login(client)
    rv = client.get("/api/forecast/99999/data")
    assert rv.status_code == 403
