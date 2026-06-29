"""
ml/recommender.py
──────────────────
Inventory Recommender — Dynamic Safety Buffer (CV-based).

Updated to support:
  • Per-item pricing   via item_prices dict  {item: price}
  • Current stock      via current_stocks dict {(store, item): on_hand_units}
  • Service-level KPI  — estimated from buffer / CV profile
  • Savings calculation — capital locked in excess inventory
  • Supplier info       via supplier_map / supplier_lead_time_map ({item: ...})
  • External Events Impact — additive buffer from ml/events.py (Ramadan,
    Eid al-Fitr/Adha, Black Friday, Back-to-School), kept separate from
    the core recommended_stock — see recommended_stock_with_events.

Buffer logic (Coefficient of Variation):
  CV < 0.2  → 10%  (low volatility — stable product)
  CV < 0.5  → 20%  (medium volatility)
  CV >= 0.5 → 35%  (high volatility — seasonal / unpredictable)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional

import numpy as np
import pandas as pd

from ml.events import compute_event_impact


# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_LEAD_TIME_DAYS = 7
FORECAST_HORIZON_DAYS  = 90

# Estimated service level per buffer tier (based on using 90th-pct + buffer)
_SL_BY_BUFFER: dict[float, float] = {
    0.10: 87.0,
    0.20: 93.0,
    0.35: 97.5,
}


# ── Output dataclass ──────────────────────────────────────────────────────────

@dataclass
class ItemRecommendation:
    store:              str | int
    item:               str | int
    forecast_90d:       float
    forecast_90d_low:   float
    forecast_90d_high:  float
    avg_daily_demand:   float
    cv:                 float
    buffer_pct:         float
    recommended_stock:  float
    reorder_point:      float
    seasonal_warning:   bool
    warning_message:    str

    # ── Financial impact ──────────────────────────────────────────────────────
    unit_price:         Optional[float] = None
    capital_tied_up:    Optional[float] = None   # recommended_stock × unit_price
    safety_stock_value: Optional[float] = None   # (rec − forecast_median) × price

    # ── NEW: Current stock & savings ──────────────────────────────────────────
    current_stock:      Optional[float] = None   # on-hand units (from data column)
    excess_units:       Optional[float] = None   # current_stock − recommended_stock (if > 0)
    savings_value:      Optional[float] = None   # excess_units × unit_price

    # ── NEW: Service level KPI (estimated) ───────────────────────────────────
    service_level_pct:  Optional[float] = None   # estimated % of demand fulfilled

    # ── Supplier info (only populated when a `supplier` column is present) ──
    supplier:                  Optional[str]   = None
    supplier_lead_time_days:   Optional[float] = None

    # ── External Events Impact — additive, never silently folded into
    #    recommended_stock (see ml/events.py docstring for why) ──────────────
    event_tags:                    list[str] = field(default_factory=list)
    event_buffer_units:            float     = 0.0
    event_note:                    str       = ""
    recommended_stock_with_events: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ── Main entry point ──────────────────────────────────────────────────────────

def recommend(
    history_df:     pd.DataFrame,
    forecast_df:    pd.DataFrame,
    lead_time_days: int = DEFAULT_LEAD_TIME_DAYS,
    unit_price:     Optional[float] = None,
    item_prices:    Optional[dict]  = None,   # NEW: {item: price} — overrides global
    current_stocks: Optional[dict]  = None,   # NEW: {(store, item): on_hand_units}
    supplier_map:           Optional[dict] = None,   # NEW: {item: supplier_name}
    supplier_lead_time_map: Optional[dict] = None,   # NEW: {item: lead_time_days}
    apply_event_adjustments: bool = True,            # NEW: see ml/events.py
) -> list[ItemRecommendation]:
    """
    Generate inventory recommendations for every (store, item) pair.

    Parameters
    ----------
    history_df      : Clean historical DataFrame — date | store | item | sales
    forecast_df     : Output of ml.model.forecast()
    lead_time_days  : Days between order placement and delivery.
    unit_price      : Optional global cost per unit (fallback when item_prices missing).
    item_prices     : Per-item price dict {item: price}. Takes priority over unit_price.
    current_stocks  : On-hand quantity keyed by (store, item) tuple. Enables savings calc.
    supplier_map           : Per-item supplier name {item: supplier}.
    supplier_lead_time_map : Per-item supplier lead time in days {item: days}.
    apply_event_adjustments : Whether to compute the External Events Impact
                               buffer (Ramadan/Eid/Black Friday/back-to-school).
    """
    recommendations: list[ItemRecommendation] = []
    pairs = forecast_df[["store", "item"]].drop_duplicates().values.tolist()

    for store, item in pairs:
        hist_mask     = (history_df["store"] == store) & (history_df["item"] == item)
        forecast_mask = (forecast_df["store"] == store) & (forecast_df["item"] == item)

        hist_sales = history_df.loc[hist_mask, "sales"].dropna()
        fc_rows    = forecast_df.loc[forecast_mask]

        pred_median = fc_rows["pred_sales"]
        pred_low    = fc_rows.get("pred_sales_low",  pred_median)
        pred_high   = fc_rows.get("pred_sales_high", pred_median)

        # Resolve effective unit price for this item
        effective_price = (
            item_prices.get(item) if item_prices else None
        ) or unit_price

        # Resolve current stock for this (store, item) pair — current_stocks
        # is keyed by (store, item), NOT item alone, since the same item can
        # carry very different stock levels at different branches.
        effective_stock = current_stocks.get((store, item)) if current_stocks else None

        # Resolve supplier info for this item
        effective_supplier   = supplier_map.get(item) if supplier_map else None
        effective_lead_time  = supplier_lead_time_map.get(item) if supplier_lead_time_map else None

        rec = _build_recommendation(
            store=store,
            item=item,
            hist_sales=hist_sales,
            pred_median=pred_median,
            pred_low=pred_low,
            pred_high=pred_high,
            lead_time_days=lead_time_days,
            history_df=history_df.loc[hist_mask],
            unit_price=effective_price,
            current_stock=effective_stock,
            supplier=effective_supplier,
            supplier_lead_time_days=effective_lead_time,
            forecast_dates=fc_rows["date"] if "date" in fc_rows.columns else None,
            apply_event_adjustments=apply_event_adjustments,
        )
        recommendations.append(rec)

    return recommendations


def recommendations_to_df(recs: list[ItemRecommendation]) -> pd.DataFrame:
    return pd.DataFrame([r.to_dict() for r in recs])


# ── Per-item logic ────────────────────────────────────────────────────────────

def _build_recommendation(
    store,
    item,
    hist_sales:    pd.Series,
    pred_median:   pd.Series,
    pred_low:      pd.Series,
    pred_high:     pd.Series,
    lead_time_days: int,
    history_df:    pd.DataFrame,
    unit_price:    Optional[float] = None,
    current_stock: Optional[float] = None,
    supplier:                Optional[str]   = None,
    supplier_lead_time_days: Optional[float] = None,
    forecast_dates:          Optional[pd.Series] = None,
    apply_event_adjustments: bool = True,
) -> ItemRecommendation:

    forecast_90d      = float(pred_median.sum())
    forecast_90d_low  = float(pred_low.sum())
    forecast_90d_high = float(pred_high.sum())
    avg_daily_demand  = forecast_90d / FORECAST_HORIZON_DAYS

    cv         = _compute_cv(hist_sales)
    buffer_pct = _cv_to_buffer(cv)

    recommended_stock = forecast_90d_high * (1 + buffer_pct)
    reorder_point     = avg_daily_demand * lead_time_days

    seasonal_warning, warning_message = _check_seasonal_warning(
        hist_sales, history_df, item
    )

    # ── Financial impact ──────────────────────────────────────────────────────
    capital_tied_up    = None
    safety_stock_value = None
    if unit_price is not None and unit_price > 0:
        capital_tied_up    = round(recommended_stock * unit_price, 2)
        safety_buffer_units = max(0.0, recommended_stock - forecast_90d)
        safety_stock_value  = round(safety_buffer_units * unit_price, 2)

    # ── Current-stock savings ─────────────────────────────────────────────────
    excess_units  = None
    savings_value = None
    if current_stock is not None and current_stock >= 0:
        raw_excess = current_stock - recommended_stock
        excess_units = round(max(0.0, raw_excess), 2)
        if unit_price is not None and unit_price > 0 and excess_units > 0:
            savings_value = round(excess_units * unit_price, 2)

    # ── Service-level KPI (estimate) ──────────────────────────────────────────
    service_level_pct = _SL_BY_BUFFER.get(buffer_pct, 90.0)

    # ── External Events Impact (additive buffer — see ml/events.py) ─────────
    event_tags: list[str] = []
    event_buffer_units    = 0.0
    event_note            = ""
    recommended_stock_with_events = recommended_stock

    if apply_event_adjustments and forecast_dates is not None and len(forecast_dates) > 0:
        try:
            window_start = pd.Timestamp(forecast_dates.min()).date()
            window_end   = pd.Timestamp(forecast_dates.max()).date()
            impacts = compute_event_impact(
                window_start=window_start,
                window_end=window_end,
                avg_daily_demand=avg_daily_demand,
            )
            if impacts:
                event_buffer_units = round(sum(i.additional_units for i in impacts), 2)
                event_tags = [i.name_ar for i in impacts]
                recommended_stock_with_events = round(recommended_stock + event_buffer_units, 2)
                top = max(impacts, key=lambda i: i.additional_units)
                event_note = (
                    f"يقع جزء من فترة التوقع ضمن: {', '.join(event_tags)}. "
                    f"يُقترح هامش إضافي قدره {event_buffer_units:.0f} وحدة "
                    f"(أبرزها {top.name_ar} بزيادة طلب متوقعة +{top.uplift_pct*100:.0f}%)."
                )
        except Exception:
            # Calendar layer is a best-effort enhancement — never break the
            # core recommendation if date parsing fails for any reason.
            pass

    return ItemRecommendation(
        store=store,
        item=item,
        forecast_90d=round(forecast_90d, 2),
        forecast_90d_low=round(forecast_90d_low, 2),
        forecast_90d_high=round(forecast_90d_high, 2),
        avg_daily_demand=round(avg_daily_demand, 2),
        cv=round(cv, 3),
        buffer_pct=buffer_pct,
        recommended_stock=round(recommended_stock, 2),
        reorder_point=round(reorder_point, 2),
        seasonal_warning=seasonal_warning,
        warning_message=warning_message,
        unit_price=unit_price,
        capital_tied_up=capital_tied_up,
        safety_stock_value=safety_stock_value,
        current_stock=round(current_stock, 2) if current_stock is not None else None,
        excess_units=excess_units,
        savings_value=savings_value,
        service_level_pct=service_level_pct,
        supplier=supplier,
        supplier_lead_time_days=round(supplier_lead_time_days, 1) if supplier_lead_time_days is not None else None,
        event_tags=event_tags,
        event_buffer_units=event_buffer_units,
        event_note=event_note,
        recommended_stock_with_events=recommended_stock_with_events,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_cv(sales: pd.Series) -> float:
    if len(sales) == 0:
        return 0.0
    mean = sales.mean()
    if mean == 0:
        return 0.0
    return float(sales.std() / mean)


def _cv_to_buffer(cv: float) -> float:
    if cv < 0.2:
        return 0.10
    elif cv < 0.5:
        return 0.20
    else:
        return 0.35


def _check_seasonal_warning(
    hist_sales:  pd.Series,
    history_df:  pd.DataFrame,
    item,
) -> tuple[bool, str]:
    if "date" not in history_df.columns or len(history_df) < 30:
        return False, ""

    h = history_df.copy()
    h["date"]    = pd.to_datetime(h["date"])
    h["quarter"] = h["date"].dt.quarter

    quarterly = h.groupby("quarter")["sales"].sum()
    if quarterly.sum() == 0:
        return False, ""

    quarterly_pct = quarterly / quarterly.sum()
    peak_quarter  = int(quarterly_pct.idxmax())
    peak_pct      = float(quarterly_pct.max())

    QUARTER_NAMES = {
        1: "الربع الأول (يناير–مارس)",
        2: "الربع الثاني (أبريل–يونيو)",
        3: "الربع الثالث (يوليو–سبتمبر)",
        4: "الربع الرابع (أكتوبر–ديسمبر)",
    }

    if peak_pct >= 0.40:
        return (
            True,
            f"يبلغ هذا المنتج ذروته تاريخياً في {QUARTER_NAMES[peak_quarter]} "
            f"({peak_pct*100:.0f}% من المبيعات السنوية). "
            "يُنصح بتوفير مخزون إضافي قبل هذه الفترة.",
        )

    return False, ""
