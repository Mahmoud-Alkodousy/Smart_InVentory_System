# Smart Inventory Manager — Frontend

React + Vite single-page app for the Smart Inventory Manager. Upload sales
data, watch the pipeline run through its steps live, then explore the
forecast, financial impact, supplier risk, multi-branch transfers, and the
Arabic LLM report — all in one dashboard.

## Setup

```bash
npm install
cp .env.example .env   # set VITE_API_URL to your backend, e.g. http://localhost:8000
npm run dev
```

## Build

```bash
npm run build      # outputs to dist/
npm run preview    # preview the production build locally
```

### Docker

```bash
docker build --build-arg VITE_API_URL=https://your-api.example.com -t sim-frontend .
docker run -p 8080:80 sim-frontend
```

`VITE_API_URL` is baked in at **build time** (Vite convention — env vars
aren't available at container runtime for a static SPA), so it's passed as
a Docker build arg rather than a runtime environment variable. See the
`Dockerfile`'s multi-stage build.

## Structure

```
src/
  App.jsx                    Top-level state, upload→poll→results flow, tab navigation
  components/
    FileUpload.jsx           Upload form (file or Google Sheets URL)
    ForecastDashboard.jsx    Core forecast + recommendations table
    ForecastTimeline.jsx     Historical + forecasted demand chart
    InventoryReport.jsx      Renders the Arabic LLM-generated report
    DriftAlert.jsx           Data-quality warnings panel
    MonitoringSetup.jsx      Scheduled-monitoring registration form
    PipelineDiagram.jsx      Live pipeline-step visualization while processing
    BusinessDashboard.jsx    Business Impact Layer container (tabs below)
    business/
      EventsImpactPanel.jsx     Upcoming events (Ramadan, Eid, Black Friday...)
      MultiBranchPanel.jsx      Inter-branch stock transfer suggestions
      PurchaseOrderPanel.jsx    Generate/download Purchase Order PDFs
      SupplierRiskPanel.jsx     Supplier lead-time risk analysis
      shared.jsx                Shared UI primitives for the business/ panels
```

### Dashboard tabs (set via `activeTab` in `App.jsx`)

| Tab        | Component             | Shows                                              |
|------------|------------------------|------------------------------------------------------|
| `business` | `BusinessDashboard`    | Financial impact, suppliers, transfers, events, PO   |
| `forecast` | `ForecastDashboard`    | Per-item 90-day forecast + recommended stock table   |
| `timeline` | `ForecastTimeline`     | Historical vs. forecasted demand chart               |
| `report`   | `InventoryReport`      | The Arabic LLM-generated business report             |
| `drift`    | `DriftAlert`           | Data-quality warnings (nulls, outliers, gaps)         |

### Demo Mode

`App.jsx` ships with a complete mock dataset (`DEMO_DATA`) covering 3
stores, 10 items, suppliers, transfers, and seasonal events — useful for
exploring the UI or giving a demo without a backend running.

## Environment variables

| Variable        | Purpose                                          |
|------------------|---------------------------------------------------|
| `VITE_API_URL`   | Backend base URL (empty = same-origin)            |
| `VITE_API_KEY`   | Sent as `X-API-Key` header if backend auth is enabled |

## Known limitations

- `App.jsx` is large (~1000 lines) and owns most of the top-level state
  (job polling, tab state, theme, elapsed time) in one component. The
  `business/` subfolder shows the intended pattern (small, focused
  components) — `App.jsx` itself is the next candidate for that kind of
  split, most naturally around the upload/poll state machine vs. the
  tab-navigation chrome.
- No automated frontend tests yet (see the backend's `tests/` for the
  testing approach used there; a similar setup with Vitest + React Testing
  Library would be the natural next step here).
