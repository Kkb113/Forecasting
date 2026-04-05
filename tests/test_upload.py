"""
Phase 2 upload tests.

Each test gets a fresh in-memory SQLite DB and a temp upload directory
(via the function-scoped `app` and `client` fixtures in conftest.py).
No state leaks between tests.

Helper `make_excel()` creates a minimal valid .xlsx file in memory using
openpyxl — no real file on disk needed until the route saves it.
"""
from io import BytesIO

import openpyxl
import pytest


# ── Helpers ────────────────────────────────────────────────────────────────


def make_excel(columns=None, rows=None):
    """Return a BytesIO containing a valid .xlsx file with the given data."""
    if columns is None:
        columns = ["date", "sales", "region"]
    if rows is None:
        rows = [
            ["2024-01-01", 100, "North"],
            ["2024-02-01", 200, "South"],
            ["2024-03-01", 150, "East"],
        ]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(columns)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def register_and_login(client, email="user@example.com", password="password123"):
    """Register a user (Phase 1 auto-logs them in on success)."""
    client.post("/register", data={"email": email, "password": password})


def upload_file(client, buf=None, filename="data.xlsx", mime=XLSX_MIME):
    """POST to /upload and return the response (no redirect follow)."""
    if buf is None:
        buf = make_excel()
    return client.post(
        "/upload",
        data={"file": (buf, filename, mime)},
        content_type="multipart/form-data",
        follow_redirects=False,
    )


# ── Access control ─────────────────────────────────────────────────────────


def test_upload_page_requires_login(client):
    rv = client.get("/upload", follow_redirects=False)
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_upload_page_loads_when_authenticated(client):
    register_and_login(client)
    rv = client.get("/upload")
    assert rv.status_code == 200
    assert b"Upload" in rv.data


def test_preview_page_requires_login(client):
    rv = client.get("/upload/1", follow_redirects=False)
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_api_preview_requires_login(client):
    rv = client.get("/api/upload/1/preview", follow_redirects=False)
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


# ── Successful upload ──────────────────────────────────────────────────────


def test_successful_xlsx_upload_redirects_to_preview(client, app):
    register_and_login(client)
    rv = upload_file(client)

    # Must redirect to /upload/<id>
    assert rv.status_code == 302
    assert "/upload/" in rv.headers["Location"]


def test_successful_upload_creates_db_record(client, app):
    register_and_login(client)
    upload_file(client, filename="sales.xlsx")

    with app.app_context():
        from app.models.upload import FileUpload

        record = FileUpload.query.first()
        assert record is not None
        assert record.original_name == "sales.xlsx"
        assert record.status == "ready"
        assert record.stored_name != "sales.xlsx"  # must be UUID-based
        assert record.file_size_kb is not None


def test_successful_upload_stores_file_on_disk(client, app):
    import os

    register_and_login(client)
    upload_file(client)

    with app.app_context():
        from app.models.upload import FileUpload

        record = FileUpload.query.first()
        assert os.path.isfile(record.upload_path)


def test_upload_links_to_logged_in_user(client, app):
    register_and_login(client, email="owner@example.com")
    upload_file(client)

    with app.app_context():
        from app.models.upload import FileUpload
        from app.models.user import User

        user = User.query.filter_by(email="owner@example.com").first()
        record = FileUpload.query.first()
        assert record.user_id == user.id


# ── Validation errors ──────────────────────────────────────────────────────


