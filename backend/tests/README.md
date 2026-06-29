# Tests

Unit and integration tests for the Smart Inventory Manager backend.

## Setup

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Running

```bash
# Run everything
pytest

# Run one file
pytest tests/test_recommender.py -v

# Run with coverage
pytest --cov=. --cov-report=term-missing
```

## What's covered

| File                          | Module under test                  | Focus                                                              |
|--------------------------------|-------------------------------------|---------------------------------------------------------------------|
| `test_recommender.py`          | `ml/recommender.py`                 | CV→buffer tiers, financial fields, per-(store,item) stock, seasonal warning |
| `test_fast_validator.py`       | `data_agent/fast_validator.py`      | Fast-path validation pass/fail conditions                          |
| `test_smart_cleaner.py`        | `data_agent/smart_cleaner.py`       | Fuzzy column mapping, deterministic cleaning (no LLM calls made)   |
| `test_schema.py`               | `data_agent/schema.py`              | Optional business-column alias detection                           |
| `test_drift_detector.py`       | `monitoring/drift_detector.py`      | Missing values, outliers, zero-streaks, short-history checks       |
| `test_alert_checker.py`        | `monitoring_jobs/alert_checker.py`  | Low-stock / seasonal alert decision logic                          |
| `test_pipeline_common.py`      | `api/pipeline_common.py`            | **End-to-end** `run_full_pipeline()` run, only Chronos/LLM mocked  |
| `test_api_routes.py`           | `api/routes.py`, `api/monitor_routes.py` | HTTP contract: validation, status codes, auth gating          |

## What's intentionally NOT covered

- **Chronos forecasting itself** (`ml/model.py`'s `forecast()`) — requires downloading
  real model weights and running inference, which is slow and network-dependent. Not a
  unit-test concern; if you need to verify it works, run the app end-to-end with a real
  upload instead.
- **The LLM column-mapping fallback** in `smart_cleaner.py` and **the report generator**
  in `reporting/report_generator.py` — both call out to OpenRouter/Ollama. These are
  exercised manually / in staging, not in the automated suite, to avoid flaky tests that
  depend on external API availability and to avoid burning API credits on every CI run.
- **Celery task dispatch** — `worker.py`'s `run_pipeline_task` is a thin wrapper around
  `api.pipeline_common.run_full_pipeline` (which IS tested indirectly through the API
  tests' background-thread fallback path); the Celery wiring itself needs a running
  broker to test meaningfully and is better covered by an end-to-end smoke test in CI.

## Notes

- **Why `test_pipeline_common.py` exists separately from the unit tests**: the
  unit tests above call `recommend()`, `detect_drift()`, etc. directly, and
  `test_api_routes.py` only checks the immediate HTTP response without
  waiting for the background job to finish. Neither catches a bug *inside*
  `run_full_pipeline()`'s orchestration itself (wrong call order, a typo'd
  function name, a step that got deleted in a refactor). `test_pipeline_common.py`
  runs the real orchestrator end-to-end with only Chronos/the LLM report call
  mocked, so every other line — including `build_pipeline_extras`,
  `extract_optional_signals`, `build_timeseries_payload`, `detect_drift`, and
  `job_store.complete` — actually executes. This is the test that would have
  (and, after being added, did) catch a `NameError` from a missing function.
- Tests run against in-memory fallbacks for both `job_store` and `user_store` — no Redis
  required. `main.py` already falls back to these automatically when `REDIS_URL` is
  unreachable, which is what makes these tests possible without spinning up infrastructure.
- `tests/test_api_routes.py` triggers `api.pipeline_common.run_full_pipeline` on a
  background thread for upload tests. Since Chronos isn't installed in a typical test
  environment, you'll see a `ModuleNotFoundError: No module named 'chronos'` traceback
  printed to stderr — that's expected and harmless (it's caught internally and recorded
  as a failed job); it does not affect any test assertion.
