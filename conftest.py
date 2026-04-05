"""
Root-level conftest.py — ensures the project root is on sys.path so that
`from app import ...` works under `python -m pytest` regardless of the
working directory.

The `app` fixture uses pytest's built-in `tmp_path` to give each test an
isolated, temporary upload directory that is cleaned up automatically.
"""
import sys
import os

# Insert project root at the front of sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import pytest
from app import create_app
from app.extensions import db as _db


@pytest.fixture()
def app(tmp_path):
    """
    Create an isolated test application with:
    - A fresh in-memory SQLite database (dropped after the test).
    - A temporary upload folder unique to this test invocation.
    """
    flask_app = create_app("testing")
    # Override UPLOAD_FOLDER so uploaded files go to a temp dir, not uploads/
    flask_app.config["UPLOAD_FOLDER"] = str(tmp_path)
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.drop_all()


@pytest.fixture()
def client(app):
    """A test client bound to the isolated test app."""
    return app.test_client()
