# ForecastIQ — Azure Deployment Guide

**Production URL:** https://forecastiq-demo-karthik.azurewebsites.net
**Resource Group:** rg-forecastiq-dev
**Web App:** forecastiq-demo-karthik
**App Service Plan:** asp-forecastiq-dev
**SQL Server:** forecastlogic.database.windows.net
**SQL Database:** free-sql-db-0224916
**SQL Username:** forecast

---

## 1. Azure SQL Setup

### 1a. Allow App Service outbound IP in SQL firewall

The SQL Server firewall must allow connections from Azure App Service.

1. Go to **Azure Portal → SQL Server (forecastlogic) → Networking**
2. Under **Firewall rules**, click **Add a firewall rule**
3. Add: `Name=AppService`, `Start IP=0.0.0.0`, `End IP=0.0.0.0`
   *(This is the "Allow Azure services" shorthand — acceptable for demo.)*
4. Alternatively, tick **"Allow Azure services and resources to access this server"**
5. Click **Save**

### 1b. Verify SQL connectivity (optional, from local machine)

```bash
# Install pymssql locally if needed
pip install pymssql

python - <<'EOF'
import pymssql
conn = pymssql.connect(
    server="forecastlogic.database.windows.net",
    user="forecast",
    password="YOUR_PASSWORD",
    database="free-sql-db-0224916",
    port=1433
)
print("Connected:", conn.cursor().execute("SELECT @@VERSION"))
conn.close()
EOF
```

### 1c. Database tables

ForecastIQ uses SQLAlchemy's `db.create_all()` on first startup to create all tables
automatically. **No manual SQL migration is needed.** Tables created:

| Table | Purpose |
|---|---|
| `users` | Registered accounts |
| `file_uploads` | Uploaded Excel file metadata |
| `forecast_runs` | Forecast job metadata (columns, horizon, status) |
| `prediction_results` | Per-period forecast values and confidence bounds |

If you prefer to inspect the schema first, run this in Azure SQL Query Editor:

```sql
-- Check tables after first deploy
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE';
```

---

## 2. App Service Environment Variables

Go to **Azure Portal → App Service (forecastiq-demo-karthik) → Configuration → Application settings**
Add the following key/value pairs. Click **Save** after all are entered.

| Key | Value | Notes |
|---|---|---|
| `APP_ENV` | `production` | Activates ProductionConfig |
| `SECRET_KEY` | *(generated value)* | See generator command below |
| `DATABASE_URL` | *(see format below)* | Azure SQL connection string |
| `UPLOAD_FOLDER` | `/home/uploads` | Persistent volume on App Service |
| `MAX_UPLOAD_MB` | `10` | Max upload file size |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` | Runs `pip install` on deploy |

**Generate SECRET_KEY** (run once locally, paste the output):
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**DATABASE_URL format:**
```
mssql+pymssql://forecast:YOUR_PASSWORD@forecastlogic.database.windows.net:1433/free-sql-db-0224916?charset=utf8
```
Replace `YOUR_PASSWORD` with the actual SQL password.

---

## 3. Startup Command

Go to **Azure Portal → App Service → Configuration → General settings**
Set **Startup Command** to:

```
bash /home/site/wwwroot/startup.sh
```

This script (committed to the repo as `startup.sh`) creates `/home/uploads` and
starts Gunicorn with 2 workers on port 8000.

Alternatively, enter the Gunicorn command directly:

```
gunicorn --bind=0.0.0.0:8000 --workers=2 --timeout=120 --log-level=info run:app
```

---

## 4. Deployment Steps (GitHub → App Service — Manual ZIP Deploy)

### Option A: Deploy from GitHub via App Service Deployment Center (recommended)

1. Go to **App Service → Deployment Center**
2. **Source:** GitHub
3. **Organization/Repository:** `Kkb113/Forecasting`
4. **Branch:** `main`
5. **Build provider:** App Service Build Service (Kudu)
6. Click **Save** — this sets up auto-deploy on every push to `main`

After the first deploy completes (~3–5 min), visit the production URL to verify.

### Option B: Manual ZIP deploy via Azure CLI

```bash
# Install Azure CLI if needed: https://aka.ms/installazurecli

# Log in
az login

# Build a deployment zip (from the repo root)
# Windows PowerShell:
Compress-Archive -Path * -DestinationPath deploy.zip -Force

