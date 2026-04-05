from datetime import datetime, timezone
from ..extensions import db


class FileUpload(db.Model):
    __tablename__ = "file_uploads"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    file_size_kb = db.Column(db.Integer)
    upload_path = db.Column(db.String(500))
    uploaded_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc)
    )
    status = db.Column(db.String(50), default="ready")

    user = db.relationship("User", backref=db.backref("uploads", lazy=True))

    def __repr__(self):
        return f"<FileUpload {self.original_name}>"
