# ForecastIQ — Technical Architecture Document

## 1. System Overview

ForecastIQ is a three-tier web application:

```
[Browser (HTML/CSS/JS)]
        |
        | HTTP(S)
        v
[Flask Web Server (Python)]
        |
        |-- Azure SQL Database (users, uploads, forecasts)
        |-- File Storage (local in dev / Azure Blob in prod)
```

---

## 2. Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Charts | Chart.js |
| Backend | Python 3.11, Flask |
| ORM / DB Access | SQLAlchemy + pyodbc |
| Database | Azure SQL Database (SQL Server compatible) |
| Auth | Flask-Login + bcrypt (server-side sessions) |
| Data Processing | pandas, openpyxl |
| Forecasting | statsmodels (ExponentialSmoothing), scikit-learn (linear regression fallback) |
| File Storage (dev) | Local filesystem |
| File Storage (prod) | Azure Blob Storage |
| Hosting | Azure App Service (Linux, Python runtime) |
| Config Management | python-dotenv (.env files, App Service environment vars) |

---

## 3. Folder Structure

```
ForecastIQ/
├── app/
│   ├── __init__.py              # Flask app factory
│   ├── config.py                # Config classes (dev/prod)
│   ├── extensions.py            # SQLAlchemy, LoginManager init
│   ├── models/
│   │   ├── user.py              # User model
│   │   ├── upload.py            # FileUpload model
│   │   ├── forecast.py          # ForecastRun + PredictionResult models
│   ├── routes/
│   │   ├── auth.py              # /register, /login, /logout
│   │   ├── dashboard.py         # / (home/dashboard)
│   │   ├── upload.py            # /upload (file upload endpoint)
│   │   ├── forecast.py          # /forecast/run, /forecast/<id>
│   │   ├── history.py           # /history
│   ├── services/
│   │   ├── file_service.py      # File save/validation logic
│   │   ├── forecast_service.py  # Forecasting logic (model runs)
│   │   ├── storage_service.py   # Abstraction: local vs blob storage
│   ├── static/
│   │   ├── css/
│   │   │   └── main.css
│   │   ├── js/
│   │   │   ├── upload.js
│   │   │   ├── forecast.js
│   │   │   └── chart_helper.js
│   │   └── img/
│   ├── templates/
│   │   ├── base.html            # Layout with nav
│   │   ├── auth/
│   │   │   ├── login.html
│   │   │   └── register.html
│   │   ├── dashboard.html
│   │   ├── upload.html
│   │   ├── forecast/
│   │   │   ├── configure.html   # Column picker + horizon selector
│   │   │   └── results.html     # Chart + table of predictions
│   │   └── history.html
├── migrations/                  # SQL migration scripts (not Alembic for simplicity)
│   └── 001_init_schema.sql
├── uploads/                     # Local dev file storage (gitignored)
├── tests/
│   ├── test_auth.py
│   ├── test_forecast.py
│   └── test_upload.py
├── .env.example                 # Template for environment variables
├── .gitignore
├── requirements.txt
├── run.py                       # Entry point: flask run / gunicorn
├── PRD.md
├── ARCHITECTURE.md
└── IMPLEMENTATION_PLAN.md
```

---

## 4. Database Schema

### 4.1 `users`

```sql
CREATE TABLE users (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    email         NVARCHAR(255) NOT NULL UNIQUE,
    password_hash NVARCHAR(255) NOT NULL,
    display_name  NVARCHAR(100),
    created_at    DATETIME2 DEFAULT GETUTCDATE(),
    is_active     BIT DEFAULT 1
);
```

### 4.2 `file_uploads`

```sql
CREATE TABLE file_uploads (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    user_id       INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    original_name NVARCHAR(255) NOT NULL,
    stored_name   NVARCHAR(255) NOT NULL,   -- UUID-based filename
    file_size_kb  INT,
    upload_path   NVARCHAR(500),            -- local path or blob URI
    uploaded_at   DATETIME2 DEFAULT GETUTCDATE(),
    status        NVARCHAR(50) DEFAULT 'pending'  -- pending | ready | error
);
```

### 4.3 `forecast_runs`

```sql
CREATE TABLE forecast_runs (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    user_id         INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    upload_id       INT NOT NULL REFERENCES file_uploads(id),
    date_column     NVARCHAR(100) NOT NULL,
    value_column    NVARCHAR(100) NOT NULL,
    horizon         INT NOT NULL,           -- number of periods to forecast
    frequency       NVARCHAR(20),           -- D, W, M, Q, Y (inferred or user-selected)
    model_used      NVARCHAR(100),          -- e.g., "ExponentialSmoothing"
    status          NVARCHAR(50) DEFAULT 'pending',  -- pending | running | complete | failed
    error_message   NVARCHAR(MAX),
    created_at      DATETIME2 DEFAULT GETUTCDATE(),
    completed_at    DATETIME2
);
```