# Deploy
az webapp deploy `
  --resource-group rg-forecastiq-dev `
  --name forecastiq-demo-karthik `
  --src-path deploy.zip `
  --type zip

# Stream logs to watch startup
az webapp log tail --resource-group rg-forecastiq-dev --name forecastiq-demo-karthik
```

### Option C: Push to GitHub (CI/CD will handle future deploys once set up)

```bash
git add -A
git commit -m "Phase 5: production deployment"
git push origin main
```

---

## 5. Verification Steps

After deployment completes:

### 5a. Check the app is running
```
GET https://forecastiq-demo-karthik.azurewebsites.net/
```
Expected: redirect to `/login` (302) — confirms Flask is serving.

### 5b. Check App Service logs
- **Azure Portal → App Service → Log stream** — watch real-time logs
- Or: `az webapp log tail --resource-group rg-forecastiq-dev --name forecastiq-demo-karthik`

### 5c. End-to-end smoke test (browser)
1. Visit https://forecastiq-demo-karthik.azurewebsites.net/register
2. Register a new account → should land on dashboard
3. Upload a `.xlsx` file with a date column and numeric column
4. Configure a forecast (date col, value col, horizon=6)
5. Run forecast → verify chart renders on results page
6. Visit `/history` → verify run appears

### 5d. Database verification
- **Azure Portal → SQL Database (free-sql-db-0224916) → Query editor**
- Run: `SELECT * FROM users;` — should show the registered user

### 5e. Upload persistence check
- Upload a file, note its filename shown in the preview
- Restart the App Service (`az webapp restart ...`)
- Reload the history page — file record should still be present (stored in `/home/uploads`)

---

## 6. Common Azure Pitfalls — Self-Check

| Pitfall | How we handle it |
|---|---|
| `db.create_all()` crashes on bad `DATABASE_URL` | Wrapped in `try/except` — app starts, errors logged per-request |
| Azure SQL closes idle connections after 30 min | `pool_recycle=1800` + `pool_pre_ping=True` in `ProductionConfig` |
| Uploaded files lost on restart | `UPLOAD_FOLDER=/home/uploads` (App Service persistent volume) |
| App crashes on startup without `DATABASE_URL` | `ProductionConfig` logs the error; won't silently produce a corrupt state |
| `SECRET_KEY` left as default | Documented — must be set before first deploy |
| `DEBUG=True` in production | `ProductionConfig.DEBUG = False` — no stack traces exposed to users |
| Session cookies sent over HTTP | `SESSION_COOKIE_SECURE=True` — cookies only over HTTPS |
| Large forecasts timing out | Gunicorn `--timeout=120` gives 2 min per request |
| Worker count too high for free tier | `--workers=2` matches free/B1 single vCPU |
| Port mismatch (App Service expects 8000) | `--bind=0.0.0.0:8000` in startup.sh |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` missing | App setting documented — Kudu runs `pip install -r requirements.txt` |
| ODBC driver not installed | Using `pymssql` (pure Python + pre-built wheel) — no system ODBC needed |

---

## 7. Environment Variable Reference (Complete)

| Variable | Dev default | Production value |
|---|---|---|
| `APP_ENV` | `development` | `production` |
| `SECRET_KEY` | `dev-secret-...` *(insecure)* | 64-char hex string |
| `DATABASE_URL` | SQLite (`forecastiq_dev.db`) | `mssql+pymssql://forecast:PW@forecastlogic...` |
| `UPLOAD_FOLDER` | `./uploads` (project root) | `/home/uploads` |
| `MAX_UPLOAD_MB` | `10` | `10` |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | N/A | `true` |

---

## 8. What Is NOT Yet Done (Future Phases)

- **Blob Storage**: Uploaded files are stored in `/home/uploads` (App Service local disk).
  For multi-instance scaling or guaranteed durability, migrate to Azure Blob Storage (Phase 5 extension).
- **CI/CD**: Automated test + deploy pipeline via GitHub Actions (Phase 6).
- **Custom domain / TLS cert**: Use the App Service managed certificate for `*.azurewebsites.net` (already included).
- **Secrets rotation**: Move `SECRET_KEY` and `DATABASE_URL` to Azure Key Vault for production hardening.
