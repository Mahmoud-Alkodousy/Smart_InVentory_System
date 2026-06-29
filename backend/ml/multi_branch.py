"""
ml/multi_branch.py
─────────────────────
Multi-Branch Optimization — "move it, don't buy it".

When the same item is tracked across several stores/branches (the
existing `store` column already gives us this — no new data required),
one branch can be sitting on excess stock while another is about to run
out of the very same item. Buying more is wasteful when a transfer would
solve it for free (or near-free).

This module only needs `current_stock` to be present (already an
optional column the recommender supports — see data_agent/schema.py).
Returns [] gracefully when current_stock isn't available or there's
only a single store in the data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# A branch only "donates" stock if its excess clears this safety margin —
# avoids suggesting transfers that would themselves create a shortage.
SURPLUS_SAFETY_MARGIN = 1.10   # keep 110% of recommended_stock before donating

# A branch is flagged as needing stock if it's below its reorder point
# (the lead-time buffer is already gone) OR below this fraction of its
# 90-day target — reorder_point alone is too small a bar (it only reflects
# the lead-time window, not the full target), so we use whichever signal
# is more inclusive.
DEFICIT_TARGET_RATIO = 0.50


@dataclass
class TransferSuggestion:
    item:                str
    from_store:          str
    to_store:            str
    quantity:            float
    unit_price:          Optional[float]
    value_saved:         Optional[float]   # avoided purchase cost
    from_store_stock_before: float
    from_store_stock_after:  float
    to_store_stock_before:   float
    to_store_stock_after:    float

    def to_dict(self) -> dict:
        return {
            "item":                     self.item,
            "from_store":               self.from_store,
            "to_store":                 self.to_store,
            "quantity":                 self.quantity,
            "unit_price":               self.unit_price,
            "value_saved":              self.value_saved,
            "from_store_stock_before":  self.from_store_stock_before,
            "from_store_stock_after":   self.from_store_stock_after,
            "to_store_stock_before":    self.to_store_stock_before,
            "to_store_stock_after":     self.to_store_stock_after,
        }


def suggest_transfers(recommendations: list) -> list[TransferSuggestion]:
    """
    recommendations: list[ItemRecommendation] or list[dict] (already
    containing store, item, current_stock, recommended_stock, reorder_point,
    unit_price — exactly the shape ml.recommender.recommend() produces).
    """
    recs = [r.to_dict() if hasattr(r, "to_dict") else r for r in recommendations]
    recs = [r for r in recs if r.get("current_stock") is not None]
    if not recs:
        return []

    by_item: dict[str, list[dict]] = {}
    for r in recs:
        by_item.setdefault(str(r["item"]), []).append(r)

    suggestions: list[TransferSuggestion] = []

    for item, rows in by_item.items():
        if len(rows) < 2:
            continue  # only one store carries this item — nothing to transfer

        surplus, deficit = [], []
        for r in rows:
            current = r["current_stock"]
            rec_stock = r["recommended_stock"] or 0
            reorder_point = r.get("reorder_point") or 0

            safe_floor = rec_stock * SURPLUS_SAFETY_MARGIN
            if current > safe_floor:
                surplus.append({**r, "excess": current - safe_floor})
            else:
                deficit_floor = max(reorder_point, rec_stock * DEFICIT_TARGET_RATIO)
                if current < deficit_floor:
                    deficit.append({**r, "shortage": rec_stock - current})

        if not surplus or not deficit:
            continue

        surplus.sort(key=lambda r: r["excess"], reverse=True)
        deficit.sort(key=lambda r: r["shortage"], reverse=True)

        # Greedy matching — biggest surplus feeds biggest shortage first.
        s_idx = 0
        for d in deficit:
            remaining_need = d["shortage"]
            while remaining_need > 0 and s_idx < len(surplus):
                s = surplus[s_idx]
                available = s["excess"]
                if available <= 0:
                    s_idx += 1
                    continue

                qty = round(min(available, remaining_need), 2)
                if qty <= 0:
                    s_idx += 1
                    continue

                unit_price = s.get("unit_price") or d.get("unit_price")
                value_saved = round(qty * unit_price, 2) if unit_price else None

                suggestions.append(TransferSuggestion(
                    item=item,
                    from_store=str(s["store"]),
                    to_store=str(d["store"]),
                    quantity=qty,
                    unit_price=unit_price,
                    value_saved=value_saved,
                    from_store_stock_before=s["current_stock"],
                    from_store_stock_after=round(s["current_stock"] - qty, 2),
                    to_store_stock_before=d["current_stock"],
                    to_store_stock_after=round(d["current_stock"] + qty, 2),
                ))

                s["excess"] -= qty
                remaining_need -= qty
                if s["excess"] <= 0:
                    s_idx += 1

    suggestions.sort(key=lambda s: (s.value_saved or 0), reverse=True)
    return suggestions


def total_value_saved(suggestions: list[TransferSuggestion]) -> float:
    return round(sum(s.value_saved or 0 for s in suggestions), 2)
