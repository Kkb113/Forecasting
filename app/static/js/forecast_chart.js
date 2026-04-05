/**
 * forecast_chart.js — Chart.js integration for ForecastIQ results page.
 *
 * Reads the run ID from the canvas element's data-run-id attribute, fetches
 * forecast data from /api/forecast/<run_id>/data, and renders a line chart
 * showing historical observations and predicted values side-by-side.
 *
 * Handles null confidence bounds gracefully — chart renders correctly whether
 * or not lower_bound / upper_bound are present.
 */
(function () {
  "use strict";

  var canvas = document.getElementById("forecast-chart");
  if (!canvas) return; // results page not in "complete" state

  var runId = canvas.getAttribute("data-run-id");
  var statusEl = document.getElementById("chart-status");

  function setStatus(msg, isError) {
    if (!statusEl) return;
    statusEl.textContent = msg;
    statusEl.style.display = msg ? "" : "none";
    if (isError) {
      statusEl.className = "alert alert-danger";
    } else {
      statusEl.className = "text-muted chart-loading";
    }
  }

  setStatus("Loading chart data\u2026");

  fetch("/api/forecast/" + runId + "/data")
    .then(function (r) {
      if (!r.ok) throw new Error("Server returned " + r.status);
      return r.json();
    })
    .then(function (data) {
      setStatus(""); // hide loading message
      renderChart(canvas, data);
    })
    .catch(function (err) {
      setStatus("Could not load chart: " + err.message, true);
    });

  function renderChart(canvas, data) {
    var historical = data.historical || [];
    var predictions = data.predictions || [];
    var valueLabel = data.value_column || "Value";

    // ── Build combined x-axis labels ────────────────────────────────────
    var histLabels = historical.map(function (h) { return h.label; });
    var predLabels = predictions.map(function (p) { return p.period_label; });
    var allLabels = histLabels.concat(predLabels);

    var nHist = historical.length;
    var nPred = predictions.length;

    // ── Historical dataset ───────────────────────────────────────────────
    // Occupies positions 0…(nHist-1), null for forecast positions.
    var histValues = historical.map(function (h) { return h.value; });
    var histDataset = histValues.concat(new Array(nPred).fill(null));

    // ── Forecast dataset ─────────────────────────────────────────────────
    // Starts one position before the first forecast label (using the last
    // historical value as a visual bridge), then continues with predictions.
    var predValues = predictions.map(function (p) { return p.predicted_value; });
    var bridge = nHist > 0 ? histValues[nHist - 1] : null;
    var forecastPad = new Array(Math.max(0, nHist - 1)).fill(null);
    var forecastDataset = forecastPad.concat([bridge]).concat(predValues);
    // Trim or pad to match allLabels length
    while (forecastDataset.length < allLabels.length) forecastDataset.push(null);
    forecastDataset = forecastDataset.slice(0, allLabels.length);

    // ── Build dataset array ──────────────────────────────────────────────
    var datasets = [
      {
        label: valueLabel + " (historical)",
        data: histDataset,
        borderColor: "#4361ee",
        backgroundColor: "rgba(67, 97, 238, 0.08)",
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
        tension: 0.3,
        spanGaps: false,
        order: 2,
      },
      {
        label: valueLabel + " (forecast)",
        data: forecastDataset,
        borderColor: "#f97316",
        backgroundColor: "rgba(249, 115, 22, 0.06)",
        borderDash: [6, 3],
        borderWidth: 2.5,
        pointRadius: 3,
        pointHoverRadius: 5,
        tension: 0.3,
        spanGaps: false,
        order: 1,
      },
    ];

    // ── Optional confidence band (when lower/upper bounds are available) ─
    var hasBounds = predictions.some(function (p) {
      return p.lower_bound !== null && p.upper_bound !== null;
    });
    if (hasBounds) {
      var lowerPad = new Array(Math.max(0, nHist - 1)).fill(null);
      var upperPad = new Array(Math.max(0, nHist - 1)).fill(null);
      var lowerValues = lowerPad
        .concat([bridge])
        .concat(predictions.map(function (p) { return p.lower_bound; }))
        .slice(0, allLabels.length);
      var upperValues = upperPad
        .concat([bridge])
        .concat(predictions.map(function (p) { return p.upper_bound; }))
        .slice(0, allLabels.length);

      datasets.push({
        label: "Lower bound",
        data: lowerValues,
        borderColor: "rgba(249, 115, 22, 0.35)",
        borderDash: [3, 3],
        borderWidth: 1,
        pointRadius: 0,
        tension: 0.3,
        spanGaps: false,
        fill: false,
        order: 3,
      });
      datasets.push({
        label: "Upper bound",
        data: upperValues,
        borderColor: "rgba(249, 115, 22, 0.35)",
        borderDash: [3, 3],
        borderWidth: 1,
        pointRadius: 0,
        tension: 0.3,
        spanGaps: false,
        fill: "-1", // fill between upper and lower
        backgroundColor: "rgba(249, 115, 22, 0.07)",
        order: 3,
      });
    }

    // ── Render ───────────────────────────────────────────────────────────
    new Chart(canvas, {
      type: "line",
      data: { labels: allLabels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "top",
            labels: { usePointStyle: true, padding: 16, font: { size: 12 } },
          },
          tooltip: {
            mode: "index",
            intersect: false,
            callbacks: {
              label: function (ctx) {
                if (ctx.parsed.y === null) return null;
                return ctx.dataset.label + ": " + ctx.parsed.y.toFixed(2);
              },
            },
          },
        },
        scales: {
          x: {
            ticks: {
              maxTicksLimit: 14,
              maxRotation: 45,
              font: { size: 11 },
            },
            grid: { color: "rgba(0,0,0,0.04)" },
          },
          y: {
            title: { display: true, text: valueLabel, font: { size: 12 } },
            grid: { color: "rgba(0,0,0,0.04)" },
          },
        },
        interaction: { mode: "nearest", axis: "x", intersect: false },
      },
    });
  }
}());
