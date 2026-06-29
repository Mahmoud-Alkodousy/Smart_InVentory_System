# 📦 Smart Inventory Manager
### AI-Powered, Self-Healing Inventory Forecasting & Recommendation Platform

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.3-61DAFB.svg)](https://react.dev/)
[![Celery](https://img.shields.io/badge/Celery-5.3-37814A.svg)](https://docs.celeryq.dev/)
[![Chronos](https://img.shields.io/badge/Amazon%20Chronos-T5%20Forecasting-orange.svg)](https://github.com/amazon-science/chronos-forecasting)
<img src="https://img.shields.io/badge/Code%20Lines-11K%2B-blue" />
<img src="https://img.shields.io/badge/Backend%20Modules-30-purple" />
<img src="https://img.shields.io/badge/Tests-112%20passing-brightgreen" />
<img src="https://img.shields.io/badge/Pipeline-3--Tier%20Self--Healing-red" />

---

## 📑 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [System Architecture](#️-system-architecture)
- [Tech Stack](#-tech-stack)
- [Installation](#-installation)
- [Usage](#-usage)
- [The 3-Tier Self-Healing Pipeline](#-the-3-tier-self-healing-pipeline)
- [Project Structure](#-project-structure)
- [API Reference](#-api-reference)
- [Challenges & Solutions](#-challenges--solutions)
- [Performance Metrics](#-performance-metrics)
- [Future Enhancements](#-future-enhancements)
- [Developer](#-developer)

---

## 🎯 Overview

### What is Smart Inventory Manager?

**Smart Inventory Manager** is a full-stack, AI-powered platform that turns raw, messy sales data into a 90-day demand forecast, dynamic safety-stock recommendations, financial impact analysis, supplier-risk scoring, multi-branch transfer suggestions, seasonal/event-driven demand shifts, a data-quality audit, an auto-generated Purchase Order PDF, and a full Arabic business report — without the user writing a single line of analysis themselves.

### Project Description

Most inventory tools assume the input is already clean. In practice, real-world exports from POS systems are full of mixed languages, inconsistent date formats, missing values, and unpredictable column names. **Smart Inventory Manager is built around the opposite assumption**: that messiness is the default, and a tool that only works on a perfectly-formatted demo CSV isn't actually useful to a real business.

So instead of one rigid loader, the system runs every upload through a three-tier recovery pipeline — fast deterministic validation, then fuzzy/rule-based cleaning, and only as a last resort, a sandboxed LLM agent that writes and safely executes its own cleaning code — before ever telling the user "please fix your file."

**Core Objectives:**
- 🎯 **Forecast demand 90 days out** with a zero-shot time-series model — no training step per customer
- 🩹 **Recover gracefully from messy data** instead of failing on the first malformed row
- 💰 **Translate forecasts into money** — capital tied up, excess-stock value, potential savings
- 🌍 **Account for context a univariate model can't see** — Ramadan, Eid, Black Friday, supplier risk, inter-branch transfers
- 📨 **Run unattended** — register once, get recurring analysis and email alerts on a schedule

### Why This Project Stands Out

| Feature | Typical Inventory Tools | Smart Inventory Manager |
|---|---|---|
| **Input data** | Assumes clean, fixed schema | 3-tier recovery: fast validator → fuzzy cleaner → sandboxed LLM agent |
| **Forecasting** | Per-customer trained model | Zero-shot (Amazon Chronos T5) — works on first upload |
| **Safety stock** | Flat % rule for everything | Per-item buffer tier driven by coefficient of variation |
| **Context awareness** | None | Hijri calendar events, supplier lead-time risk, multi-branch transfers |
| **Code execution from an LLM** | N/A / unsafe | Hardened subprocess sandbox — import allowlist, resource caps, no network |
| **Reporting** | Numbers only | Auto-generated Arabic business narrative + Purchase Order PDF |
| **Automation** | Manual re-runs | APScheduler-driven recurring analysis with email alerting |

---

## ✨ Key Features

### 🧠 1. Self-Healing Data Ingestion (3-Tier Pipeline)

The foundation of the whole system — see the [dedicated section](#-the-3-tier-self-healing-pipeline) below for the full breakdown. In short:

```
✅ Tier 1 — fast_validator: instant pass for already-clean data, zero LLM cost
✅ Tier 2 — smart_cleaner: fuzzy Arabic/English column matching, mixed-format
            date parsing, null imputation — deterministic, no LLM call
✅ Tier 3 — Planner → Executor → Sandbox: an LLM plans a fix, another LLM
            writes the pandas code, a hardened subprocess actually runs it
```

### 📈 2. Zero-Shot Demand Forecasting

- **Model:** Amazon Chronos T5 — a pretrained time-series foundation model
- **Horizon:** 90 days per (store, item) pair
- **Output:** point forecast **plus** a low/high confidence interval, not just a single number
- **No training pipeline required** — works the moment a new customer uploads their first file, which matters for a multi-tenant tool where every dataset looks completely different

### 💡 3. Dynamic Safety-Stock & Financial Recommendations

`ml/recommender.py` computes the **coefficient of variation (CV)** of each item's historical sales and maps it to one of three safety-buffer tiers (10% / 20% / 35%) — so a steady-selling staple and a wildly seasonal item get genuinely different treatment instead of one flat rule applied everywhere. Where pricing/stock data exists, it also derives:

```
📊 Computed per (store, item):
├── recommended_stock & reorder_point
├── capital tied up in current stock
├── excess-stock value
└── potential savings from right-sizing inventory
```

### 🏢 4. Business Impact Layer

A set of enrichment modules that compensate for the fact that a univariate forecasting model has no notion of context:

| Module | What it does |
|---|---|
| `ml/supplier_risk.py` | Scores suppliers on lead-time exposure, suggests switches |
| `ml/multi_branch.py` | "Move it, don't buy it" — flags transfer opportunities between branches |
| `ml/events.py` | Models demand uplift around Ramadan, Eid, Black Friday, Back-to-School — accounting for the Hijri calendar shifting ~11 days earlier every Gregorian year |
| `monitoring/drift_detector.py` | Flags null ratios, IQR-based outliers, zero-sales streaks, and short history — independently, so the user knows exactly what to double-check |

### 📝 5. Arabic LLM Business Report

`reporting/report_generator.py` turns the structured forecast + recommendations + drift findings into a written **Arabic-language business narrative** via GPT-4o (through OpenRouter), with a graceful fallback message if the LLM call fails — a failed report-writing step never takes down the rest of the pipeline.

### 📄 6. Auto-Generated Purchase Order PDFs

`reporting/purchase_order.py` builds a print-ready PDF Purchase Order directly from a job's recommendations (or from manually supplied line items), using `reportlab`'s native Arabic bidi/shaping support for correctly-rendered Arabic text in the document.

### ⏰ 7. Scheduled, Multi-User Monitoring

Register a Google Sheet or an uploaded CSV once, and the system re-runs the **exact same** pipeline for that user automatically:

```
🗓️ Supported cadences:
├── Daily
├── Weekly
├── Monthly
├── Quarterly
└── Semiannual
```

Built on APScheduler, with Redis-backed (or in-memory fallback) per-user config, and `monitoring_jobs/alert_checker.py` deciding between a routine "analysis complete" email and an urgent low-stock/seasonal-warning email after every run.

### 🖥️ 8. Live Pipeline Visualization

Rather than a generic loading spinner, `PipelineDiagram.jsx` polls the job's current step and renders the live progress through load → clean → forecast → recommend → drift → report — genuinely useful given that a real Chronos run can take well over a minute.

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                          │
│              React + Vite Frontend (4.5K+ lines, 13 components)     │
│   5 tabs: Business · Forecast · Timeline · Report · Drift           │
└─────────────────────────────────────────────────────────────────────┘
                                    │  POST /api/upload (file or Sheets URL)
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       FastAPI Backend (main.py)                     │
│         job_id created instantly → 200 OK → frontend polls          │
│                                                                       │
│   Heavy work dispatched to ONE of three execution paths:             │
│     • Celery worker        (production — worker.py)                 │
│     • in-process thread    (dev fallback — api/routes.py)            │
│     • APScheduler          (recurring runs — monitoring_jobs/)       │
│                                                                       │
│   All three call the SAME orchestrator — no duplicated logic:        │
│              api/pipeline_common.py :: run_full_pipeline()           │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  run_full_pipeline()                                                  │
│                                                                        │
│   1. LOAD       data_agent/  — 3-tier self-healing cleaning strategy │
│   2. FORECAST   ml/model.py — Chronos T5, zero-shot, 90-day horizon  │
│   3. RECOMMEND  ml/recommender.py — dynamic safety buffer, finance   │
│   4. ENRICH     ml/supplier_risk.py · multi_branch.py · events.py    │
│   5. DRIFT      monitoring/drift_detector.py — data-quality checks  │
│   6. REPORT     reporting/report_generator.py — Arabic LLM report   │
│                                                                        │
│   Result written to job_store (Redis, or in-memory fallback)        │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
        Frontend polls /api/forecast, /api/report, /api/drift
                    and renders the full dashboard
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | FastAPI 0.111 | Async REST API, job orchestration |
| **Frontend** | React 18.3 + Vite 5.3 | Interactive dashboard UI |
| **Forecasting** | Amazon Chronos T5 | Zero-shot time-series forecasting |
| **Task Queue** | Celery 5.3 + Redis | Background pipeline execution |
| **Scheduling** | APScheduler | Recurring multi-user monitoring runs |
| **LLM Integration** | OpenRouter (GPT-4o) / Ollama | Arabic report generation, Tier-3 data cleaning |
| **PDF Generation** | ReportLab 4.x | Purchase Order PDFs with Arabic bidi/shaping |
| **Rate Limiting** | SlowAPI | Per-route request throttling |
| **Charts** | Recharts | Forecast & historical demand visualization |
| **Data Processing** | Pandas, NumPy, OpenPyXL | CSV/Excel/JSON ingestion & transformation |
| **Testing** | Pytest, HTTPX | 112 tests across 8 files |
| **Containerization** | Docker, Docker Compose | Redis + API + Celery worker orchestration |

---

## 📥 Installation

### Prerequisites

```bash
✅ Python 3.12
✅ Node.js + npm (for the frontend)
✅ pip / virtual environment
✅ Redis (optional — falls back to in-memory automatically)
✅ Docker (optional, recommended for the full stack)
```

### Option A — Docker (recommended)

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

### Option B — Local dev (no Docker)

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

> Redis and Celery are both optional in dev — `job_store` and `user_store` fall back to in-memory storage automatically, and uploads fall back to an in-process background thread if no Celery worker is detected. The full stack, including the test suite, runs without any external infrastructure.

---

## 🚀 Usage

### Web Dashboard

```bash
npm run dev   # from /frontend
```

**Access:** `http://localhost:5173` (Vite dev server)

**What you get:**
- 🏢 Business Impact dashboard (financials, suppliers, transfers, events, PO)
- 📈 90-day forecast + recommended stock table
- 📉 Historical vs. forecasted demand timeline
- 📝 Arabic business report
- ⚠️ Data-quality / drift warnings
- 🗓️ Scheduled-monitoring registration form

A complete mock dataset ships with the frontend (`DEMO_DATA` in `App.jsx`), covering 3 stores, 10 items, suppliers, transfers, and seasonal events — so the UI can be explored without a backend running at all.

### REST API

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**API Docs:** `http://localhost:8000/docs`

---

## 🩹 The 3-Tier Self-Healing Pipeline

This is the part of the system most worth understanding — it's the difference between "works on the demo file" and "works on whatever a real business actually exports from their POS system."

```
Uploaded file
     │
     ▼
┌─────────────────────┐
│ 1. fast_validator    │  Already has date/store/item/sales, parseable,
│    (instant)         │  no excessive nulls? → use as-is.
│                      │  No LLM call, no cost, no latency.
└─────────────────────┘
     │ fails
     ▼
┌─────────────────────┐
│ 2. smart_cleaner     │  Deterministic, pandas-only:
│    (fast, no LLM)    │   • fuzzy column-name matching (English + Arabic
│                      │     aliases, typo tolerance via difflib)
│                      │   • mixed-format date parsing
│                      │   • negative-sales clipping, null filling via
│                      │     rolling mean / forward-fill
└─────────────────────┘
     │ fails (column names too unusual to guess)
     ▼
┌─────────────────────┐
│ 3. Planner→Executor  │  Last resort, sandboxed:
│    →Sandbox loop     │   • Planner LLM reads a stratified sample and
│    (slow, LLM-based) │     writes a fix plan
│                      │   • Executor LLM turns that plan into pandas code
│                      │   • Code runs in a hardened subprocess sandbox
│                      │     (import allowlist, CPU/memory/time caps, no
│                      │     network, no filesystem writes)
│                      │   • Re-validated, up to 2 retries with the
│                      │     sandbox error fed back to the Executor
└─────────────────────┘
     │ fails
     ▼
   Clear, actionable error message back to the user
```

Letting an LLM write and execute arbitrary code is a real security surface, so the sandbox (`data_agent/sandbox.py`) layers several defenses: a custom import-hook allowlist, hard timeouts, memory/CPU caps, no network access, no filesystem writes, and code-size limits.

---

## 📁 Project Structure

```
.
├── backend/
│   ├── main.py                      FastAPI app, startup/shutdown, CORS, rate limiting
│   ├── worker.py                    Celery task — thin wrapper around run_full_pipeline
│   ├── docker-compose.yml           Redis + API + Celery worker
│   │
│   ├── api/
│   │   ├── routes.py                Core endpoints: upload, forecast, report, drift, PO
│   │   ├── monitor_routes.py        Scheduled-monitoring endpoints
│   │   ├── pipeline_common.py       run_full_pipeline() — the single shared orchestrator
│   │   ├── job_store.py             Redis-backed job state (+ in-memory fallback)
│   │   └── rate_limiter.py          Centralized SlowAPI limiter
│   │
│   ├── data_agent/                  The 3-tier self-healing cleaning pipeline
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
│   │   └── purchase_order.py        PDF Purchase Order generator (ReportLab)
│   │
│   └── tests/                       112 tests across 8 files (see below)
│
└── frontend/
    └── src/
        ├── App.jsx                   Top-level state, upload→poll→results, tab nav
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

## 📡 API Reference

All endpoints are under `/api`. Set `API_KEYS` in `.env` to require an `X-API-Key` header; leave it empty to disable auth (dev only — `/api/health` is always reachable).

### Core pipeline

| Method | Path | Rate limit | Description |
|---|---|---|---|
| GET | `/api/health` | — | Health check, reports auth status + store backend |
| POST | `/api/upload` | 10/min | Upload a file or Google Sheets URL → `job_id` |
| GET | `/api/forecast/{job_id}` | 60/min | Poll forecast + recommendations |
| GET | `/api/report/{job_id}` | 60/min | Poll the Arabic LLM report |
| GET | `/api/drift/{job_id}` | 60/min | Poll data-quality check results |
| POST | `/api/purchase-order` | 60/min | Generate a Purchase Order PDF from line items |
| GET | `/api/purchase-order/auto/{job_id}` | 60/min | Auto-build a PO PDF from a job's recommendations |

### Scheduled monitoring (prefix `/api/monitor`)

| Method | Path | Rate limit | Description |
|---|---|---|---|
| POST | `/register` | 20/min | Register a Google Sheet for recurring analysis |
| POST | `/register-with-file` | 20/min | Register an uploaded CSV for recurring analysis |
| GET | `/users` | 60/min | List all registered users (admin) |
| GET | `/users/{user_id}` | 60/min | Get one user's settings |
| PATCH | `/users/{user_id}` | 30/min | Update frequency / email / lead time / etc. |
| DELETE | `/users/{user_id}` | 20/min | Unregister |
| POST | `/users/{user_id}/run` | 5/min | Trigger an immediate analysis run |
| GET | `/users/{user_id}/last` | 60/min | Last completed job's results |
| GET | `/frequencies` | — | List valid frequency values |

Scheduled runs fire automatically at 06:00 UTC on the user's chosen cadence. Full interactive docs at `/docs` once the server is running.

---

## 🔧 Challenges & Solutions

### Challenge 1: One bug, three copy-pasted implementations

**Problem:** The pipeline needed to run from three different triggers — an API upload, a Celery worker, and a scheduled job — and each started as its own implementation.

**Solution:** Unified all three into a single `run_full_pipeline()` orchestrator in `api/pipeline_common.py`, called identically from `api/routes.py`'s dev fallback, `worker.py`'s production Celery task, and `monitoring_jobs/scheduler.py`'s recurring runs.

**Result:** A bug fix or new pipeline step now only needs to happen once — verified by an end-to-end test (`test_pipeline_common.py`) added specifically after a refactor briefly reintroduced the duplication problem in miniature.

---

### Challenge 2: "Clean data" is the exception, not the rule

**Problem:** Real uploaded files have Arabic/English mixed column names, inconsistent date formats, and missing values — a single rigid loader broke constantly.

**Solution:** Built the 3-tier recovery pipeline: instant validation → deterministic fuzzy cleaning (no LLM) → a sandboxed Planner/Executor LLM loop as a last resort.

**Result:** The fast, free tiers handle the large majority of "messy but recognizable" files; the expensive LLM tier only fires on genuinely unusual schemas.

---

### Challenge 3: Letting an LLM write code safely

**Problem:** The Tier-3 fallback needs an LLM to generate and run real pandas code against untrusted file content — a serious security surface if done carelessly.

**Solution:** Built a hardened subprocess sandbox (`data_agent/sandbox.py`) with a custom import-hook allowlist, hard timeouts, CPU/memory caps, no network access, and no filesystem writes — plus a validation loop that retries up to twice with the sandbox's own error fed back to the Executor LLM.

**Result:** The system can recover from almost any column-naming scheme without ever giving arbitrary LLM-generated code unrestricted access to the host.

---

### Challenge 4: Univariate forecasts miss real-world context

**Problem:** Chronos forecasts purely from historical numbers — it has no notion of Ramadan, Eid, or Black Friday, and the Hijri calendar shifts ~11 days earlier every Gregorian year, so a hardcoded date range doesn't work either.

**Solution:** Built `ml/events.py` as a dedicated enrichment layer that maps recurring demand-shifting events onto the forecast window independently of the model itself.

**Result:** Forecasts get a context-aware uplift signal without needing to retrain or fine-tune the underlying time-series model.

---

### Challenge 5: GPU dependencies bloating the Docker image

**Problem:** Default PyTorch wheels (CUDA-enabled) pushed the production Docker image toward ~45GB.

**Solution:** Split into `requirements.txt` (CPU-only torch, used in Docker/production) and `requirements-gpu.txt` (CUDA build, opt-in for local development with a GPU).

**Result:** Production image size dropped to roughly ~15GB while keeping a documented fast-inference path for local dev.

---

## 📊 Performance Metrics

### Test Suite

| Metric | Value |
|---|---|
| **Total tests** | 112 across 8 files |
| **Coverage focus** | Recommender buffer logic, 3-tier cleaning pipeline, schema detection, drift detection, alert logic, full HTTP contract, end-to-end pipeline orchestration |
| **External-dependency tests** | Intentionally excluded (live Chronos inference, live LLM calls, Celery broker wiring) — covered by manual/staging verification instead |

### Engineering Impact

| Area | Before | After |
|---|---|---|
| **Production Docker image size** | ~45GB (CUDA torch) | ~15GB (CPU torch) |
| **Pipeline duplication** | 3 copy-pasted implementations | 1 shared orchestrator |
| **Data-cleaning success rate** | Fails on any unrecognized schema | 3 fallback tiers before user intervention |
| **Report generation failure mode** | N/A | Pipeline completes even if the LLM report call fails |

---

## 🚀 Future Enhancements

- [ ] Batch Chronos inference across multiple (store, item) series instead of sequential looping
- [ ] Offline fallback mode for the LLM-dependent cleaning tier and report generator
- [ ] Split `App.jsx` (~1000 lines) into smaller, focused components, following the pattern already used in `components/business/`
- [ ] Automated frontend test suite (Vitest + React Testing Library)
- [ ] Edge/on-device deployment option for smaller retail deployments

---

## 👨‍💻 Developer

**Eng. Mahmoud Khalid Alkodousy**

- 🎓 Telecom/Communication Engineering — High Institute of Engineering and Technology, Tanta
- 💼 Generative AI & Machine Learning Engineer | LLM Applications | RAG Pipelines | Multi-Agent Systems | FastAPI | Full-Stack AI Systems

---

## 📜 License

MIT License — see `LICENSE` file

---

<div align="center">

### ⭐ Star this repo if you found it helpful! ⭐

**Built with ❤️ | Self-Healing by Design | Production Ready**

</div>
