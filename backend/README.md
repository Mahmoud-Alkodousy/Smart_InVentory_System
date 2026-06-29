# Smart Inventory Manager

A full-stack, AI-powered inventory forecasting and recommendation system.
Upload sales data — a CSV, an Excel file, JSON, or a public Google Sheets
link — and get back a 90-day demand forecast, dynamic safety-stock
recommendations, financial impact, supplier-risk analysis, multi-branch
transfer suggestions, upcoming-event impact (Ramadan, Eid, Black Friday...),
a data-quality report, an auto-generated Purchase Order PDF, and a full
Arabic business report, all without writing a single line of analysis
yourself.

It's built around one core idea: **most real-world spreadsheets are messy**,
and a tool that only works on perfectly-formatted data isn't actually
useful. So the pipeline is designed to recover gracefully at every stage —
from column names in Arabic or English, to missing values, to outright
garbage rows — before ever giving up and asking the user to clean their own
file.

---

## Table of contents

- [Architecture](#architecture)
- [Project layout](#project-layout)
- [Quick start](#quick-start)
- [How it works, end to end](#how-it-works-end-to-end)
- [Backend deep dive](#backend-deep-dive)
- [Frontend deep dive](#frontend-deep-dive)
- [API reference](#api-reference)
- [Environment variables](#environment-variables)
- [Tests](#tests)
- [Known limitations](#known-limitations)

---

## Architecture

```
                                Frontend (React + Vite)
                                         │
                                         │  POST /api/upload  (file or Sheets URL)
                                         ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         FastAPI backend (main.py)                        │
│                                                                            │
│   job_id created immediately → 200 OK → frontend starts polling          │
│                                                                            │
│   Heavy work dispatched to:                                              │
│     • Celery worker          (production — worker.py)                    │
│     • in-process thread      (dev fallback — api/routes.py)              │
│     • scheduler              (recurring runs — monitoring_jobs/)         │
│                                                                            │
│   All three call the SAME orchestrator:                                  │
│   api/pipeline_common.py :: run_full_pipeline()                          │
└──────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  run_full_pipeline()                                                      │
│                                                                            │
│   1. LOAD       data_agent/agent_pipeline.py — routes the file/URL        │
│                  through a 3-tier cleaning strategy (see below)           │
│   2. FORECAST   ml/model.py — Chronos T5, zero-shot, 90-day horizon       │
│   3. RECOMMEND  ml/recommender.py — dynamic safety buffer, financials     │
│   4. ENRICH     ml/supplier_risk.py, ml/multi_branch.py, ml/events.py     │
│   5. DRIFT      monitoring/drift_detector.py — data-quality checks       │
│   6. REPORT     reporting/report_generator.py — Arabic LLM report        │
│                                                                            │
│   Result written to job_store (Redis, or in-memory fallback)             │
└──────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
                  Frontend polls /api/forecast, /api/report, /api/drift
                          and renders the full dashboard
```

### The 3-tier data-cleaning strategy

This is the part of the system most worth understanding, because it's the
difference between "works on the demo file" and "works on whatever a real
business actually exports from their POS system."

```
Uploaded file
     │
     ▼
┌─────────────────────┐
│ 1. fast_validator    │  Already has date/store/item/sales, parseable,
│    (instant)         │  no excessive nulls?  → use as-is. No LLM call,
│                      │  no cost, no latency. This is the common case
│                      │  for anyone who already has clean data.
└─────────────────────┘
     │ fails
     ▼
┌─────────────────────┐
│ 2. smart_cleaner     │  Deterministic, pandas-only:
│    (fast, no LLM)    │   • fuzzy column-name matching (English aliases,
│                      │     Arabic aliases, typo tolerance via difflib)
│                      │   • mixed-format date parsing
│                      │   • negative-sales clipping, null filling via
│                      │     rolling mean / forward-fill
│                      │  Handles the vast majority of "messy but
│                      │  recognisable" files without ever touching an LLM.
└─────────────────────┘
     │ fails (column names too unusual to guess)
     ▼
┌─────────────────────┐
│ 3. Planner→Executor  │  Last resort, sandboxed:
│    →Sandbox loop     │   • Planner LLM (Gemini 2.5 Pro) reads a stratified
│    (slow, LLM-based) │     sample of the file and writes a plan.md
│                      │   • Executor LLM (Gemini 2.5 Flash) turns that
│                      │     plan into actual pandas code
│                      │   • The code runs in a hardened subprocess sandbox
│                      │     (import allowlist, CPU/memory/time caps, no
│                      │     network, no filesystem writes)
│                      │   • Re-validated; up to 2 retries with the
│                      │     sandbox error fed back to the Executor
└─────────────────────┘
     │ fails
     ▼
   Clear, actionable error message back to the user
```

The sandbox step exists specifically because letting an LLM write and
execute arbitrary code is a real security surface — see
`data_agent/sandbox.py`'s docstring for the full list of defence-in-depth
layers (import allowlisting via a custom import hook, hard timeouts, memory
and CPU caps on Linux, no network access, no filesystem writes, code-size
limits).

---

## Project layout

```
.
├── backend/
│   ├── main.py                      FastAPI app, startup/shutdown, CORS, rate limiting
│   ├── worker.py                    Celery task — thin wrapper around run_full_pipeline
│   ├── docker-compose.yml           Redis + API + Celery worker
│   ├── Dockerfile
│   ├── requirements.txt             Production deps (CPU torch by default)
│   ├── requirements-gpu.txt         Optional: local CUDA torch for faster Chronos
│   ├── requirements-dev.txt         pytest + test tooling
│   │
│   ├── api/
│   │   ├── routes.py                Core endpoints: upload, forecast, report, drift, PO
│   │   ├── monitor_routes.py        Scheduled-monitoring endpoints (register/run/etc.)
│   │   ├── pipeline_common.py       run_full_pipeline() — the single shared orchestrator
│   │   ├── job_store.py             Redis-backed job state (+ in-memory fallback)
│   │   └── rate_limiter.py          Centralised slowapi limiter
│   │
│   ├── data_agent/                  The 3-tier cleaning pipeline (see architecture above)
│   │   ├── agent_pipeline.py        Orchestrates fast_validator → smart_cleaner → LLM loop
│   │   ├── fast_validator.py        Tier 1 — zero-LLM-call validation
│   │   ├── smart_cleaner.py         Tier 2 — fuzzy mapping + deterministic cleaning
│   │   ├── schema.py                Optional business-column alias detection
│   │   ├── sampler.py               Stratified sampling for the Planner LLM
│   │   ├── planner.py               Planner LLM — produces a fix plan
│   │   ├── executor.py              Executor LLM — turns the plan into pandas code
│   │   ├── validation_loop.py       Re-validates sandboxed output, up to 2 retries
│   │   └── sandbox.py               Hardened subprocess sandbox for LLM-generated code
│   │
│   ├── data_loader/
│   │   ├── loader.py                CSV / Excel / JSON loading, multi-encoding detection
│   │   └── sheets_loader.py         Public Google Sheets → DataFrame
│   │
│   ├── ml/
│   │   ├── model.py                 Chronos T5 zero-shot forecasting
│   │   ├── recommender.py           Safety-stock buffer, financial impact, savings
│   │   ├── supplier_risk.py         Supplier lead-time risk scoring + switch suggestions
│   │   ├── multi_branch.py          Inter-branch stock transfer suggestions
│   │   ├── events.py                Calendar of recurring demand-shifting events
│   │   └── timeseries.py            Compact chart payload for the frontend timeline
│   │
│   ├── monitoring/
│   │   └── drift_detector.py        Missing values, outliers, zero-streaks, short history
│   │
│   ├── monitoring_jobs/             Scheduled, recurring, multi-user monitoring
│   │   ├── scheduler.py             APScheduler — runs the pipeline per user on a cadence
│   │   ├── user_store.py            Redis-backed user config (+ in-memory fallback)
│   │   ├── alert_checker.py         Low-stock / seasonal alert decision logic
│   │   └── notifier.py              SMTP email notifications
│   │
│   ├── reporting/
│   │   ├── report_generator.py      Arabic business report via LLM (GPT-4o / OpenRouter)
│   │   └── purchase_order.py        PDF Purchase Order generator (reportlab)
│   │
│   └── tests/                       pytest suite — see Tests section below
│
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── Dockerfile                    Multi-stage build (Vite build-time env → nginx)
    ├── nginx.conf
    └── src/
        ├── App.jsx                   Top-level state, upload→poll→results, tab nav
        ├── main.jsx
        ├── index.css
        └── components/
            ├── FileUpload.jsx        Upload form (file or Google Sheets URL)
            ├── PipelineDiagram.jsx   Live pipeline-step visualization while processing
            ├── ForecastDashboard.jsx Core forecast + recommendations table
            ├── ForecastTimeline.jsx  Historical + forecasted demand chart
            ├── InventoryReport.jsx   Renders the Arabic LLM-generated report
            ├── DriftAlert.jsx        Data-quality warnings panel
            ├── MonitoringSetup.jsx   Scheduled-monitoring registration form
            ├── BusinessDashboard.jsx Business Impact Layer container
            └── business/
                ├── SupplierRiskPanel.jsx
                ├── MultiBranchPanel.jsx
                ├── EventsImpactPanel.jsx
                ├── PurchaseOrderPanel.jsx
                └── shared.jsx        Shared UI primitives for the panels above
```

---

## Quick start

### Docker (recommended)

```bash
cd backend
cp .env.example .env
# at minimum, fill in OPENROUTER_API_KEY

docker compose up --build
# starts Redis + API (port 8000) + a Celery worker
```

```bash
cd ../frontend
docker build --build-arg VITE_API_URL=http://localhost:8000 -t sim-frontend .
docker run -p 8080:80 sim-frontend
```

Open `http://localhost:8080`.

### Local dev (no Docker)

```bash
# Terminal 1 — backend
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload

# Terminal 2 — (optional) Celery worker for production-like behavior
cd backend
celery -A worker worker --loglevel=info --concurrency=2

# Terminal 3 — frontend
cd frontend
npm install
cp .env.example .env   # VITE_API_URL=http://localhost:8000
npm run dev
```

Redis and Celery are both optional in dev: `job_store` and `user_store`
fall back to in-memory storage automatically if Redis is unreachable, and
uploads fall back to an in-process background thread if no Celery worker
is detected. This means the whole stack can be exercised — including the
test suite — without any external infrastructure running.

---

## How it works, end to end

1. **Upload.** The frontend `POST`s a file (or a Google Sheets URL) to
   `/api/upload`. The backend creates a `job_id`, dispatches the heavy work
   asynchronously, and responds immediately with `{"job_id": ..., "status":
   "processing"}` — the HTTP request never blocks on the actual pipeline.

2. **Pipeline runs** (Celery worker, or the in-process fallback thread):
   - **Load & clean** through the 3-tier strategy described above.
   - **Forecast 90 days** with Chronos T5 (zero-shot — no per-customer
     training step, works on any uploaded dataset immediately). Returns a
     point forecast plus a confidence interval (low/high) per (store, item)
     pair, not just a single number.
   - **Recommend stock levels.** For each (store, item): compute the
     coefficient of variation (CV) of historical sales, map that to a
     dynamic safety-buffer tier (10% / 20% / 35% — higher volatility gets a
     bigger buffer), then derive `recommended_stock` and `reorder_point`.
     If pricing/current-stock data is present, also compute capital tied
     up, excess-stock value, and potential savings.
   - **Detect seasonal peaks.** If a product's sales history shows a
     strong concentration in one calendar quarter, flag it with a warning
     and an Arabic explanation — even without external calendar data.
   - **Enrich** with the Business Impact Layer: supplier risk scores
     (lead-time exposure, switch suggestions), multi-branch transfer
     opportunities ("move it, don't buy it" — when one branch has excess
     of an item another branch is about to run out of), and upcoming
     calendar events (Ramadan, Eid, Black Friday, Back-to-School) with an
     estimated demand uplift — this exists because Chronos's forecast is
     univariate and has no notion of the Hijri calendar shifting ~11 days
     earlier every Gregorian year.
   - **Check data quality.** Null ratios, statistical outliers (IQR-based),
     long zero-sales streaks, and overall history length — each flagged
     independently so the user knows exactly what to double-check, not
     just "something looks off."
   - **Generate the report.** An LLM (GPT-4o via OpenRouter by default)
     turns the structured recommendations + drift report into a written
     Arabic business report, with a graceful fallback message if the LLM
     call fails — the pipeline never fails outright just because the
     report-writing step did.

3. **Poll & render.** The frontend polls `/api/forecast/{job_id}`,
   `/api/report/{job_id}`, and `/api/drift/{job_id}` every few seconds,
   showing a live pipeline-step diagram while waiting, then renders the
   full dashboard once everything completes.

4. **Optional: schedule it.** Register a Google Sheet (or an uploaded CSV)
   via `/api/monitor/register` for recurring analysis — daily, weekly,
   monthly, quarterly, or semiannual. A background scheduler re-runs the
   exact same `run_full_pipeline()` for each registered user at 06:00 UTC
   on the appropriate cadence, then emails either a low-stock/seasonal
   alert or a routine "analysis complete" notification, depending on what
   the alert checker finds.

---

## Backend deep dive

### Why Chronos instead of a trained model (e.g. XGBoost)

Chronos is a **zero-shot** time-series foundation model — it forecasts
directly from a sequence of past values without any per-dataset training
step. For a multi-tenant SaaS where every customer uploads completely
different products, stores, and demand patterns, that's the difference
between "works the moment someone uploads their first file" and "needs a
training pipeline, stored model artifacts per customer, and a retraining
schedule." The trade-off is inference cost (a transformer forward pass per
series) rather than training cost — which is why `ml/model.py` defaults to
CPU and documents an optional GPU path (see `requirements-gpu.txt`) for
anyone who wants faster inference locally.

### Why three separate execution paths share one function

`run_full_pipeline()` in `api/pipeline_common.py` is called identically
from:
- `api/routes.py`'s in-process thread fallback (used when Celery isn't
  running — convenient for local dev, not meant for production load),
- `worker.py`'s actual Celery task (the production path), and
- `monitoring_jobs/scheduler.py`'s scheduled per-user runs.

This used to be three copy-pasted implementations. Keeping them as one
function means a bug fix or a new pipeline step only needs to happen once
— which matters in practice, not just in theory: see
`tests/test_pipeline_common.py`'s docstring for the story of a bug that
slipped through specifically because of a refactor that briefly
reintroduced the duplication problem in miniature (a single missing
function definition), and the end-to-end test that was added afterward to
make sure it can't happen silently again.

### Why a sandboxed LLM-code-execution path exists at all

Some uploaded files have column names that no fuzzy-matching heuristic can
reasonably guess (entirely non-standard naming, multiple languages mixed
in one header row, etc.). Rather than just failing on those files, the
Planner/Executor/Sandbox loop lets an LLM look at a representative sample,
describe a fix in plain language, generate the actual transformation code,
and run it — but only inside a hardened subprocess with import
allowlisting, CPU/memory/time limits, no network access, and no filesystem
writes. This is explicitly the *last* tier, tried only after the free,
fast, deterministic tiers have both failed.

### Why the recommender's safety buffer is dynamic, not fixed

A flat "20% safety stock for everything" rule either over-stocks predictable
items (wasting capital) or under-stocks volatile ones (risking stockouts).
`ml/recommender.py` computes the coefficient of variation of each
(store, item)'s historical sales and maps it to one of three buffer tiers —
so a steady-selling staple and a wildly seasonal impulse item get
genuinely different treatment from the same formula, rather than the same
treatment applied uniformly.

---

## Frontend deep dive

The dashboard is organized into five tabs, all driven by the same
`forecastData` object once a job completes:

| Tab        | Component             | Shows                                                |
|------------|------------------------|--------------------------------------------------------|
| `business` | `BusinessDashboard`    | Financial impact, suppliers, transfers, events, PO     |
| `forecast` | `ForecastDashboard`    | Per-item 90-day forecast + recommended stock table     |
| `timeline` | `ForecastTimeline`     | Historical vs. forecasted demand chart                 |
| `report`   | `InventoryReport`      | The Arabic LLM-generated business report                |
| `drift`    | `DriftAlert`           | Data-quality warnings (nulls, outliers, gaps)           |

While a job is processing, `PipelineDiagram` renders the live step-by-step
progress (load → clean → forecast → recommend → drift → report) by polling
the job's current step, rather than showing a generic spinner — useful
feedback given that a real run with Chronos can take well over a minute.

A complete mock dataset (`DEMO_DATA` in `App.jsx`) covering 3 stores, 10
items, suppliers, transfers, and seasonal events ships with the frontend,
so the UI can be explored or demoed without a backend running at all.

---

## API reference

All endpoints are under `/api`. Set `API_KEYS` in `.env` (comma-separated)
to require an `X-API-Key` header on every request; leave it empty to
disable auth entirely (dev only — `/api/health` is always reachable
either way).

### Core pipeline (`api/routes.py`)

| Method | Path                                 | Rate limit | Description                                  |
|--------|----------------------------------------|------------|------------------------------------------------|
| GET    | `/api/health`                          | —          | Health check, reports auth status + store backend |
| POST   | `/api/upload`                          | 10/min     | Upload a file or Google Sheets URL → `job_id` |
| GET    | `/api/forecast/{job_id}`               | 60/min     | Poll forecast + recommendations                |
| GET    | `/api/report/{job_id}`                 | 60/min     | Poll the Arabic LLM report                     |
| GET    | `/api/drift/{job_id}`                  | 60/min     | Poll data-quality check results                |
| POST   | `/api/purchase-order`                  | 60/min     | Generate a Purchase Order PDF from line items  |
| GET    | `/api/purchase-order/auto/{job_id}`    | 60/min     | Auto-build a PO PDF from a job's recommendations |

### Scheduled monitoring (`api/monitor_routes.py`, prefix `/api/monitor`)

| Method | Path                       | Rate limit | Description                                    |
|--------|-----------------------------|------------|---------------------------------------------------|
| POST   | `/register`                | 20/min     | Register a Google Sheet for recurring analysis     |
| POST   | `/register-with-file`      | 20/min     | Register an uploaded CSV for recurring analysis    |
| GET    | `/users`                   | 60/min     | List all registered users (admin)                  |
| GET    | `/users/{user_id}`         | 60/min     | Get one user's settings                            |
| PATCH  | `/users/{user_id}`         | 30/min     | Update frequency / email / lead time / etc.        |
| DELETE | `/users/{user_id}`         | 20/min     | Unregister                                         |
| POST   | `/users/{user_id}/run`     | 5/min      | Trigger an immediate analysis run                  |
| GET    | `/users/{user_id}/last`    | 60/min     | Last completed job's results                       |
| GET    | `/frequencies`             | —          | List valid frequency values                        |

Scheduled runs fire automatically at 06:00 UTC on the user's chosen cadence
(daily / weekly / monthly / quarterly / semiannual). After each run, the
alert checker decides between a low-stock/seasonal-warning email or a
routine "analysis complete" notification — see `monitoring_jobs/
alert_checker.py` and `monitoring_jobs/notifier.py`.

---

## Environment variables

See `backend/.env.example` for the full annotated list. The essentials:

| Variable                                      | Purpose                                                   |
|------------------------------------------------|---------------------------------------------------------------|
| `OPENROUTER_API_KEY`                            | Required for the Arabic report (GPT-4o) and the LLM cleaning fallback |
| `API_KEYS`                                      | Comma-separated keys to enable auth (empty = disabled)        |
| `REDIS_URL`                                     | Job store / user store / Celery broker (optional — in-memory fallback) |
| `CHRONOS_MODEL`                                 | `amazon/chronos-t5-{small,base,large,xl}`                     |
| `CHRONOS_DEVICE`                                | `cpu` (default) or `cuda`                                      |
| `UPLOAD_RATE_LIMIT` / `POLL_RATE_LIMIT`         | Override the default rate limits                               |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD`     | Required for scheduled-monitoring email notifications          |
| `OLLAMA`                                        | `true` to route the Planner/Executor LLMs to a local Ollama instance instead of OpenRouter |

Frontend (`frontend/.env.example`):

| Variable        | Purpose                                              |
|------------------|---------------------------------------------------------|
| `VITE_API_URL`   | Backend base URL (empty = same-origin)                  |
| `VITE_API_KEY`   | Sent as `X-API-Key` header if backend auth is enabled    |

Note: `VITE_API_URL` is baked in at **build time**, not read at container
runtime — it's passed as a Docker build arg (`--build-arg VITE_API_URL=...`)
because Vite inlines `import.meta.env.*` values during the build step.

---

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

112 tests across 8 files, covering the recommender's buffer logic, the
3-tier cleaning pipeline's fuzzy matching and deterministic cleaning,
optional-column schema detection, drift detection's statistical checks,
the alert-decision logic, the HTTP contract of every route, and — notably
— an end-to-end run of `run_full_pipeline()` itself with only Chronos and
the LLM report call mocked out, so a broken orchestration step gets caught
by the test suite rather than surfacing two minutes into a real Celery run.

See `backend/tests/README.md` for the full breakdown, including what's
intentionally *not* covered (real Chronos inference, live LLM calls, and
Celery broker wiring — all of which need external infra/network and are
better suited to manual or staging verification than a unit-test suite).

No automated frontend test suite exists yet; see "Known limitations."

---

## Known limitations

- **Chronos forecasting loops sequentially** over each (store, item) pair
  rather than batching multiple series into a single tensor/`predict()`
  call. Fine for small-to-medium catalogs; a real bottleneck on large
  multi-store, multi-item uploads. Batching would be the natural next
  optimization.
- **Two features have a hard external dependency with no offline mode**:
  the LLM-assisted data-cleaning fallback (tier 3) and the Arabic report
  generator both require OpenRouter (or a local Ollama instance) to be
  reachable. Everything else in the pipeline works fully offline.
- **`App.jsx` is a large, single component** (~1000 lines) owning most of
  the frontend's top-level state — job polling, tab navigation, theme,
  elapsed time. The `components/business/` subfolder shows the intended
  pattern of small, focused components; `App.jsx` itself is the natural
  next candidate for that kind of split.
- **No automated frontend tests yet.** The backend's pytest suite would be
  the template to follow — Vitest + React Testing Library would be the
  equivalent setup here.
