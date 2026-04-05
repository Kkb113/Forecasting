"""
forecast_service.py — Time-series forecasting logic.

Primary model:  ExponentialSmoothing (Holt-Winters via statsmodels)
Fallback model: LinearRegression (scikit-learn)

Design:
- All user-facing errors are raised as ForecastError.
- Confidence bounds are stored as None — ExponentialSmoothing without
  simulation does not produce reliable intervals; faking them is misleading.
- The module is stateless: all inputs come as arguments, all outputs as dicts.
"""

import os
import warnings

import numpy as np
import pandas as pd

# Minimum clean (date + numeric value) rows needed to attempt a forecast.
MIN_ROWS = 4


class ForecastError(Exception):
    """User-facing validation or model failure — safe to display directly."""


# ── Public API ─────────────────────────────────────────────────────────────


def run_forecast(
    file_path: str, date_col: str, value_col: str, horizon: int
) -> dict:
    """
    Load an Excel file, validate and clean the data, run a forecast, and
    return structured results.

    Returns:
        {
            "model_used": "ExponentialSmoothing" | "LinearRegression",
            "frequency": "MS" | "W" | "D" | ... | None,
            "predictions": [
                {
                    "period_index": 1,
                    "period_label": "2024-02-01",
                    "predicted_value": 1234.56,
                    "lower_bound": None,
                    "upper_bound": None,
                },
                ...
            ],
        }

    Raises:
        ForecastError: for any user-facing validation or model failure.
    """
    # 1. Load Excel
    try:
        df = _load_excel(file_path)
    except Exception as exc:
        raise ForecastError(f"Could not read the uploaded file: {exc}") from exc

    # 2. Validate column names exist
    available = [str(c) for c in df.columns]
    if date_col not in available:
        raise ForecastError(
            f"Date column '{date_col}' was not found in the file. "
            f"Available columns: {', '.join(available)}"
        )
    if value_col not in available:
        raise ForecastError(
            f"Value column '{value_col}' was not found in the file. "
            f"Available columns: {', '.join(available)}"
        )

    # 3. Coerce to proper types
    dates = pd.to_datetime(df[date_col], errors="coerce")
    values_raw = pd.to_numeric(df[value_col], errors="coerce")

    # 4. Explicit check: value column has no numeric data at all
    if values_raw.notna().sum() == 0:
        raise ForecastError(
            f"Value column '{value_col}' contains no numeric data. "
            "Please select a column that holds numbers."
        )

    # 5. Drop rows where date or value is null after coercion
    mask = dates.notna() & values_raw.notna()
    clean_dates = dates[mask].reset_index(drop=True)
    clean_values = values_raw[mask].reset_index(drop=True)

    # 6. Sort by date ascending
    order = clean_dates.argsort()
    clean_dates = clean_dates.iloc[order].reset_index(drop=True)
    clean_values = clean_values.iloc[order].reset_index(drop=True)

    # 7. Minimum rows check
    n = len(clean_dates)
    if n < MIN_ROWS:
        raise ForecastError(
            f"Not enough usable data points — {n} valid row(s) found after "
            f"removing invalid dates and values; minimum {MIN_ROWS} required. "
            "Check that your date and value columns contain valid data."
        )

    # 8. Infer time frequency (used for period label generation)
    freq = _infer_frequency(clean_dates)

    # 9. Fit model and forecast
    values_arr = clean_values.values.astype(float)
    model_name, pred_arr = _fit_and_predict(values_arr, horizon)

    # 10. Generate future period labels
    last_date = clean_dates.iloc[-1]
    labels = _future_labels(last_date, freq, horizon)

    # 11. Assemble result
    predictions = [
        {
            "period_index": i + 1,
            "period_label": label,
            "predicted_value": float(val),
            "lower_bound": None,
            "upper_bound": None,
        }
        for i, (label, val) in enumerate(zip(labels, pred_arr))
    ]

    return {"model_used": model_name, "frequency": freq, "predictions": predictions}


# ── Public helper for chart data ──────────────────────────────────────────


