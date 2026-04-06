import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", 10))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024  # enforced by Flask automatically


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///forecastiq_dev.db"
    )


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    # Azure SQL: recycle connections before Azure's 30-min idle timeout;
    # pre_ping detects stale connections so Flask-SQLAlchemy reconnects cleanly.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,   # 30 minutes
        "pool_size": 5,
        "max_overflow": 10,
    }

    # On Azure App Service the /home directory is the only persistent volume.
    # Files written outside /home are wiped on restarts/redeploys.
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "/home/uploads")

    # Harden session cookies in production (HTTPS-only, JS-inaccessible).
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    SECRET_KEY = "test-secret-key"
    # Use in-memory SQLite with StaticPool so all connections share the same DB
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
    }
    WTF_CSRF_ENABLED = False


_config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(config_name=None):
    env = config_name or os.environ.get("APP_ENV", "development")
    return _config_map.get(env, DevelopmentConfig)