def test_invalid_extension_rejected(client):
    register_and_login(client)
    rv = client.post(
        "/upload",
        data={"file": (BytesIO(b"col1,col2\n1,2"), "data.csv", "text/csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert rv.status_code == 200
    assert b".xlsx" in rv.data or b"allowed" in rv.data


def test_txt_extension_rejected(client):
    register_and_login(client)
    rv = client.post(
        "/upload",
        data={"file": (BytesIO(b"hello"), "notes.txt", "text/plain")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert rv.status_code == 200
    assert b"allowed" in rv.data or b"xlsx" in rv.data


def test_missing_file_field_rejected(client):
    """POST with no file field at all."""
    register_and_login(client)
    rv = client.post(
        "/upload",
        data={},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert rv.status_code == 200
    assert b"select a file" in rv.data.lower()


def test_empty_filename_rejected(client):
    """File field present but no file selected (empty filename)."""
    register_and_login(client)
    rv = client.post(
        "/upload",
        data={"file": (BytesIO(b""), "", "application/octet-stream")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert rv.status_code == 200
    assert b"select a file" in rv.data.lower()


def test_corrupt_excel_rejected(client):
    """A file with .xlsx extension but invalid content must be rejected cleanly."""
    register_and_login(client)
    rv = client.post(
        "/upload",
        data={"file": (BytesIO(b"this is not an excel file"), "fake.xlsx", XLSX_MIME)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert rv.status_code == 200
    # Flash message about invalid Excel
    assert b"valid" in rv.data.lower() or b"read" in rv.data.lower()


def test_corrupt_file_not_saved_to_db(client, app):
    """Corrupt upload must not leave a DB record behind."""
    register_and_login(client)
    client.post(
        "/upload",
        data={"file": (BytesIO(b"garbage"), "bad.xlsx", XLSX_MIME)},
        content_type="multipart/form-data",
    )
    with app.app_context():
        from app.models.upload import FileUpload

        assert FileUpload.query.count() == 0


# ── Preview endpoint (JSON API) ────────────────────────────────────────────


def test_api_preview_returns_columns_and_rows(client, app):
    register_and_login(client)
    columns = ["date", "value", "label"]
    rows = [["2024-01", 42, "A"], ["2024-02", 99, "B"]]
    upload_file(client, buf=make_excel(columns, rows))

    with app.app_context():
        from app.models.upload import FileUpload

        upload_id = FileUpload.query.first().id

    rv = client.get(f"/api/upload/{upload_id}/preview")
    assert rv.status_code == 200

    payload = rv.get_json()
    assert "columns" in payload
    assert "rows" in payload
    assert payload["columns"] == columns
    assert len(payload["rows"]) == 2


def test_api_preview_returns_at_most_10_rows(client, app):
    register_and_login(client)
    many_rows = [[f"2024-{i:02d}-01", i * 10] for i in range(1, 16)]
    upload_file(client, buf=make_excel(["date", "val"], many_rows))

    with app.app_context():
        from app.models.upload import FileUpload

        upload_id = FileUpload.query.first().id

    rv = client.get(f"/api/upload/{upload_id}/preview")
    payload = rv.get_json()
    assert len(payload["rows"]) == 10


# ── Cross-user isolation ───────────────────────────────────────────────────


def test_api_preview_rejects_another_users_file(client, app):
    """User B must not be able to preview User A's upload."""
    # User A uploads
    register_and_login(client, email="alice@example.com")
    upload_file(client)

    with app.app_context():
        from app.models.upload import FileUpload

        upload_id = FileUpload.query.first().id

    client.get("/logout")

    # User B logs in and tries to access User A's preview
    register_and_login(client, email="bob@example.com")
    rv = client.get(f"/api/upload/{upload_id}/preview")
    assert rv.status_code == 403


def test_preview_page_rejects_another_users_file(client, app):
    """User B must not be able to view the preview page for User A's upload."""
    register_and_login(client, email="alice@example.com")
    upload_file(client)

    with app.app_context():
        from app.models.upload import FileUpload

        upload_id = FileUpload.query.first().id

    client.get("/logout")
    register_and_login(client, email="bob@example.com")

    rv = client.get(f"/upload/{upload_id}")
    assert rv.status_code == 403


def test_preview_page_404_for_nonexistent_upload(client):
    register_and_login(client)
    rv = client.get("/upload/99999")
    assert rv.status_code == 403  # non-existent → same 403 (no info leak)
