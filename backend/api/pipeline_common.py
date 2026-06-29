"""
api/pipeline_common.py
─────────────────────────
Shared pipeline logic used by ALL THREE execution paths:
  - api/routes.py:_run_pipeline_fallback   (dev mode, no Celery)
  - worker.py:run_pipeline_task            (production, Celery)
  - monitoring_jobs/scheduler.py           (scheduled per-user runs)

run_full_pipeline() is the single source of truth for pipeline
orchestration (load → clean → forecast → recommend → drift → report).
It used to be copy-pasted across all three call sites, which meant a
fix in one place silently didn't apply to the other two.

extract_optional_signals / build_pipeline_extras are lower-level
helpers used by run_full_pipeline (and kept importable separately for
any caller that needs just one piece).
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def extract_optional_signals(df: pd.DataFrame) -> dict:
    """
    Pull the per-item business-enrichment maps out of the cleaned
    DataFrame, if the relevant optional columns survived cleaning (see
    data_agent/schema.py — they're preserved by canonical name, so we
    only ever need to check for the canonical column here, not aliases).

    Returns a dict with keys: item_prices, current_stocks, supplier_map,
    supplier_lead_time_map. Any key whose source column wasn't present
    (or was entirely null) is None.

    current_stocks is keyed by (store, item) — NOT item alone. The same
    item can legitimately carry different stock levels at different
    branches; collapsing to item-only would silently average/overwrite
    per-branch stock and break both the savings calculation and the
    Multi-Branch transfer suggestions for any multi-store dataset.
    unit_price and supplier are kept item-level, since a product's price
    and its supplier don't normally vary by branch.
    """
    item_prices = (
        df.groupby("item")["unit_price"].mean().to_dict()
        if "unit_price" in df.columns and df["unit_price"].notna().any()
        else None
    )
    current_stocks = (
        df.groupby(["store", "item"])["current_stock"].last().to_dict()
        if "current_stock" in df.columns and df["current_stock"].notna().any()
        else None
    )
    supplier_map = (
        df.dropna(subset=["supplier"]).groupby("item")["supplier"].last().to_dict()
        if "supplier" in df.columns and df["supplier"].notna().any()
        else None
    )
    supplier_lead_time_map = (
        df.groupby("item")["supplier_lead_time_days"].mean().to_dict()
        if "supplier_lead_time_days" in df.columns and df["supplier_lead_time_days"].notna().any()
        else None
    )
    return {
        "item_prices":             item_prices,
        "current_stocks":          current_stocks,
        "supplier_map":            supplier_map,
        "supplier_lead_time_map":  supplier_lead_time_map,
    }


def build_pipeline_extras(df: pd.DataFrame, recs_list: list[dict]) -> dict:
    """
    Compute the three new Business Impact Layer artefacts:
      suppliers / supplier_switches — Supplier Risk Analysis
      transfers                     — Multi-Branch Optimization
      events                        — upcoming External Events (calendar)

    Each is computed defensively: if the underlying optional data isn't
    present (or anything goes wrong), the corresponding list is simply
    empty rather than failing the whole job — these are enrichments on
    top of the core forecast/recommendation, not load-bearing for it.
    """
    suppliers: list[dict]         = []
    supplier_switches: list[dict] = []
    transfers: list[dict]         = []
    events_list: list[dict]       = []

    try:
        from ml.supplier_risk import analyze_suppliers, suggest_supplier_switches
        suppliers          = [s.to_dict() for s in analyze_suppliers(df, recs_list)]
        supplier_switches  = [s.to_dict() for s in suggest_supplier_switches(df)]
    except Exception:
        logger.exception("Supplier risk analysis failed — continuing without it.")

    try:
        from ml.multi_branch import suggest_transfers
        transfers = [t.to_dict() for t in suggest_transfers(recs_list)]
    except Exception:
        logger.exception("Multi-branch transfer analysis failed — continuing without it.")

    try:
        from ml.events import upcoming_events
        if "date" in df.columns and len(df):
            reference_date = pd.Timestamp(df["date"].max()).date()
            events_list = upcoming_events(reference_date)
    except Exception:
        logger.exception("Events lookup failed — continuing without it.")

    return {
        "suppliers":          suppliers,
        "supplier_switches":  supplier_switches,
        "transfers":          transfers,
        "events":             events_list,
    }


def build_chronos_sample_context(
    history_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    max_pairs: int = 3,
    history_rows: int = 10,
    forecast_rows: int = 7,
) -> str:
    """
    Build a compact textual snapshot of real input data + Chronos output
    to inject into the LLM report prompt.  This lets the model ground its
    analysis in concrete numbers (actual historical sales and the day-by-day
    forecast values) rather than relying solely on the pre-aggregated
    recommendation fields.

    Parameters
    ----------
    history_df    : Clean historical DataFrame (date | store | item | sales).
    forecast_df   : Output of ml.model.forecast() with pred_sales / low / high.
    max_pairs     : How many (store, item) pairs to sample (default 3 — enough
                    context without overloading the prompt).
    history_rows  : Last N historical rows to include per pair.
    forecast_rows : First N forecast rows to include per pair (shows the
                    near-term daily prediction the model produced).

    Returns
    -------
    A UTF-8 string ready to paste into the LLM user message as
    "Chronos Forecast Sample".  Returns an empty string if either
    DataFrame is empty or doesn't have the expected columns.
    """
    try:
        required_hist = {"date", "store", "item", "sales"}
        required_fc   = {"date", "store", "item", "pred_sales"}
        if not required_hist.issubset(history_df.columns) or not required_fc.issubset(forecast_df.columns):
            return ""
        if history_df.empty or forecast_df.empty:
            return ""

        pairs = (
            forecast_df[["store", "item"]]
            .drop_duplicates()
            .head(max_pairs)
            .values.tolist()
        )
        if not pairs:
            return ""

        has_low  = "pred_sales_low"  in forecast_df.columns
        has_high = "pred_sales_high" in forecast_df.columns

        sections: list[str] = []

        for store, item in pairs:
            hist_mask = (history_df["store"] == store) & (history_df["item"] == item)
            fc_mask   = (forecast_df["store"] == store) & (forecast_df["item"] == item)

            hist_slice = (
                history_df[hist_mask]
                .sort_values("date")
                .tail(history_rows)[["date", "sales"]]
            )
            fc_slice = (
                forecast_df[fc_mask]
                .sort_values("date")
                .head(forecast_rows)
            )

            # ── Historical block ───────────────────────────────────────────
            hist_lines = ["  date        | sales"]
            hist_lines.append("  ------------|------")
            for _, row in hist_slice.iterrows():
                d = str(row["date"])[:10]
                s = f"{row['sales']:.1f}"
                hist_lines.append(f"  {d} | {s}")

            # ── Forecast block (median + optionals) ────────────────────────
            if has_low and has_high:
                fc_lines = ["  date        | pred_sales (median) | low (p10) | high (p90)"]
                fc_lines.append("  ------------|---------------------|-----------|------------")
                for _, row in fc_slice.iterrows():
                    d  = str(row["date"])[:10]
                    m  = f"{row['pred_sales']:.2f}"
                    lo = f"{row['pred_sales_low']:.2f}"
                    hi = f"{row['pred_sales_high']:.2f}"
                    fc_lines.append(f"  {d} | {m:>19} | {lo:>9} | {hi}")
            else:
                fc_lines = ["  date        | pred_sales"]
                fc_lines.append("  ------------|----------")
                for _, row in fc_slice.iterrows():
                    d = str(row["date"])[:10]
                    m = f"{row['pred_sales']:.2f}"
                    fc_lines.append(f"  {d} | {m}")

            block = (
                f"[Store={store} | Item={item}]\n"
                f"  Historical (last {len(hist_slice)} days):\n"
                + "\n".join(hist_lines)
                + f"\n\n  Chronos Forecast (next {len(fc_slice)} days):\n"
                + "\n".join(fc_lines)
            )
            sections.append(block)

        return (
            "=== Chronos Forecast Sample ===\n"
            f"(Showing {len(pairs)} of the available store×item pairs. "
            "Use these numbers to ground your analysis — e.g. if the forecast "
            "shows a rising trend in the first 7 days, mention it.)\n\n"
            + "\n\n".join(sections)
        )

    except Exception:
        # Never crash the pipeline over a best-effort enrichment
        logger.warning("build_chronos_sample_context failed — skipping.", exc_info=True)
        return ""


def run_full_pipeline(
    job_id:          str,
    source,
    filename:        str = "",
    mime_type:       str = "",
    lead_time_days:  int = 7,
    extra_context:   str = "",
    unit_price:      Optional[float] = None,
) -> bool:
    """
    Runs the complete pipeline (load → clean → forecast → recommend →
    drift → report) for one job and writes the result into job_store.

    This is the SINGLE source of truth for pipeline orchestration. It
    used to be copy-pasted three times — api/routes.py's in-process
    fallback, worker.py's Celery task, and monitoring_jobs/scheduler.py's
    scheduled-user runner — which meant a fix in one place silently
    didn't apply to the other two. All three now call this function.

    Returns True on success, False on failure (job_store is updated
    with the failure/success state either way — callers don't need to
    inspect the return value unless they want to skip post-processing
    like alert emails on failure).
    """
    from api.job_store import (
        job_store,
        STEP_LOAD, STEP_VALIDATE, STEP_FORECAST,
        STEP_RECOMMEND, STEP_DRIFT, STEP_REPORT,
    )

    def _step(key: str) -> None:
        job_store.update_step(job_id, key)

    try:
        _step(STEP_LOAD)
        from data_agent.agent_pipeline import run_pipeline
        pipeline_result = run_pipeline(
            source, filename=filename, mime_type=mime_type,
            on_step=lambda step: job_store.update_step(job_id, step),
        )

        if not pipeline_result.success:
            job_store.fail(
                job_id,
                error=pipeline_result.error,
                attempt_errors=pipeline_result.attempt_errors,
            )
            return False

        df = pipeline_result.df

        _step(STEP_VALIDATE)
        _step(STEP_FORECAST)
        from ml.model import forecast
        forecast_df = forecast(df)

        _step(STEP_RECOMMEND)
        from ml.recommender import recommend

        signals = extract_optional_signals(df)
        recs = recommend(
            history_df=df, forecast_df=forecast_df,
            lead_time_days=lead_time_days, unit_price=unit_price,
            item_prices=signals["item_prices"],
            current_stocks=signals["current_stocks"],
            supplier_map=signals["supplier_map"],
            supplier_lead_time_map=signals["supplier_lead_time_map"],
        )
        recs_list = [r.to_dict() for r in recs]
        extras    = build_pipeline_extras(df, recs_list)

        from ml.timeseries import build_timeseries_payload
        timeseries = build_timeseries_payload(
            history_df=df, forecast_df=forecast_df, recs_list=recs_list,
        )

        _step(STEP_DRIFT)
        from monitoring.drift_detector import detect_drift
        drift = detect_drift(df)
        drift_data = {
            "has_drift":      drift.has_drift,
            "n_drifted":      drift.n_drifted,
            "total_checked":  drift.total_checked,
            "alerts":         drift.alerts,
            "summary":        drift.summary(),
            "skipped_reason": drift.skipped_reason,
            "feature_details": [
                {
                    "feature":       fd.feature,
                    "train_mean":    fd.train_mean,
                    "incoming_mean": fd.incoming_mean,
                    "train_std":     fd.train_std,
                    "deviation":     fd.deviation,
                    "is_drifted":    fd.is_drifted,
                }
                for fd in drift.feature_details
            ],
        }

        # ── Build Chronos sample context for the report LLM ───────────────
        chronos_sample = build_chronos_sample_context(df, forecast_df)
        full_extra_context = "\n\n".join(
            part for part in [extra_context, chronos_sample] if part
        )

        _step(STEP_REPORT)
        from reporting.report_generator import generate_report, ReportGeneratorError
        try:
            report_text = generate_report(
                recommendations=recs,
                drift_report=drift,
                extra_context=full_extra_context,
            )
        except ReportGeneratorError as exc:
            logger.error("Report generation failed for job %s: %s", job_id, exc)
            report_text = "تعذّر توليد التقرير التلقائي. يرجى مراجعة بيانات التوصيات مباشرةً."

        job_store.complete(
            job_id,
            route=pipeline_result.route,
            n_rows=pipeline_result.n_rows,
            n_stores=pipeline_result.n_stores,
            n_items=pipeline_result.n_items,
            date_min=pipeline_result.date_min,
            date_max=pipeline_result.date_max,
            recommendations=recs_list,
            warnings=pipeline_result.warnings,
            drift=drift_data,
            report=report_text,
            timeseries=timeseries,
            suppliers=extras["suppliers"],
            supplier_switches=extras["supplier_switches"],
            transfers=extras["transfers"],
            events=extras["events"],
        )
        return True

    except Exception as exc:
        import traceback
        traceback.print_exc()
        job_store.fail(job_id, error=str(exc).strip()[:400])
        return False
