from datetime import datetime, timezone
from ..extensions import db


class ForecastRun(db.Model):
    __tablename__ = "forecast_runs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    upload_id = db.Column(
        db.Integer,
        db.ForeignKey("file_uploads.id"),
        nullable=False,
    )
    date_column = db.Column(db.String(100), nullable=False)
    value_column = db.Column(db.String(100), nullable=False)
    horizon = db.Column(db.Integer, nullable=False)
    frequency = db.Column(db.String(20))
    model_used = db.Column(db.String(100))
    # pending | complete | failed
    status = db.Column(db.String(50), default="pending", nullable=False)
    error_message = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc)
    )
    completed_at = db.Column(db.DateTime)

    user = db.relationship("User", backref=db.backref("forecast_runs", lazy=True))
    upload = db.relationship(
        "FileUpload", backref=db.backref("forecast_runs", lazy=True)
    )
    predictions = db.relationship(
        "PredictionResult",
        backref="run",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="PredictionResult.period_index",
    )

    def __repr__(self):
        return f"<ForecastRun {self.id} status={self.status}>"


class PredictionResult(db.Model):
    __tablename__ = "prediction_results"

    id = db.Column(db.Integer, primary_key=True)
    forecast_run_id = db.Column(
        db.Integer,
        db.ForeignKey("forecast_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_label = db.Column(db.String(50), nullable=False)
    period_index = db.Column(db.Integer, nullable=False)
    predicted_value = db.Column(db.Float, nullable=False)
    lower_bound = db.Column(db.Float)   # null when not available from model
    upper_bound = db.Column(db.Float)   # null when not available from model

    def __repr__(self):
        return f"<PredictionResult period={self.period_label} val={self.predicted_value}>"
