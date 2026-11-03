# WindLens

WindLens is a React/FastAPI portal comparing UK national wind forecasts (WINDFOR) with Elexon BMRS FUELHH WIND actuals for January 2026.

## Quickstart

Requirements: Docker Desktop, or Python 3.12+ and Node 20+.

```bash
docker compose up --build
```

- Web Dashboard: http://localhost:5173
- API Documentation: http://localhost:8000/docs
- Health Endpoint: http://localhost:8000/health

### Non-Docker Local Run

Backend:
```bash
python -m pip install -r backend/requirements.txt
set PYTHONPATH=backend   # or export PYTHONPATH=backend
uvicorn app.main:app --app-dir backend --reload
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

## Architecture

```mermaid
flowchart LR
 E[Elexon Insights API] --> C[FastAPI Client / Cache] --> N[UTC Normalization + Vintage Selection] --> G[Hourly Delivery Aggregation vs Half-Hourly Baseline] --> M[Metrics + Data Quality] --> A[FastAPI REST API] --> R[React Interactive Dashboard]
```

- `backend/app/data.py`: Ingests and caches raw Elexon BMRS datasets in `data/raw`.
- `backend/app/analytics.py`: Handles timestamp validation, deduplication, D-1 cutoff selection, delivery-period aggregation, matching, and statistical metrics.
- `backend/app/main.py`: Exposes `/api/overview`, `/api/series`, `/api/interval`, `/api/compare`, and `/health`.
- `frontend/src/main.tsx`: Interactive executive dashboard with granularity toggling, forecast-vs-actual and error charts, date and interval explorer, data-quality audit card, side-by-side methodology benchmark, and transparent methodology disclosure.

## Data Semantics and Methodology Audit

### 1. Source Data Resolution Audit
- **FUELHH (Half-Hourly Generation Outturn by Fuel Type):** Elexon official documentation confirms values represent **average MW** over 30-minute settlement periods (e.g. 00:00–00:30, 00:30–01:00). January 2026 contains 1,488 valid half-hourly WIND actual observations (31 days × 48 settlement periods).
- **WINDFOR (Wind Generation Forecast):** Published by NESO (National Energy System Operator) up to 8 times daily. Official schema and source data inspection confirms that delivery timestamps (`startTime`) are strictly hourly (`:00` minutes, odd settlement periods 1, 3, 5... 47). Forecasted values represent **average MW over 1-hour delivery periods [T, T+1h)**.

### 2. Methodologies Compared

| Metric / Attribute | Hourly Delivery Aggregation (Recommended) | Half-Hourly Exact Match (Legacy Baseline) |
| :--- | :--- | :--- |
| **Actual Observations** | 744 hourly periods (from 1,488 30-min actuals) | 1,488 30-minute intervals |
| **Forecast Observations** | 744 hourly forecasts | 744 hourly forecasts |
| **Matched Intervals** | **744** | **744** |
| **Missing Forecasts** | **0** | **744** (all :30 intervals) |
| **Coverage Percentage** | **100.0%** | **50.0%** |
| **Incomplete Actual Periods**| **0** | N/A |
| **Mean Absolute Error (MAE)**| **2,142.12 MW** | **2,127.48 MW** |
| **Root Mean Squared Error (RMSE)** | **2,611.70 MW** | **2,606.07 MW** |
| **Mean Bias** | **+1,851.90 MW** | **+1,851.53 MW** |

### 3. Why Delivery-Period Aggregation is Scientifically Justified
1. **Dimension Preservation:** Because both datasets report power in Megawatts (MW), energy over a 1-hour delivery period is $E = (P_1 \times 0.5\text{ h}) + (P_2 \times 0.5\text{ h}) = 0.5 \times (P_1 + P_2)\text{ MWh}$. The equivalent average hourly power is $P_{\text{hour}} = \frac{P_1 + P_2}{2}\text{ MW}$. Summing MW as MWh would overestimate power by $2\times$; averaging preserves physical dimensions.
2. **Eliminates Evaluation Asymmetry:** Legacy exact matching paired a 1-hour forecast against only the first 30 minutes of generation, ignoring the second 30 minutes and falsely treating it as a "missing forecast". Delivery-period averaging compares the forecast to the true delivery period outturn.
3. **No Look-Ahead Bias & Strict Completeness:** Forecast vintage selection is strictly constrained by the D-1 09:20 GMT decision cutoff before any aggregation occurs. Incomplete hourly periods are omitted from accuracy metrics rather than imputed with zero.

## Verification and Testing

### Backend Test Suite
The backend test suite (`backend/tests/test_analytics.py`) contains 11 tests covering:
- Delivery-period averaging of complete 30-minute pairs ((3000 + 3200) / 2 = 3100 MW).
- Ensuring MW values are averaged and never summed.
- Omitting incomplete hourly periods without zero-imputation.
- Selection of the latest eligible vintage before D-1 cutoff.
- Rejection of post-cutoff vintages.
- Valid handling of zero-generation outturns and forecasts.
- Rejection of timezone-naive timestamps.
- Distinction between revisions and duplicate records.
- Independent validation of MAE, RMSE, bias, and coverage calculations.
- Granularity switching and methodology comparison output.

```bash
# Host test execution
set PYTHONPATH=backend
pytest backend/tests

# Docker container test execution
docker exec -e PYTHONPATH=/app datagridassignment-backend-1 pytest
```

### Frontend Production Build
```bash
cd frontend
npm run build
```
Type checks and bundles cleanly using Vite and TypeScript.

### Docker Runtime Validation
Validated live in Docker Desktop:
- `docker compose up -d --build` builds backend and frontend images cleanly.
- Backend healthcheck reports healthy on `http://localhost:8000/health`.
- Backend serves `/api/overview`, `/api/series`, and `/api/compare` with instant response from cached raw data.
- Frontend serves production dashboard at `http://localhost:5173`.

## Deployment

### Vercel Single-Project Container Deployment

WindLens is configured for unified single-project deployment on Vercel using **Vercel Services** (`vercel.json`):

- **Architecture:** 
  - `frontend`: Built and served as high-performance edge-cached static assets via Vite.
  - `backend`: Containerized service built from `backend/Dockerfile` and executed on Vercel Fluid compute (OCI container runtime), automatically binding to `0.0.0.0:$PORT`.
  - **Unified Domain Routing:** Top-level rewrites route `/api/*`, `/health`, `/docs`, and `/openapi.json` to the backend container service, while all other routes are handled by the frontend. Browser requests use same-origin relative paths without cross-origin CORS barriers.
- **Cache & Persistence Strategy:** The verified January 2026 Elexon benchmark data (`fuelhh_january_2026.json` and `windfor_january_2026.json`) is bundled directly inside the backend container image (`backend/data/raw`), eliminating reliance on ephemeral serverless storage and avoiding cold-start Elexon API rate limits or latency.
- **Deploy via Vercel CLI:**
  ```bash
  vercel login
  vercel
  vercel --prod
  ```
- **Deploy via Git / GitHub:**
  When ready, initialize Git, push the repository to GitHub, and import the repository into Vercel. Vercel automatically detects `vercel.json` and coordinates the multi-service deployment.
