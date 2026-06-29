"""
monitoring_jobs/alert_checker.py
──────────────────────────────────
After the pipeline finishes, checks every ItemRecommendation and decides
whether to send a low-stock email alert (see monitoring_jobs/notifier.py).

Alert conditions (any one triggers a notification):
  1. avg_daily_demand * lead_time_days  >  recommended_stock * STOCK_RATIO_THRESHOLD
     → current pace will exhaust safe stock before the next order arrives
  2. seasonal_warning is True
     → a seasonal peak is approaching (already flagged by the recommender)

The thresholds are intentionally conservative to avoid alert fatigue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Trigger alert when reorder_point exceeds this fraction of recommended_stock.
# 0.80 = alert if you'd need to order before you have 80 % of the safe stock left.
STOCK_RATIO_THRESHOLD = 0.80


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class AlertResult:
    should_notify:    bool
    low_stock_alerts: list[dict]   # items that need reordering
    seasonal_alerts:  list[dict]   # items with upcoming seasonal spikes
    summary:          str          # human-readable Arabic summary for logging


# ── Main function ─────────────────────────────────────────────────────────────

def check_alerts(
    recommendations: list[dict],
    lead_time_days:  int = 7,
) -> AlertResult:
    """
    `recommendations` is a list of ItemRecommendation.to_dict() dicts
    (as stored in job_store / returned by /api/forecast).
    """
    low_stock:  list[dict] = []
    seasonal:   list[dict] = []

    for rec in recommendations:
        item           = rec.get("item", "?")
        store          = rec.get("store", "?")
        reorder_point  = float(rec.get("reorder_point", 0))
        rec_stock      = float(rec.get("recommended_stock", 0))
        avg_daily      = float(rec.get("avg_daily_demand", 0))
        seasonal_warn  = rec.get("seasonal_warning", False)
        warn_msg       = rec.get("warning_message", "")

        # Condition 1 — reorder urgency
        if rec_stock > 0 and reorder_point > rec_stock * STOCK_RATIO_THRESHOLD:
            low_stock.append({
                "item":          item,
                "store":         store,
                "reorder_point": reorder_point,
                "rec_stock":     rec_stock,
                "avg_daily":     avg_daily,
            })

        # Condition 2 — seasonal warning
        if seasonal_warn:
            seasonal.append({
                "item":    item,
                "store":   store,
                "message": warn_msg,
            })

    should_notify = bool(low_stock or seasonal)

    # Build Arabic summary for logging
    parts = []
    if low_stock:
        parts.append(f"{len(low_stock)} منتج يحتاج إعادة طلب")
    if seasonal:
        parts.append(f"{len(seasonal)} منتج بتحذير موسمي")
    summary = "تنبيهات: " + " + ".join(parts) if parts else "لا توجد تنبيهات"

    logger.info("AlertChecker: %s", summary)
    return AlertResult(
        should_notify=should_notify,
        low_stock_alerts=low_stock,
        seasonal_alerts=seasonal,
        summary=summary,
    )


def build_alert_payload(result: AlertResult) -> Optional[list[dict]]:
    """
    Merge low_stock + seasonal into one flat list suitable for
    notifier.notify_low_stock_alert().
    Returns None if nothing to notify.
    """
    if not result.should_notify:
        return None

    combined = []
    seen = set()

    for a in result.low_stock_alerts:
        key = (a["item"], a["store"])
        seen.add(key)
        combined.append(a)

    for s in result.seasonal_alerts:
        key = (s["item"], s["store"])
        if key not in seen:
            combined.append({
                "item":          s["item"],
                "store":         s["store"],
                "reorder_point": 0,
                "note":          s["message"],
            })

    return combined if combined else None
