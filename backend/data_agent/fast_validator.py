"""
data_agent/fast_validator.py
─────────────────────────────
Pure-Python validation — zero LLM calls.
Runs first on every upload to decide:
  - PASS  → data is clean, send directly to Feature Engineering
  - FAIL  → data needs fixing, send to Data Fixer Agent

Required columns (canonical names):
  date  |  store  |  item  |  sales

All checks are collected before returning so the caller
gets a complete picture in one shot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


# ── Constants ─────────────────────────────────────────────────────────────────

REQUIRED_COLUMNS: list[str] = ["date", "store", "item", "sales"]

MIN_ROWS = 2          # Need at least 2 rows for lag features to make sense
MAX_NULL_PCT = 0.0    # Zero nulls required (strict); adjust if you want tolerance


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Populated only when passed=True
    n_rows: int = 0
    n_stores: int = 0
    n_items: int = 0
    date_min: Optional[str] = None
    date_max: Optional[str] = None

    def summary(self) -> str:
        lines = []
        if self.passed:
            lines.append("✅ Validation PASSED")
            lines.append(f"   Rows     : {self.n_rows:,}")
            lines.append(f"   Stores   : {self.n_stores}")
            lines.append(f"   Items    : {self.n_items}")
            lines.append(f"   Date range: {self.date_min} → {self.date_max}")
        else:
            lines.append("❌ Validation FAILED")
            for err in self.errors:
                lines.append(f"   ERROR   : {err}")
        for w in self.warnings:
            lines.append(f"   WARNING : {w}")
        return "\n".join(lines)


# ── Main validator ────────────────────────────────────────────────────────────

def validate(df: pd.DataFrame) -> ValidationResult:
    """
    Run all checks on *df* and return a ValidationResult.

    Parameters
    ----------
    df : Raw DataFrame straight from the loader (column names not yet fixed).

    Returns
    -------
    ValidationResult
        .passed  = True  → send to Feature Engineering
        .passed  = False → send to Data Fixer Agent
    """
    errors: list[str] = []
    warnings: list[str] = []

    # ── 1. Minimum row count ──────────────────────────────────────────────────
    if len(df) < MIN_ROWS:
        errors.append(
            f"File has only {len(df)} row(s). Minimum required: {MIN_ROWS}."
        )
        return ValidationResult(passed=False, errors=errors, warnings=warnings)

    # ── 2. Required columns present ──────────────────────────────────────────
    actual_cols = [c.strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in actual_cols]

    if missing:
        errors.append(
            f"Missing required column(s): {missing}. "
            f"Found columns: {list(df.columns)}"
        )
        # No point running further checks — column names are wrong
        return ValidationResult(passed=False, errors=errors, warnings=warnings)

    # Normalise column names for the remaining checks
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]

    # ── 3. Date column is parseable ───────────────────────────────────────────
    try:
        df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=False)
    except Exception as exc:
        errors.append(
            f"'date' column could not be parsed as datetime: {exc}"
        )

    # ── 4. Sales column is numeric ────────────────────────────────────────────
    if not pd.api.types.is_numeric_dtype(df["sales"]):
        try:
            df["sales"] = pd.to_numeric(df["sales"], errors="raise")
        except Exception:
            errors.append(
                "'sales' column is not numeric. "
                f"Sample values: {df['sales'].head(5).tolist()}"
            )

    # ── 5. Sales values are non-negative ─────────────────────────────────────
    if pd.api.types.is_numeric_dtype(df["sales"]):
        n_negative = (df["sales"] < 0).sum()
        if n_negative > 0:
            errors.append(
                f"'sales' column contains {n_negative:,} negative value(s). "
                "All sales must be >= 0."
            )

    # ── 6. Null counts ────────────────────────────────────────────────────────
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            continue  # already caught above
        null_count = df[col].isna().sum()
        null_pct   = null_count / len(df)
        if null_pct > MAX_NULL_PCT:
            errors.append(
                f"Column '{col}' has {null_count:,} null value(s) "
                f"({null_pct*100:.1f}%). Must be 0."
            )

    # ── 7. Extra-column warnings (non-blocking) ───────────────────────────────
    from data_agent.schema import map_optional_columns

    extra_cols = [c for c in df.columns if c not in REQUIRED_COLUMNS]
    if extra_cols:
        recognised_map = map_optional_columns(extra_cols)
        recognised  = list(recognised_map.keys())
        unrecognised = [c for c in extra_cols if c not in recognised]
        if recognised:
            warnings.append(
                f"تم التعرف على أعمدة إضافية مفيدة وسيتم استخدامها "
                f"(سعر/مخزون/مورد/مدة توريد): {recognised}"
            )
        if unrecognised:
            warnings.append(
                f"عمود/أعمدة إضافية غير معروفة وسيتم تجاهلها: {unrecognised}"
            )

    # ── 8. Duplicate rows warning ─────────────────────────────────────────────
    n_dupes = df.duplicated(subset=["date", "store", "item"]).sum()
    if n_dupes > 0:
        warnings.append(
            f"{n_dupes:,} duplicate (date, store, item) combination(s) found. "
            "Consider aggregating before uploading."
        )

    # ── Final decision ────────────────────────────────────────────────────────
    if errors:
        return ValidationResult(passed=False, errors=errors, warnings=warnings)

    # All checks passed — populate summary stats
    return ValidationResult(
        passed=True,
        errors=[],
        warnings=warnings,
        n_rows=len(df),
        n_stores=df["store"].nunique(),
        n_items=df["item"].nunique(),
        date_min=str(df["date"].min().date()),
        date_max=str(df["date"].max().date()),
    )
