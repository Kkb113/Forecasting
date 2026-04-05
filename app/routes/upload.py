import os

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from ..extensions import db
from ..models.upload import FileUpload
from ..services.file_service import (
    allowed_extension,
    get_columns,
    get_preview,
    save_upload,
)

upload_bp = Blueprint("upload", __name__)


@upload_bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        # ── Presence check ──────────────────────────────────────────────
        if "file" not in request.files or request.files["file"].filename == "":
            flash("Please select a file to upload.", "danger")
            return render_template("upload.html"), 200

        file = request.files["file"]

        # ── Extension check ─────────────────────────────────────────────
        if not allowed_extension(file.filename):
            flash("Only .xlsx and .xls files are allowed.", "danger")
            return render_template("upload.html"), 200

        upload_folder = current_app.config["UPLOAD_FOLDER"]

        # ── Save to disk ─────────────────────────────────────────────────
        try:
            stored_name, safe_original, size_kb = save_upload(file, upload_folder)
        except Exception:
            flash("File could not be saved. Please try again.", "danger")
            return render_template("upload.html"), 200

        file_path = os.path.join(upload_folder, stored_name)

        # ── Validate Excel structure (extract columns) ───────────────────
        try:
            columns = get_columns(file_path)
        except Exception:
            # File saved but unreadable — remove it and report
            try:
                os.remove(file_path)
            except OSError:
                pass
            flash(
                "Could not read the Excel file. "
                "Please check it is a valid .xlsx or .xls file.",
                "danger",
            )
            return render_template("upload.html"), 200

        # ── Persist upload record ────────────────────────────────────────
        record = FileUpload(
            user_id=current_user.id,
            original_name=safe_original,
            stored_name=stored_name,
            file_size_kb=size_kb,
            upload_path=file_path,
            status="ready",
        )
        db.session.add(record)
        db.session.commit()

        flash(f'"{safe_original}" uploaded successfully!', "success")
        return redirect(url_for("upload.preview_page", upload_id=record.id))

    return render_template("upload.html")


@upload_bp.route("/upload/<int:upload_id>")
@login_required
def preview_page(upload_id):
    record = db.session.get(FileUpload, upload_id)
    if record is None or record.user_id != current_user.id:
        abort(403)
    return render_template("upload_preview.html", upload=record)


@upload_bp.route("/api/upload/<int:upload_id>/preview")
@login_required
def api_preview(upload_id):
    record = db.session.get(FileUpload, upload_id)
    if record is None or record.user_id != current_user.id:
        abort(403)

    try:
        columns, rows = get_preview(record.upload_path)
    except Exception:
        return jsonify({"error": "Could not read file preview."}), 500

    return jsonify({"columns": columns, "rows": rows})
