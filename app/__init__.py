import logging
import os

from flask import flash, redirect, render_template, url_for
from flask import Flask

from .config import get_config
from .extensions import db, login_manager, bcrypt

logger = logging.getLogger(__name__)


def create_app(config_name=None):
    # Use flask_app (not app) to avoid shadowing the app package name
    flask_app = Flask(__name__)
    flask_app.config.from_object(get_config(config_name))

    # ── Upload folder ────────────────────────────────────────────────────
    # flask_app.root_path is the app/ directory; go up one level for project root
    upload_folder = os.path.join(
        os.path.dirname(flask_app.root_path), "uploads"
    )
    flask_app.config.setdefault("UPLOAD_FOLDER", upload_folder)
    os.makedirs(flask_app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ── Initialize extensions ────────────────────────────────────────────
    db.init_app(flask_app)
    login_manager.init_app(flask_app)
    bcrypt.init_app(flask_app)

    # ── Register blueprints (late import prevents circular references) ───
    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.upload import upload_bp
    from .routes.forecast import forecast_bp
    from .routes.history import history_bp

    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(dashboard_bp)
    flask_app.register_blueprint(upload_bp)
    flask_app.register_blueprint(forecast_bp)
    flask_app.register_blueprint(history_bp)

    # ── Create DB tables (imports models so SQLAlchemy sees them) ────────
    with flask_app.app_context():
        from .models import user      # noqa: F401 — registers user_loader
        from .models import upload    # noqa: F401 — registers FileUpload
        from .models import forecast  # noqa: F401 — registers ForecastRun + PredictionResult
        try:
            db.create_all()
        except Exception as exc:  # pragma: no cover
            # Log and continue — avoids crashing on startup if DATABASE_URL is
            # temporarily unreachable.  The app will surface DB errors per-request.
            logger.error("db.create_all() failed during startup: %s", exc)

    # ── Error handlers ───────────────────────────────────────────────────
    @flask_app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @flask_app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    @flask_app.errorhandler(413)
    def file_too_large(e):
        max_mb = flask_app.config.get("MAX_UPLOAD_MB", 10)
        flash(f"File exceeds the {max_mb} MB size limit.", "danger")
        return redirect(url_for("upload.upload"))

    return flask_app