### 4.4 `prediction_results`

```sql
CREATE TABLE prediction_results (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    forecast_run_id INT NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
    period_label    NVARCHAR(50) NOT NULL,   -- e.g., "2025-01", "2025-02"
    period_index    INT NOT NULL,            -- 1-based index
    predicted_value FLOAT NOT NULL,
    lower_bound     FLOAT,                   -- confidence interval lower
    upper_bound     FLOAT                    -- confidence interval upper
);
```

---

## 5. API Routes

### Authentication

| Method | Route | Description | Auth Required |
|--------|-------|-------------|---------------|
| GET | `/register` | Show registration page | No |
| POST | `/register` | Create user account | No |
| GET | `/login` | Show login page | No |
| POST | `/login` | Authenticate user, start session | No |
| GET | `/logout` | Destroy session, redirect to login | Yes |

### Dashboard & Navigation

| Method | Route | Description | Auth Required |
|--------|-------|-------------|---------------|
| GET | `/` | Dashboard: summary stats + recent runs | Yes |
| GET | `/history` | List all forecast runs for current user | Yes |

### File Upload

| Method | Route | Description | Auth Required |
|--------|-------|-------------|---------------|
| GET | `/upload` | Show file upload form | Yes |
| POST | `/upload` | Accept file, validate, store, return column list | Yes |

### Forecasting

| Method | Route | Description | Auth Required |
|--------|-------|-------------|---------------|
| GET | `/forecast/configure/<upload_id>` | Show column picker + horizon form | Yes |
| POST | `/forecast/run` | Start a forecast run (synchronous for MVP) | Yes |
| GET | `/forecast/<run_id>` | Show forecast results (chart + table) | Yes |

### API (JSON endpoints for JS)

| Method | Route | Description | Auth Required |
|--------|-------|-------------|---------------|
| GET | `/api/forecast/<run_id>/data` | Return JSON of historical + predicted values | Yes |
| GET | `/api/upload/<upload_id>/preview` | Return first N rows of uploaded file as JSON | Yes |

---

## 6. Frontend Pages

| Page | Template | Purpose |
|------|----------|---------|
| Login | `auth/login.html` | Email + password login form |
| Register | `auth/register.html` | New account form |
| Dashboard | `dashboard.html` | Welcome, recent forecasts, quick upload link |
| Upload | `upload.html` | Drag-and-drop or click-to-upload Excel file |
| Configure Forecast | `forecast/configure.html` | Pick date col, value col, horizon; file preview table |
| Forecast Results | `forecast/results.html` | Chart.js line chart + results table |
| History | `history.html` | Table of all past forecast runs with links |

---

## 7. Backend Modules (Services)

### `file_service.py`
- Validate file extension and MIME type
- Save file to local `uploads/` or Azure Blob
- Return stored path and extracted column names

### `forecast_service.py`
- Load Excel via pandas
- Validate date + value columns
- Infer or accept frequency
- Run `statsmodels.tsa.holtwinters.ExponentialSmoothing` (primary)
- Fall back to linear regression if too few data points
- Return list of `{period, predicted, lower, upper}` dicts

### `storage_service.py`
- Abstraction layer: `save_file()` and `get_file_path()` work the same in dev (local) and prod (Azure Blob)
- Configured via `STORAGE_BACKEND` env var

---

## 8. Security Considerations

- Passwords stored as bcrypt hashes (cost factor 12)
- Sessions managed server-side via Flask-Login
- All DB queries use SQLAlchemy ORM (parameterized, no raw string interpolation)
- File uploads: extension allowlist, size limit enforced at Flask and HTML level
- Uploaded files stored with UUID names (no original filename in path)
- CSRF protection via Flask-WTF (added in Phase 2)
- Environment variables for all secrets (never hardcoded)

---

## 9. Deployment (Azure)

| Component | Azure Service |
|-----------|--------------|
| App hosting | Azure App Service (Linux, Python 3.11) |
| Database | Azure SQL Database (Basic/S0 tier for demo) |
| File storage | Azure Blob Storage (Standard LRS) |
| Secrets | App Service Application Settings (env vars) |
| TLS | Managed by App Service (free HTTPS) |

Startup command: `gunicorn -w 2 -b 0.0.0.0:8000 run:app`
