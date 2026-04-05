"""
file_service.py — File validation, local storage, and Excel data extraction.

Phase 2 only handles local filesystem storage.
Azure Blob Storage is deferred to Phase 5.
"""
import json
import os
import uuid

import pandas as pd
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {".xlsx", ".xls"}


def allowed_extension(filename: str) -> bool:
    """Return True if the filename has an allowed Excel extension."""
    _, ext = os.path.splitext(filename)
    return ext.lower() in ALLOWED_EXTENSIONS


def _excel_engine(file_path: str) -> str:
    """Select the correct pandas engine based on file extension."""
    _, ext = os.path.splitext(file_path)
    return "xlrd" if ext.lower() == ".xls" else "openpyxl"


def save_upload(file_storage, upload_folder: str):
    """
    Save a Werkzeug FileStorage object to *upload_folder* using a UUID-based
    filename so there are no collisions and no original filenames in paths.

    Returns:
        (stored_name, safe_original_name, size_kb)
    """
    safe_original = secure_filename(file_storage.filename)
    _, ext = os.path.splitext(safe_original)
    stored_name = f"{uuid.uuid4().hex}{ext.lower()}"
    dest = os.path.join(upload_folder, stored_name)
    file_storage.save(dest)
    size_kb = os.path.getsize(dest) // 1024
    return stored_name, safe_original, size_kb


def get_columns(file_path: str) -> list:
    """
    Return a list of column name strings from the first row of an Excel file.
    Reads only the header row (nrows=0) for speed.
    """
    engine = _excel_engine(file_path)
    df = pd.read_excel(file_path, nrows=0, engine=engine)
    return [str(c) for c in df.columns]


def get_preview(file_path: str, nrows: int = 10):
    """
    Return (columns, rows) for the first *nrows* rows of an Excel file.

    *rows* is a list-of-lists that is guaranteed JSON-safe: pandas to_json
    handles numpy integers, floats, and datetime objects correctly.

    Returns:
        (columns: list[str], rows: list[list])
    """
    engine = _excel_engine(file_path)
    df = pd.read_excel(file_path, nrows=nrows, engine=engine)
    columns = [str(c) for c in df.columns]
    # to_json handles all numpy/datetime types; orient='values' → list of lists
    rows = json.loads(df.to_json(orient="values", date_format="iso", default_handler=str))
    return columns, rows
