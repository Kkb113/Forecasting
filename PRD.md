# ForecastIQ — Product Requirements Document

## 1. Overview

**Product Name:** ForecastIQ
**Type:** Full-stack web application
**Purpose:** Allow users to upload Excel data files and generate time-series forecasts with interactive visualizations.
**Audience:** Analysts, business users, and data-savvy professionals who need quick forecasting without writing code.

---

## 2. Problem Statement

Business users often have historical data in Excel but lack tools to generate forward-looking forecasts without coding skills or expensive software. ForecastIQ closes this gap by providing a simple web interface to upload data, run forecasting models, and visualize results — all in a browser.

---

## 3. Goals

- Provide secure user registration and login
- Accept Excel file uploads with tabular time-series data
- Run forecasting models on uploaded data (e.g., exponential smoothing, linear regression, Prophet-style)
- Display forecasts as interactive charts alongside historical data
- Store forecast results and allow users to revisit past runs
- Be deployable to Azure App Service with minimal configuration

---

## 4. Non-Goals (Out of Scope for MVP)

- Real-time streaming data
- Multi-tenant organization/team management
- Model training on custom algorithms
- Export to BI tools (Power BI, Tableau)
- CI/CD pipeline (planned for later phase)

---

## 5. User Stories

| ID | As a... | I want to... | So that... |
|----|---------|--------------|------------|
| US-01 | New user | Sign up with email and password | I can access the app securely |
| US-02 | Returning user | Log in with my credentials | I can access my data and forecasts |
| US-03 | Logged-in user | Upload an Excel file | The app can read my historical data |
| US-04 | Logged-in user | Select the date column and value column | The model knows what to forecast |
| US-05 | Logged-in user | Choose a forecast horizon (e.g., next 12 periods) | I control how far ahead to predict |
| US-06 | Logged-in user | View forecast results as a chart | I can interpret predictions visually |
| US-07 | Logged-in user | See a table of predicted values | I can read exact numbers |
| US-08 | Logged-in user | View my upload and forecast history | I can revisit past work |
| US-09 | Logged-in user | Log out | My session ends securely |

---

## 6. Functional Requirements

### Authentication
- FR-01: Users can register with a unique email and a hashed password
- FR-02: Users can log in and receive a server-side session
- FR-03: Protected routes redirect unauthenticated users to the login page
- FR-04: Users can log out, destroying their session

### File Upload
- FR-05: Users can upload `.xlsx` or `.xls` files up to 10 MB
- FR-06: The app validates file format and basic structure on upload
- FR-07: Uploaded files are stored server-side (Azure Blob Storage in production, local in dev)
- FR-08: Upload metadata (filename, size, upload time) is persisted to the database

### Forecasting
- FR-09: Users select a date/time column and a numeric target column from a preview of the uploaded file
- FR-10: Users choose the number of forecast periods (1–60)
- FR-11: The backend runs a forecasting model and returns predictions
- FR-12: Forecast runs and their results are persisted to the database

### Visualization
- FR-13: A line chart shows historical data and forecasted values
- FR-14: A data table shows period, predicted value, and confidence interval (if available)
- FR-15: Users can navigate to past forecast runs from a history page

### Error Handling
- FR-16: Meaningful error messages are shown for invalid files, failed forecasts, or auth errors

---

## 7. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Response time (forecast) | < 10 seconds for files up to 5,000 rows |
| Uptime | 99% (Azure App Service standard tier) |
| Security | Passwords hashed (bcrypt), sessions server-managed, SQL parameterized queries |
| Browser support | Chrome, Edge, Firefox (latest 2 versions) |
| Accessibility | Basic WCAG 2.1 AA compliance |

---

## 8. Assumptions

- Users upload clean or mostly-clean data (minimal data wrangling in MVP)
- One Excel sheet per file; users pick columns after upload
- Forecasting uses a lightweight Python model (no GPU or heavy ML framework needed)
- Azure SQL Database is pre-provisioned before deployment
