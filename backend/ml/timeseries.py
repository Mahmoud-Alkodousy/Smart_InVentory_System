"""
ml/timeseries.py
──────────────────
Builds a compact day-by-day payload (history + forecast w/ confidence band)
for a handful of top items, so the frontend can render an actual time-series
chart instead of only the 90-day aggregate totals.

Only the top N (store, item) pairs (by recommended_stock) are included to
keep the job payload small — charting every pair would bloat Redis/JSON
for no visual benefit (you can't usefully look at 200 line charts anyway).
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

DEFAULT_TOP_N      = 8
HISTORY_LOOKBACK_D = 120   # only send the recent tail of history, not the whole series


def build_timeseries_payload(
    history_df:  pd.DataFrame,
    forecast_df: pd.DataFrame,
    recs_list:   list[dict],
    top_n: int = DEFAULT_TOP_N,
) -> list[dict]:
    """
    Parameters
    ----------
    history_df  : clean DataFrame — date | store | item | sales
    forecast_df : output of ml.model.forecast() — date | store | item |
                  pred_sales | pred_sales_low | pred_sales_high
    recs_list   : list of ItemRecommendation.to_dict() — used to rank
                  which (store, item) pairs are worth charting
    top_n       : how many pairs to include

    Returns
    -------
    list[dict] — one entry per (store, item):
        {
          "store": ..., "item": ...,
          "history":  [{"date": "YYYY-MM-DD", "sales": float}, ...],
          "forecast": [{"date": "YYYY-MM-DD", "low": float,
                        "median": float, "high": float}, ...],
        }
    """
    if not recs_list:
        return []

    top_pairs = sorted(
        recs_list, key=lambda r: r.get("recommended_stock", 0), reverse=True
    )[:top_n]

    payload: list[dict] = []

    for rec in top_pairs:
        store, item = rec["store"], rec["item"]

        h_mask = (history_df["store"] == store) & (history_df["item"] == item)
        f_mask = (forecast_df["store"] == store) & (forecast_df["item"] == item)

        h = history_df.loc[h_mask].sort_values("date").tail(HISTORY_LOOKBACK_D)
        f = forecast_df.loc[f_mask].sort_values("date")

        payload.append({
            "store": store,
            "item":  item,
            "history": [
                {"date": str(pd.Timestamp(d).date()), "sales": float(s)}
                for d, s in zip(h["date"], h["sales"])
            ],
            "forecast": [
                {
                    "date":   str(pd.Timestamp(row.date).date()),
                    "low":    float(row.pred_sales_low),
                    "median": float(row.pred_sales),
                    "high":   float(row.pred_sales_high),
                }
                for row in f.itertuples(index=False)
            ],
        })

    return payload
