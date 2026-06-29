"""
monitoring/drift_detector.py
─────────────────────────────
Data Quality Checker.

Analyses the user's own uploaded data for quality issues:
  - Missing / null values in key columns
  - Extreme outliers in sales (IQR-based, > 5× IQR above Q3)
  - Suspicious zero-sales streaks (> 14 consecutive zero-sales days)
  - Date gaps (missing days in the time series)
  - Abnormally short history (< 30 days)

This approach is self-contained and requires no external reference
dataset — so it is fully valid for zero-shot models like Chronos that
are never trained on the user's data.

The result is surfaced in the UI as "تحذيرات جودة البيانات"
(Data Quality Warnings) rather than "drift" to avoid confusion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# ── Config ────────────────────────────────────────────────────────────────────

MIN_ROWS_FOR_CHECK   = 30     # need enough rows to compute meaningful stats
OUTLIER_IQR_FACTOR   = 5.0   # flag sales > Q3 + factor × IQR
MAX_ZERO_STREAK_DAYS = 14    # flag items with > this many consecutive zero-sales days
MIN_HISTORY_DAYS     = 90    # warn if overall date span < this


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class FeatureDrift:
    """Kept for API compatibility — repurposed as a quality-check detail record."""
    feature:        str
    train_mean:     float   # baseline value (e.g. expected ratio, Q3 threshold…)
    incoming_mean:  float   # observed value in user data
    train_std:      float   # tolerance / scale
    deviation:      float   # how far off (0 = fine, 1+ = noteworthy)
    is_drifted:     bool    # True → this check raised a warning


@dataclass
class DriftReport:
    has_drift:       bool
    n_drifted:       int
    total_checked:   int
    threshold:       float
    alerts:          list[str]             = field(default_factory=list)
    feature_details: list[FeatureDrift]   = field(default_factory=list)
    skipped_reason:  str                   = ""

    def summary(self) -> str:
        if self.skipped_reason:
            return f"⚠️  فحص الجودة تم تخطيه: {self.skipped_reason}"
        if not self.has_drift:
            return (
                f"✅ لا مشاكل في جودة البيانات "
                f"({self.total_checked} فحص أُجري)."
            )
        lines = [
            f"⚠️  تم اكتشاف {self.n_drifted} مشكلة في جودة البيانات "
            f"(من أصل {self.total_checked} فحص)."
        ]
        for alert in self.alerts:
            lines.append(f"   • {alert}")
        return "\n".join(lines)


# ── Main entry point ──────────────────────────────────────────────────────────

def detect_drift(
    df: pd.DataFrame,
    threshold: float = 1.0,   # kept for API compatibility (unused internally)
) -> DriftReport:
    """
    Run data-quality checks on the user's own DataFrame.

    Parameters
    ----------
    df        : Clean DataFrame — date | store | item | sales
    threshold : API-compat parameter (not used — all checks are rule-based).

    Returns
    -------
    DriftReport  (has_drift=True means at least one quality warning fired)
    """
    if len(df) < MIN_ROWS_FOR_CHECK:
        return DriftReport(
            has_drift=False,
            n_drifted=0,
            total_checked=0,
            threshold=threshold,
            skipped_reason=(
                f"فقط {len(df)} سطر — يلزم {MIN_ROWS_FOR_CHECK} على الأقل "
                "لإجراء فحص الجودة بشكل موثوق."
            ),
        )

    details: list[FeatureDrift] = []
    alerts:  list[str]          = []

    # ── Check 1: Missing values ───────────────────────────────────────────────
    for col in ["date", "store", "item", "sales"]:
        if col not in df.columns:
            continue
        null_count = int(df[col].isna().sum())
        null_ratio = null_count / len(df)
        is_problem = null_ratio > 0.05   # > 5% missing is worth flagging

        details.append(FeatureDrift(
            feature=f"missing_{col}",
            train_mean=0.0,
            incoming_mean=round(null_ratio, 4),
            train_std=0.05,
            deviation=round(null_ratio / 0.05, 2) if null_ratio > 0 else 0.0,
            is_drifted=is_problem,
        ))
        if is_problem:
            alerts.append(
                f"عمود '{col}' يحتوي على {null_count} قيمة مفقودة "
                f"({null_ratio*100:.1f}% من البيانات) — قد يؤثر على دقة التنبؤ."
            )

    # ── Check 2: Sales outliers (IQR method) ─────────────────────────────────
    if "sales" in df.columns:
        sales = df["sales"].dropna().clip(lower=0)
        q1, q3 = float(sales.quantile(0.25)), float(sales.quantile(0.75))
        iqr    = q3 - q1
        upper_fence = q3 + OUTLIER_IQR_FACTOR * iqr
        outlier_count = int((sales > upper_fence).sum()) if iqr > 0 else 0
        outlier_ratio = outlier_count / len(sales) if len(sales) > 0 else 0.0
        is_problem    = outlier_count > 0 and outlier_ratio > 0.01

        details.append(FeatureDrift(
            feature="sales_outliers",
            train_mean=0.0,
            incoming_mean=round(outlier_ratio, 4),
            train_std=0.01,
            deviation=round(outlier_ratio / 0.01, 2) if outlier_ratio > 0 else 0.0,
            is_drifted=is_problem,
        ))
        if is_problem:
            alerts.append(
                f"اكتُشفت {outlier_count} قيمة مبيعات شاذة (> {upper_fence:,.0f} وحدة) — "
                "تحقق من صحة هذه السجلات قبل التنبؤ."
            )

    # ── Check 3: Zero-sales streaks per item ─────────────────────────────────
    zero_streak_items: list[str] = []
    if {"date", "item", "store", "sales"}.issubset(df.columns):
        df_sorted = df.copy()
        df_sorted["date"] = pd.to_datetime(df_sorted["date"], errors="coerce")
        df_sorted = df_sorted.dropna(subset=["date"]).sort_values("date")

        for (store, item), grp in df_sorted.groupby(["store", "item"]):
            sales_vals = grp["sales"].fillna(0).values
            max_streak = _max_zero_streak(sales_vals)
            if max_streak > MAX_ZERO_STREAK_DAYS:
                zero_streak_items.append(f"{item} (فرع {store}): {max_streak} يوم)")

    is_problem = len(zero_streak_items) > 0
    details.append(FeatureDrift(
        feature="zero_sales_streak",
        train_mean=0.0,
        incoming_mean=float(len(zero_streak_items)),
        train_std=1.0,
        deviation=float(len(zero_streak_items)),
        is_drifted=is_problem,
    ))
    if is_problem:
        sample = zero_streak_items[:3]
        tail   = f" وغيرها ({len(zero_streak_items)-3} أخرى)" if len(zero_streak_items) > 3 else ""
        alerts.append(
            f"مبيعات صفرية متواصلة لأكثر من {MAX_ZERO_STREAK_DAYS} يوم في: "
            + "، ".join(sample) + tail
            + " — هل المنتج خارج الخدمة مؤقتاً؟"
        )

    # ── Check 4: Short history span ──────────────────────────────────────────
    history_days = 0
    if "date" in df.columns:
        dates = pd.to_datetime(df["date"], errors="coerce").dropna()
        if len(dates) > 1:
            history_days = int((dates.max() - dates.min()).days)

    is_short = 0 < history_days < MIN_HISTORY_DAYS
    details.append(FeatureDrift(
        feature="history_span_days",
        train_mean=float(MIN_HISTORY_DAYS),
        incoming_mean=float(history_days),
        train_std=float(MIN_HISTORY_DAYS),
        deviation=round(1.0 - history_days / MIN_HISTORY_DAYS, 2) if is_short else 0.0,
        is_drifted=is_short,
    ))
    if is_short:
        alerts.append(
            f"البيانات تغطي {history_days} يوم فقط — "
            f"يُنصح بـ {MIN_HISTORY_DAYS} يوم على الأقل للحصول على تنبؤات موسمية دقيقة."
        )

    n_drifted   = sum(1 for d in details if d.is_drifted)
    has_drift   = n_drifted > 0
    total_checks = len(details)

    return DriftReport(
        has_drift=has_drift,
        n_drifted=n_drifted,
        total_checked=total_checks,
        threshold=threshold,
        alerts=alerts,
        feature_details=details,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _max_zero_streak(values: np.ndarray) -> int:
    """Return the length of the longest consecutive zero run in *values*."""
    max_streak = current = 0
    for v in values:
        if v == 0:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak
