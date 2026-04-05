from flask import Blueprint, render_template
from flask_login import login_required, current_user

from ..models.forecast import ForecastRun

history_bp = Blueprint("history", __name__)


@history_bp.route("/history")
@login_required
def history():
    runs = (
        ForecastRun.query.filter_by(user_id=current_user.id)
        .order_by(ForecastRun.created_at.desc())
        .all()
    )
    return render_template("history.html", runs=runs)
