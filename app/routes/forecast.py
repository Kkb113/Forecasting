from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from ..extensions import db
from ..models.forecast import ForecastRun, PredictionResult
from ..models.upload import FileUpload
from ..services.file_service import get_columns
from ..services.forecast_service import ForecastError, get_historical_data, run_forecast

forecast_bp = Blueprint("forecast", __name__)


# ── Helpers ────────────────────────────────────────────────────────────────


def _own_upload_or_403(upload_id: int) -> FileUpload:
    """Return the FileUpload if it belongs to the current user, else 403."""
    upload = db.session.get(FileUpload, upload_id)
    if upload is None or upload.user_id != current_user.id:
        abort(403)
    return upload


def _own_run_or_403(run_id: int) -> ForecastRun:
    """Return the ForecastRun if it belongs to the current user, else 403."""
    run = db.session.get(ForecastRun, run_id)
    if run is None or run.user_id != current_user.id:
        abort(403)
    return run


# ── Routes ─────────────────────────────────────────────────────────────────


@forecast_bp.route("/forecast/configure/<int:upload_id>")
@login_required
def configure(upload_id):
    upload = _own_upload_or_403(upload_id)

    try:
        columns = get_columns(upload.upload_path)
    except Exception:
        flash(
            "Could not read columns from the uploaded file. "
            "The file may have been moved or deleted.",
            "danger",
        )
        return redirect(url_for("upload.preview_page", upload_id=upload_id))

    return render_template(
        "forecast/configure.html", upload=upload, columns=columns
    )


@forecast_bp.route("/forecast/run", methods=["POST"])
@login_required
def run():
    # ── Validate upload ownership ────────────────────────────────────────
    upload_id = request.form.get("upload_id", type=int)
    if upload_id is None:
        abort(400)
    upload = _own_upload_or_403(upload_id)

    # ── Validate form fields ─────────────────────────────────────────────
    date_col = request.form.get("date_column", "").strip()
    value_col = request.form.get("value_column", "").strip()
    horizon_raw = request.form.get("horizon", "").strip()

    def _back_to_configure(msg):
        flash(msg, "danger")
        return redirect(url_for("forecast.configure", upload_id=upload_id))

    if not date_col:
        return _back_to_configure("Please select a date column.")
    if not value_col:
        return _back_to_configure("Please select a value column.")
    if date_col == value_col:
        return _back_to_configure(
            "Date column and value column must be different."
        )

    try:
        horizon = int(horizon_raw)
        if not (1 <= horizon <= 60):
            raise ValueError
    except (ValueError, TypeError):
        return _back_to_configure(
            "Forecast horizon must be a whole number between 1 and 60."
        )

    # ── Validate selected columns exist in the file ───────────────────────
    try:
        file_columns = get_columns(upload.upload_path)
    except Exception:
        return _back_to_configure(
            "Could not read the uploaded file. It may have been moved or deleted."
        )

    if date_col not in file_columns:
        return _back_to_configure(
            f"Date column '{date_col}' was not found in the file."
        )
    if value_col not in file_columns:
        return _back_to_configure(
            f"Value column '{value_col}' was not found in the file."
        )

    # ── Create run record (pending) ──────────────────────────────────────
    forecast_run = ForecastRun(
        user_id=current_user.id,
        upload_id=upload_id,
        date_column=date_col,
        value_column=value_col,
        horizon=horizon,
        status="pending",
    )
    db.session.add(forecast_run)
    db.session.commit()

    # ── Execute forecast ─────────────────────────────────────────────────
    try:
        result = run_forecast(upload.upload_path, date_col, value_col, horizon)

        forecast_run.model_used = result["model_used"]
        forecast_run.frequency = result["frequency"]
        forecast_run.status = "complete"
        forecast_run.completed_at = datetime.now(timezone.utc)

        for p in result["predictions"]:
            db.session.add(
                PredictionResult(
                    forecast_run_id=forecast_run.id,
                    period_label=p["period_label"],
                    period_index=p["period_index"],
                    predicted_value=p["predicted_value"],
                    lower_bound=p["lower_bound"],
                    upper_bound=p["upper_bound"],
                )
            )

        db.session.commit()
        return redirect(url_for("forecast.results", run_id=forecast_run.id))

    except ForecastError as exc:
        forecast_run.status = "failed"
        forecast_run.error_message = str(exc)
        db.session.commit()
        flash(f"Forecast failed: {exc}", "danger")
        return redirect(url_for("forecast.results", run_id=forecast_run.id))

    except Exception as exc:
        forecast_run.status = "failed"
        forecast_run.error_message = f"Unexpected error: {exc}"
        db.session.commit()
        flash("An unexpected error occurred while running the forecast.", "danger")
        return redirect(url_for("forecast.results", run_id=forecast_run.id))


@forecast_bp.route("/forecast/<int:run_id>")
@login_required
def results(run_id):
    forecast_run = _own_run_or_403(run_id)
    return render_template(
        "forecast/results.html",
        run=forecast_run,
        predictions=forecast_run.predictions,
    )


@forecast_bp.route("/api/forecast/<int:run_id>/data")
@login_required
def api_data(run_id):
    forecast_run = _own_run_or_403(run_id)

    # Historical data is loaded from disk for chart rendering.
    # Returns [] gracefully if the file has been moved or deleted.
    historical = get_historical_data(
        forecast_run.upload.upload_path,
        forecast_run.date_column,
        forecast_run.value_column,
    )

    return jsonify(
        {
            "run_id": forecast_run.id,
            "status": forecast_run.status,
            "model_used": forecast_run.model_used,
            "frequency": forecast_run.frequency,
            "date_column": forecast_run.date_column,
            "value_column": forecast_run.value_column,
            "horizon": forecast_run.horizon,
            # historical: [{label, value}, ...] — the actual observed data
            "historical": historical,
            # predictions: [{period_index, period_label, predicted_value,
            #                lower_bound, upper_bound}, ...]
            "predictions": [
                {
                    "period_index": p.period_index,
                    "period_label": p.period_label,
                    "predicted_value": p.predicted_value,
                    "lower_bound": p.lower_bound,
                    "upper_bound": p.upper_bound,
                }
                for p in forecast_run.predictions
            ],
        }
    )
