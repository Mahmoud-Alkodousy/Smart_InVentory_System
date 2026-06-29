"""
ml/supplier_risk.py
─────────────────────
Supplier Risk Analysis.

Companies care about *who* they buy from as much as *how much* to buy.
A supplier with a 20-day lead time is a structural risk even if the
demand forecast is perfect — there's a 3-week window where nothing can
be done if demand spikes. This module turns the optional `supplier` /
`supplier_lead_time_days` columns (see data_agent/schema.py) into:

  • a risk score (0-100) and level (low/medium/high) per supplier
  • the items/value exposed to each supplier
  • concrete "switch supplier" suggestions when the same item is sourced
    from more than one supplier in the data, and a faster option exists

Gracefully returns an empty result when the uploaded data has no
supplier columns — callers should treat that as "feature not enabled
for this dataset", not an error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

# ── Risk scoring thresholds (days) ────────────────────────────────────────────
LOW_RISK_MAX_DAYS    = 5
MEDIUM_RISK_MAX_DAYS = 14


def _lead_time_to_score(avg_lead_time_days: float) -> float:
    """0-100 risk score. <=5 days → low (0-20), 6-14 → medium (20-60),
    >14 → high (60-100, saturating)."""
    if avg_lead_time_days <= LOW_RISK_MAX_DAYS:
        return round((avg_lead_time_days / LOW_RISK_MAX_DAYS) * 20, 1) if LOW_RISK_MAX_DAYS else 0.0
    if avg_lead_time_days <= MEDIUM_RISK_MAX_DAYS:
        span = MEDIUM_RISK_MAX_DAYS - LOW_RISK_MAX_DAYS
        return round(20 + ((avg_lead_time_days - LOW_RISK_MAX_DAYS) / span) * 40, 1)
    # High risk: saturates towards 100 by ~34 days lead time
    return round(min(100.0, 60 + (avg_lead_time_days - MEDIUM_RISK_MAX_DAYS) * 2), 1)


def _risk_level(score: float) -> str:
    if score < 20:
        return "low"
    if score < 60:
        return "medium"
    return "high"


_LEVEL_AR = {"low": "منخفض", "medium": "متوسط", "high": "مرتفع"}


@dataclass
class SupplierRisk:
    supplier:            str
    items_supplied:      list
    n_items:             int
    avg_lead_time_days:  float
    max_lead_time_days:  float
    risk_score:          float
    risk_level:          str
    risk_level_ar:       str
    value_exposed:       Optional[float] = None   # sum of recommended_stock × unit_price
    high_volatility_items: int = 0                # items with cv > 0.5 sourced from this supplier
    recommendation:      str = ""

    def to_dict(self) -> dict:
        return {
            "supplier":             self.supplier,
            "items_supplied":       self.items_supplied,
            "n_items":              self.n_items,
            "avg_lead_time_days":   self.avg_lead_time_days,
            "max_lead_time_days":   self.max_lead_time_days,
            "risk_score":           self.risk_score,
            "risk_level":           self.risk_level,
            "risk_level_ar":        self.risk_level_ar,
            "value_exposed":        self.value_exposed,
            "high_volatility_items": self.high_volatility_items,
            "recommendation":       self.recommendation,
        }


@dataclass
class SupplierSwitchSuggestion:
    item:               str
    current_supplier:   str
    current_lead_time:  float
    suggested_supplier: str
    suggested_lead_time: float
    days_saved:         float

    def to_dict(self) -> dict:
        return {
            "item":                self.item,
            "current_supplier":    self.current_supplier,
            "current_lead_time":   self.current_lead_time,
            "suggested_supplier":  self.suggested_supplier,
            "suggested_lead_time": self.suggested_lead_time,
            "days_saved":          self.days_saved,
        }


def has_supplier_data(df: pd.DataFrame) -> bool:
    return "supplier" in df.columns and df["supplier"].notna().any()


def analyze_suppliers(
    df: pd.DataFrame,
    recommendations: Optional[list] = None,   # list[ItemRecommendation] or list[dict]
) -> list[SupplierRisk]:
    """
    Build a per-supplier risk profile from the uploaded data.

    df must contain a `supplier` column to produce any results; the
    `supplier_lead_time_days` column is optional (falls back to a neutral
    7-day assumption with a lower-confidence note when missing).
    """
    if not has_supplier_data(df):
        return []

    has_lead_time = "supplier_lead_time_days" in df.columns and df["supplier_lead_time_days"].notna().any()

    rec_by_item: dict = {}
    if recommendations:
        for r in recommendations:
            d = r.to_dict() if hasattr(r, "to_dict") else r
            rec_by_item.setdefault(str(d.get("item")), []).append(d)

    rows = df.dropna(subset=["supplier"])[["item", "supplier"] + (["supplier_lead_time_days"] if has_lead_time else [])]

    results: list[SupplierRisk] = []
    for supplier, group in rows.groupby("supplier"):
        items = sorted({str(i) for i in group["item"].unique()})

        if has_lead_time and group["supplier_lead_time_days"].notna().any():
            avg_lt = float(group["supplier_lead_time_days"].mean())
            max_lt = float(group["supplier_lead_time_days"].max())
        else:
            avg_lt = max_lt = 7.0  # neutral default when no lead-time data at all

        score = _lead_time_to_score(avg_lt)
        level = _risk_level(score)

        value_exposed = None
        high_vol = 0
        for item in items:
            for d in rec_by_item.get(item, []):
                if d.get("capital_tied_up") is not None:
                    value_exposed = (value_exposed or 0.0) + d["capital_tied_up"]
                if (d.get("cv") or 0) > 0.5:
                    high_vol += 1

        if level == "high":
            rec = (
                f"مدة توريد مرتفعة ({avg_lt:.0f} يوم) — يُنصح بالبحث عن مورد بديل "
                f"أسرع أو رفع المخزون الآمن لهذا المورد."
            )
        elif level == "medium":
            rec = f"مدة توريد متوسطة ({avg_lt:.0f} يوم) — راقب هذا المورد عند اقتراب موسم الذروة."
        else:
            rec = f"مدة توريد جيدة ({avg_lt:.0f} يوم) — مخاطر منخفضة."

        results.append(SupplierRisk(
            supplier=str(supplier),
            items_supplied=items,
            n_items=len(items),
            avg_lead_time_days=round(avg_lt, 1),
            max_lead_time_days=round(max_lt, 1),
            risk_score=score,
            risk_level=level,
            risk_level_ar=_LEVEL_AR[level],
            value_exposed=round(value_exposed, 2) if value_exposed is not None else None,
            high_volatility_items=high_vol,
            recommendation=rec,
        ))

    results.sort(key=lambda r: r.risk_score, reverse=True)
    return results


def suggest_supplier_switches(df: pd.DataFrame) -> list[SupplierSwitchSuggestion]:
    """
    When the data shows more than one supplier for the same item (e.g.
    different historical orders went to different suppliers), suggest
    consolidating future orders with whichever one has the shorter lead
    time. Returns [] if there's no supplier data or no item is genuinely
    multi-sourced.
    """
    if not has_supplier_data(df) or "supplier_lead_time_days" not in df.columns:
        return []

    rows = df.dropna(subset=["supplier"])
    suggestions: list[SupplierSwitchSuggestion] = []

    for item, group in rows.groupby("item"):
        per_supplier = (
            group.dropna(subset=["supplier_lead_time_days"])
            .groupby("supplier")["supplier_lead_time_days"].mean()
        )
        if len(per_supplier) < 2:
            continue  # single-sourced — nothing to compare

        best_supplier   = per_supplier.idxmin()
        best_lead_time  = float(per_supplier.min())
        worst_supplier  = per_supplier.idxmax()
        worst_lead_time = float(per_supplier.max())

        if worst_supplier == best_supplier or worst_lead_time <= best_lead_time:
            continue

        suggestions.append(SupplierSwitchSuggestion(
            item=str(item),
            current_supplier=str(worst_supplier),
            current_lead_time=round(worst_lead_time, 1),
            suggested_supplier=str(best_supplier),
            suggested_lead_time=round(best_lead_time, 1),
            days_saved=round(worst_lead_time - best_lead_time, 1),
        ))

    suggestions.sort(key=lambda s: s.days_saved, reverse=True)
    return suggestions
