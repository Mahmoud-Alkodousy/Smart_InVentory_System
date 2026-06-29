"""
data_agent/agent_pipeline.py
─────────────────────────────
Orchestrates the full data ingestion pipeline:

  Load → SmartCleaner (pandas-only) → [LLM fallback if needed] → Return clean DataFrame

Pipeline priority:
  1. Fast path:   fast_validator passes             → direct (no cleaning needed)
  2. Smart path:  smart_cleaner fixes it            → cleaned (pandas-only, fast)
  3. LLM path:    smart_cleaner fails + LLM enabled → agent_fixed (slow, optional)
  4. Fail:        everything fails                  → error with clear message
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Optional, Union
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    success: bool
    df: Optional[pd.DataFrame] = None

    route: str = ""    # "direct" | "smart_cleaned" | "agent_fixed" | "failed"

    n_rows: int = 0
    n_stores: int = 0
    n_items: int = 0
    date_min: str = ""
    date_max: str = ""

    fix_plan: str = ""
    attempts_used: int = 0
    agent_warnings: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    error: str = ""
    attempt_errors: list = field(default_factory=list)

    def summary(self) -> str:
        lines = []
        if self.success:
            lines.append(f"✅ Pipeline succeeded  — route: {self.route}")
            lines.append(f"   Rows    : {self.n_rows:,}")
            lines.append(f"   Stores  : {self.n_stores}")
            lines.append(f"   Items   : {self.n_items}")
            lines.append(f"   Dates   : {self.date_min} → {self.date_max}")
            if self.route == "agent_fixed":
                lines.append(f"   Attempts: {self.attempts_used}")
            for w in self.warnings:
                lines.append(f"   ⚠  {w}")
        else:
            lines.append(f"❌ Pipeline failed  — route: {self.route}")
            lines.append(f"   {self.error}")
            for e in self.attempt_errors:
                lines.append(f"   • {e}")
        return "\n".join(lines)


# ── Main entry point ──────────────────────────────────────────────────────────

def run_pipeline(
    source: Union[bytes, str, Path],
    filename: str = "",
    mime_type: str = "",
    on_step=None,       # optional callback: on_step(step_key: str)
) -> PipelineResult:

    # ── 1. Load ───────────────────────────────────────────────────────────────
    df_raw, load_error = _load(source, filename, mime_type)
    if df_raw is None:
        return PipelineResult(success=False, route="failed", error=load_error)

    # ── 2. Fast Validator — data already clean? ───────────────────────────────
    from data_agent.fast_validator import validate

    val = validate(df_raw)
    if val.passed:
        df_clean = _normalise_columns(df_raw)
        logger.info("Pipeline: direct route (no cleaning needed)")
        return PipelineResult(
            success=True,
            df=df_clean,
            route="direct",
            n_rows=val.n_rows,
            n_stores=val.n_stores,
            n_items=val.n_items,
            date_min=val.date_min or "",
            date_max=val.date_max or "",
            warnings=val.warnings,
        )

    # ── 3. Smart Cleaner — pandas-only, fast, no LLM ─────────────────────────
    if on_step: on_step("clean")
    from data_agent.smart_cleaner import clean as smart_clean

    try:
        df_clean, clean_warnings = smart_clean(df_raw)
        logger.info("Pipeline: smart_cleaned route (%d warnings)", len(clean_warnings))

        return PipelineResult(
            success=True,
            df=df_clean,
            route="smart_cleaned",
            n_rows=len(df_clean),
            n_stores=df_clean["store"].nunique(),
            n_items=df_clean["item"].nunique(),
            date_min=str(df_clean["date"].min().date()),
            date_max=str(df_clean["date"].max().date()),
            warnings=clean_warnings,
        )

    except ValueError as clean_err:
        logger.warning("SmartCleaner failed: %s — trying LLM fallback", clean_err)
        smart_clean_error = str(clean_err)

    # ── 4. LLM Fallback — only if smart_cleaner couldn't fix it ──────────────
    from data_agent.planner import create_fix_plan, PlannerError
    from data_agent.sampler import build_sample_payload

    try:
        sample_payload = build_sample_payload(df_raw)
        plan = create_fix_plan(sample_payload)
    except PlannerError as exc:
        # LLM also failed — return the smart_cleaner error (more useful)
        return PipelineResult(
            success=False,
            route="failed",
            error=(
                f"تعذّر تنظيف البيانات تلقائياً: {smart_clean_error}. "
                f"وفشل LLM أيضاً: {exc}"
            ),
        )

    from data_agent.validation_loop import run_validation_loop

    _buf = io.StringIO()
    df_raw.to_csv(_buf, index=False, encoding="utf-8")
    loop = run_validation_loop(plan=plan, input_csv=_buf.getvalue())

    if not loop.success:
        return PipelineResult(
            success=False,
            route="failed",
            error=loop.failure_reason,
            attempt_errors=loop.attempt_errors,
            fix_plan=plan,
        )

    df_clean = loop.df
    val2 = loop.validation
    logger.info("Pipeline: agent_fixed route (%d attempts)", loop.attempts_used)

    return PipelineResult(
        success=True,
        df=df_clean,
        route="agent_fixed",
        n_rows=val2.n_rows if val2 else len(df_clean),
        n_stores=val2.n_stores if val2 else df_clean["store"].nunique(),
        n_items=val2.n_items if val2 else df_clean["item"].nunique(),
        date_min=val2.date_min or "" if val2 else "",
        date_max=val2.date_max or "" if val2 else "",
        fix_plan=plan,
        attempts_used=loop.attempts_used,
        agent_warnings=loop.attempt_errors,
        warnings=val2.warnings if val2 else [],
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load(
    source: Union[bytes, str, Path],
    filename: str,
    mime_type: str,
) -> tuple[Optional[pd.DataFrame], str]:
    if isinstance(source, str) and source.startswith("http"):
        from data_loader.sheets_loader import load_google_sheet, SheetsLoadError, SheetsURLError
        try:
            return load_google_sheet(source), ""
        except (SheetsLoadError, SheetsURLError) as exc:
            return None, str(exc)

    from data_loader.loader import load_file, LoadError, UnsupportedFormatError
    try:
        return load_file(source, filename=filename, mime_type=mime_type), ""
    except (LoadError, UnsupportedFormatError) as exc:
        return None, str(exc)


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    from data_agent.schema import REQUIRED_COLUMNS, attach_optional_columns

    df_original = df.copy()
    df_original.columns = [c.strip().lower() for c in df_original.columns]

    df = df_original.copy()
    df["date"]  = pd.to_datetime(df["date"], format="mixed", dayfirst=False)
    df["sales"] = pd.to_numeric(df["sales"], errors="coerce").clip(lower=0)
    df_required = df[REQUIRED_COLUMNS]

    # Preserve recognised business columns (unit_price, current_stock,
    # supplier, supplier_lead_time_days, ...) instead of silently dropping
    # them — see data_agent/schema.py for why this matters.
    df_full, _added = attach_optional_columns(
        df_required, df_original, consumed_original_names=set(REQUIRED_COLUMNS)
    )
    return df_full
