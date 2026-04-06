#!/bin/bash
# startup.sh — Azure App Service startup script for ForecastIQ
#
# Azure App Service (Linux, Python 3.11) runs this script as the startup command.
# Configure it in: App Service > Configuration > General settings > Startup Command
#
# Startup command to enter in App Service portal:
#   bash /home/site/wwwroot/startup.sh
#
# Alternatively, set the startup command directly to:
#   gunicorn --bind=0.0.0.0:8000 --workers=2 --timeout=120 --log-level=info run:app

set -e

# Ensure the persistent upload directory exists.
# /home is the only directory that survives App Service restarts/redeploys.
mkdir -p /home/uploads

# Start the production WSGI server.
# --bind       : App Service routes external traffic to port 8000 by default.
# --workers    : 2 workers suits B1/Free tier (1 vCPU); increase for higher tiers.
# --timeout    : 120s allows forecasting models time to complete without Gunicorn killing the worker.
# --log-level  : info streams startup + request logs to App Service log stream.
# --access-logfile - : write access logs to stdout (captured by App Service log stream).
exec gunicorn \
  --bind=0.0.0.0:8000 \
  --workers=2 \
  --timeout=120 \
  --log-level=info \
  --access-logfile=- \
  run:app
