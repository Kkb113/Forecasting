from flask import Blueprint, render_template
from flask_login import login_required, current_user

from ..models.upload import FileUpload
from ..models.forecast import ForecastRun

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    uid = current_user.id

    upload_count = FileUpload.query.filter_by(user_id=uid).count()
    run_count = ForecastRun.query.filter_by(user_id=uid).count()

    recent_uploads = (
        FileUpload.query.filter_by(user_id=uid)
        .order_by(FileUpload.uploaded_at.desc())
        .limit(5)
        .all()
    )
    recent_runs = (
        ForecastRun.query.filter_by(user_id=uid)
        .order_by(ForecastRun.created_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "dashboard.html",
        user=current_user,
        upload_count=upload_count,
        run_count=run_count,
        recent_uploads=recent_uploads,
        recent_runs=recent_runs,
    )