def get_historical_data(file_path: str, date_col: str, value_col: str) -> list:
    """
    Load and clean the historical (actual) data from an Excel file for
    chart rendering.  Uses the same coercion logic as run_forecast so the
    chart and the model see identical input data.

    Returns:
        A list of {"label": str, "value": float} dicts sorted by date,
        or an empty list on any error (chart still renders forecast-only).
    """
    try:
        df = _load_excel(file_path)
        available = [str(c) for c in df.columns]
        if date_col not in available or value_col not in available:
            return []
        dates = pd.to_datetime(df[date_col], errors="coerce")
        values = pd.to_numeric(df[value_col], errors="coerce")
        mask = dates.notna() & values.notna()
        clean_dates = dates[mask].reset_index(drop=True)
        clean_values = values[mask].reset_index(drop=True)
        order = clean_dates.argsort()
        clean_dates = clean_dates.iloc[order].reset_index(drop=True)
        clean_values = clean_values.iloc[order].reset_index(drop=True)
        return [
            {"label": d.strftime("%Y-%m-%d"), "value": float(v)}
            for d, v in zip(clean_dates, clean_values)
        ]
    except Exception:
        return []


# ── Private helpers ────────────────────────────────────────────────────────


def _load_excel(file_path: str) -> pd.DataFrame:
    """Read an Excel file into a DataFrame, choosing engine by extension."""
    _, ext = os.path.splitext(file_path)
    engine = "xlrd" if ext.lower() == ".xls" else "openpyxl"
    return pd.read_excel(file_path, engine=engine)


def _infer_frequency(dates: pd.Series) -> str | None:
    """
    Infer a pandas frequency alias from a sorted Series of datetimes.
    Returns None when inference is not possible (irregular spacing).
    """
    if len(dates) < 2:
        return None

    dt_index = pd.DatetimeIndex(dates)

    # Try pandas automatic inference first (works perfectly for regular series)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            freq = pd.infer_freq(dt_index)
            if freq:
                return freq
        except Exception:
            pass

    # Fall back to classifying the median gap between observations
    diffs = dt_index.to_series().diff().dropna()
    median_gap = diffs.median()

    if median_gap <= pd.Timedelta(days=1.5):
        return "D"
    if median_gap <= pd.Timedelta(days=8):
        return "W"
    if median_gap <= pd.Timedelta(days=35):
        return "MS"
    if median_gap <= pd.Timedelta(days=100):
        return "QS"
    return "YS"


def _future_labels(last_date: pd.Timestamp, freq: str | None, horizon: int) -> list:
    """
    Return a list of *horizon* future date strings starting after *last_date*.
    Falls back to "Period N" labels if frequency-based generation fails.
    """
    if freq:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                # Generate horizon+1 periods starting at last_date, skip the first
                # (which is last_date itself)
                future = pd.date_range(
                    start=last_date, periods=horizon + 1, freq=freq
                )[1:]
                return [d.strftime("%Y-%m-%d") for d in future]
            except Exception:
                pass
    return [f"Period {i + 1}" for i in range(horizon)]


def _fit_and_predict(values: np.ndarray, horizon: int) -> tuple:
    """
    Attempt ExponentialSmoothing; fall back to LinearRegression on any failure.

    Returns:
        (model_name: str, predictions: np.ndarray of length horizon)
    """
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            # Use additive trend when there are enough points; simple smoothing
            # otherwise (trend=None prevents over-parameterisation on tiny data).
            trend = "add" if len(values) >= 6 else None
            model = ExponentialSmoothing(
                values,
                trend=trend,
                seasonal=None,
                initialization_method="estimated",
            )
            fit = model.fit(optimized=True)
            preds = fit.forecast(horizon)
            # Sanity check: no NaN or Inf in predictions
            if np.all(np.isfinite(preds)):
                return "ExponentialSmoothing", preds
        except Exception:
            pass

    # Fallback
    return _linear_forecast(values, horizon)


def _linear_forecast(values: np.ndarray, horizon: int) -> tuple:
    """Ordinary least-squares linear trend forecast."""
    from sklearn.linear_model import LinearRegression

    X = np.arange(len(values)).reshape(-1, 1)
    lr = LinearRegression()
    lr.fit(X, values)
    future_X = np.arange(len(values), len(values) + horizon).reshape(-1, 1)
    preds = lr.predict(future_X)
    return "LinearRegression", preds
