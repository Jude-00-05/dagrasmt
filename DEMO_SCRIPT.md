# WindLens Demo Script

## A. Client pitch — under 5 minutes

1. **0:00–0:45: Introduction & Purpose**
   - Introduce WindLens: a decision-time procurement intelligence platform comparing UK national wind forecasts (Elexon BMRS WINDFOR) against metered actual outturns (FUELHH WIND) for January 2026.
   - Explain that energy trading desks must evaluate forecast risk based on information available *before* gate closure, not hindsight.

2. **0:45–2:00: Granularity Audit & Core Metrics**
   - Point to the executive metric cards: MAE (2,142 MW), RMSE (2,611 MW), Bias (+1,852 MW), and Matched Intervals (744 / 744, 100% coverage).
   - Explain the 09:20 GMT D-1 analytical cutoff pill, modeling the day-ahead auction decision timeline.
   - Highlight the **Evaluation Methodology toggle**: show how switching between **Hourly Delivery-Period Aggregation (Recommended)** and **Half-Hourly Exact Match (Legacy Baseline)** updates the dashboard.

3. **2:00–3:15: Interactive Exploration (Date & Interval Explorer)**
   - Change the delivery date in the date picker and observe the intraday curves:
     - Top chart: Forecast vs Actual showing delivery ramp and diurnal patterns.
     - Bottom chart: Interval forecast error showing over- and under-forecasting blocks.
   - Walk through the Interval Explorer table: show delivery intervals (`00:00–01:00`), forecasted MW, actual MW, interval error, and the exact forecast vintage publication timestamp (`publishTime`).

4. **3:15–4:15: Methodology Audit & Data Quality**
   - Scroll to the **Methodology Audit & Benchmark Table**:
     - Explain why WINDFOR is published on 1-hour delivery intervals while FUELHH records 30-minute settlement periods.
     - Show how averaging two consecutive 30-minute actuals ((HH1 + HH2) / 2) accurately reflects the physical 1-hour delivery period, eliminating the 50% "missing forecast" artifact of naive timestamp matching.
     - Emphasize that incomplete hours are isolated rather than filled with zero.
   - Review the Data Quality Audit card: 744 matched intervals, 1,488 raw 30-min actuals audited, 0 incomplete periods, 0 duplicate records, 0 invalid rows.

5. **4:15–5:00: Procurement Desk Takeaways & Boundaries**
   - Conclude with the trading desk context: WindLens quantifies wind volume uncertainty and structural over-forecasting bias (+1,852 MW).
   - Reiterate that it intentionally does not estimate net imbalance penalties or total procurement requirements without portfolio demand and position data.

---

## B. Technical walkthrough — under 5 minutes

1. **0:00–1:00: Architecture Overview**
   - Walk through the stack: React 18 + TypeScript + Vite frontend, Python 3.12 + FastAPI backend, containerized via Docker Compose.
   - Review the pipeline: Elexon BMRS ingestion -> filesystem cache in `data/raw` -> UTC normalization -> D-1 cutoff filtering -> delivery-period aggregation -> statistical analytics -> REST API.

2. **1:00–2:15: Deep Dive into `analytics.py` & Aggregation Logic**
   - Open `backend/app/analytics.py`:
     - Show `forecast_map`: filters by `publishTime <= cutoff(startTime)` and selects the latest eligible vintage for each delivery interval.
     - Show `aggregate_hourly_actuals`: checks presence of both 30-minute intervals [T, T+30m) and [T+30m, T+1h), computes `(v0 + v1) / 2.0` to preserve MW power dimensions, and logs incomplete periods.
     - Show `build_series`: supports both `'hourly'` and `'half-hourly'` modes to preserve auditability.
     - Point out timezone enforcement: naive timestamps trigger `ValueError`.

3. **2:15–3:15: API Endpoints & Caching**
   - Open `http://localhost:8000/docs`:
     - `/api/overview`: returns selected granularity metrics, quality audit, and the side-by-side comparison payload.
     - `/api/series`: serves intraday curves with granularity parameter.
     - `/api/compare`: provides direct access to both evaluation methodologies.
     - `/health`: used by Docker healthchecks.
   - Explain cache resolution: `data.py` auto-detects `data/raw` across Docker mounts, bundled container data, and local filesystem paths, ensuring instant response times.

4. **3:15–4:15: Test Suite & Verification**
   - Run `pytest backend/tests` (or `docker exec -e PYTHONPATH=/app datagridassignment-backend-1 pytest`):
     - Point out all 11 unit tests passing: aggregation math, MW dimension preservation (averaging vs summing), missing half-hour handling, vintage cutoff enforcement, post-cutoff rejection, zero-value validity, duplicate handling, and independent metric verification.
   - Run `cd frontend; npm run build`: demonstrate clean TypeScript compilation and production bundle creation.

5. **4:15–5:00: Production Deployment Strategy**
   - Explain the single-project Vercel Services container architecture (`vercel.json`):
     - Edge-delivered Vite frontend + containerized FastAPI backend running on Fluid compute.
     - Unified routing rewrites (`/api/*`, `/health`, `/docs` -> backend container).
     - Bundled historical dataset in `backend/data/raw` for zero-latency serverless cold starts without external storage costs.

