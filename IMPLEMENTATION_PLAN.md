# ForecastIQ — Phased Implementation Plan

## Phase Overview

| Phase | Focus | Deliverable |
|-------|-------|-------------|
| 1 | Project scaffolding & auth | Working login/register with DB |
| 2 | File upload | Upload, store, preview Excel files |
| 3 | Forecasting engine | Run models, persist results |
| 4 | Frontend & charts | Full UI, Chart.js visualizations |
| 5 | Polish & Azure deployment | Production-ready, deployed app |
| 6 | CI/CD | GitHub Actions pipeline |

---

## Phase 1 — Scaffolding & Authentication

**Goal:** Runnable Flask app with user registration, login, and logout backed by Azure SQL.

### Tasks
- [ ] Initialize project folder structure (see ARCHITECTURE.md)
- [ ] Set up `requirements.txt` with Flask, SQLAlchemy, pyodbc, Flask-Login, bcrypt, python-dotenv
- [ ] Create Flask app factory (`app/__init__.py`) and `run.py`
- [ ] Configure `config.py` with `DevelopmentConfig` and `ProductionConfig` (reads from `.env`)
- [ ] Create `users` table via `migrations/001_init_schema.sql`
- [ ] Build `User` SQLAlchemy model (`app/models/user.py`)
- [ ] Build auth routes: `GET/POST /register`, `GET/POST /login`, `GET /logout`
- [ ] Build login/register HTML templates with basic CSS
- [ ] Add Flask-Login `@login_required` decorator to protected routes
- [ ] Smoke test: register a user, log in, see a placeholder dashboard, log out

**Exit Criteria:** Auth flow works end-to-end against a local or Azure SQL database.

---

## Phase 2 — File Upload

**Goal:** Users can upload Excel files; app validates, stores, and previews them.

### Tasks
- [ ] Create `file_uploads` table (migration)
- [ ] Build `FileUpload` SQLAlchemy model
- [ ] Build `storage_service.py` with local file backend
- [ ] Build `file_service.py`: extension check, size limit, UUID rename, column extraction via pandas
- [ ] Build `GET/POST /upload` route and `upload.html` template
- [ ] Build `GET /api/upload/<upload_id>/preview` JSON endpoint
- [ ] Show a preview table (first 10 rows) in the browser after upload using JS fetch
- [ ] Display extracted column names for later use in forecast configuration

**Exit Criteria:** User uploads an `.xlsx` file, sees a preview table and list of columns in the browser; record exists in `file_uploads` table.

---

## Phase 3 — Forecasting Engine

**Goal:** Users configure and run a forecast; results are stored and retrievable.

### Tasks
- [ ] Create `forecast_runs` and `prediction_results` tables (migration)
- [ ] Build `ForecastRun` and `PredictionResult` SQLAlchemy models
- [ ] Build `forecast_service.py`:
  - Load Excel from stored path
  - Accept date column, value column, horizon
  - Infer time frequency (daily/weekly/monthly)
  - Run `ExponentialSmoothing` (Holt-Winters)
  - Fall back to linear regression if < 12 data points
  - Return list of period/value/bounds dicts
- [ ] Build `GET /forecast/configure/<upload_id>` route + template (column picker form)
- [ ] Build `POST /forecast/run` route: validate inputs, call service, persist results, redirect to results
- [ ] Build `GET /forecast/<run_id>` route (results page placeholder — chart added in Phase 4)
- [ ] Build `GET /api/forecast/<run_id>/data` JSON endpoint

**Exit Criteria:** User selects columns, hits "Run Forecast", results appear in DB and on a basic results page as a data table.

---

## Phase 4 — Frontend & Visualizations

**Goal:** Polished UI with Chart.js charts, consistent layout, and history page.

### Tasks
- [ ] Build `base.html` with responsive navbar, flash message area, and footer
- [ ] Apply consistent CSS (`main.css`): color palette, card layout, button styles, form styles
- [ ] Integrate Chart.js on `forecast/results.html`:
  - Line chart: historical data (one color) + forecast (another color + shaded confidence band)
  - Labels from period_label, values from predicted_value
- [ ] Add JavaScript (`forecast.js`) that calls `/api/forecast/<run_id>/data` and renders the chart
- [ ] Style the configure page with a clean column-picker form and horizon slider/input
- [ ] Build `history.html`: paginated table of forecast runs (status, date, columns, horizon, link)
- [ ] Build `dashboard.html`: summary stats (total uploads, total forecasts) + last 3 runs
- [ ] Add loading spinner during forecast run (since it's synchronous)
- [ ] Ensure upload page has drag-and-drop UX (`upload.js`)
- [ ] Mobile-responsive layout (basic breakpoints)

**Exit Criteria:** Complete user flow works in browser: register → upload → configure → view chart → history. UI is clean and presentable for a demo.

---

## Phase 5 — Polish & Azure Deployment

**Goal:** App runs on Azure App Service connected to Azure SQL and Blob Storage.

### Tasks
- [ ] Add Azure Blob Storage backend to `storage_service.py` (using `azure-storage-blob` SDK)
- [ ] Add `ProductionConfig` with Azure SQL connection string format
- [ ] Write `startup.sh` and verify gunicorn startup command
- [ ] Create `.env.example` documenting all required environment variables
- [ ] Provision Azure resources (manual, documented in a deployment checklist):
  - Azure App Service (Linux, Python 3.11)
  - Azure SQL Database
  - Azure Blob Storage container
- [ ] Run `001_init_schema.sql` against Azure SQL
- [ ] Set App Service environment variables (DB connection, secret key, storage account)
- [ ] Deploy via `az webapp up` or zip deploy
- [ ] Verify end-to-end flow on Azure URL
- [ ] Add basic error pages (404, 500 templates)

**Exit Criteria:** App is live on Azure, accessible via browser, full flow works in production.

---

## Phase 6 — CI/CD (Future)

**Goal:** Automated testing and deployment on push to main.

### Planned Tasks
- [ ] Set up GitHub repository
- [ ] Write unit tests for `forecast_service.py` and `file_service.py`
- [ ] Write integration tests for auth and upload routes
- [ ] Create `.github/workflows/deploy.yml`:
  - Trigger on push to `main`
  - Run `pytest`
  - Deploy to Azure App Service on pass
- [ ] Add Azure service principal credentials to GitHub Secrets

**Exit Criteria:** Pushing to `main` triggers tests and auto-deploys to Azure.

---

## Key Dependencies & Risks

| Risk | Mitigation |
|------|------------|
| Azure SQL ODBC driver on App Service | Use `pyodbc` with ODBC Driver 18; verify driver availability or use `pymssql` as fallback |
| Large Excel files causing timeout | Enforce 10 MB upload cap; add row count validation |
| Forecasting fails on short series | Detect < 12 rows and fall back to linear regression with a warning |
| Blob Storage permissions | Use SAS tokens or managed identity; document both approaches |

---

## Environment Variables Required

```
FLASK_ENV=development
SECRET_KEY=<random-string>
DATABASE_URL=mssql+pyodbc://user:pass@server/db?driver=ODBC+Driver+18+for+SQL+Server
STORAGE_BACKEND=local          # or: azure
AZURE_STORAGE_CONNECTION_STRING=<connection-string>
AZURE_BLOB_CONTAINER=forecastiq-uploads
MAX_UPLOAD_MB=10
```
