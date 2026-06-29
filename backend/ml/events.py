"""
ml/events.py
─────────────
External Events Impact — calendar of recurring demand-shifting events
(Ramadan, Eid al-Fitr, Eid al-Adha, Black Friday, Back-to-School).

Why this exists
────────────────
ml/model.py's Chronos forecast is univariate: it only sees a sequence of
past sales numbers, never actual calendar dates. That means it has no way
to know that Ramadan falls in March one year and February the next (it
shifts ~11 days earlier every Gregorian year) — it can only ever learn
"this time of year was high" from raw history, which breaks down for
lunar-calendar events and is slow to adapt for newly-listed items with
no prior-year history at all.

This module adds an explicit calendar layer on top of the statistical
forecast: given the 90-day forecast window for an item, it tells the
recommender which named events fall (even partially) inside that window,
and by how much demand is conventionally expected to rise — *as an
additional, clearly-labelled buffer*, not a silent change to the base
forecast (see ml/recommender.py — event_buffer_units is always reported
separately from recommended_stock).

Lunar (Hijri) events — Ramadan, Eid al-Fitr, Eid al-Adha — don't follow
a fixed Gregorian formula, so their dates below are anchored to published
moon-sighting-based estimates and should be treated as ±1 day estimates.
Re-check official announcements close to the date for exact timing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

# ── Default uplift percentages ────────────────────────────────────────────────
# Deliberately kept identical to the "Quick scenarios" presets already offered
# in the What-If Simulation card on the frontend (BusinessDashboard.jsx) so the
# automatic calendar layer and the manual slider always tell a consistent story.
UPLIFT_RAMADAN        = 0.40
UPLIFT_RAMADAN_RUNUP  = 0.25   # week before Ramadan — pre-stocking rush
UPLIFT_EID            = 0.30
UPLIFT_BLACK_FRIDAY   = 0.60
UPLIFT_BACK_TO_SCHOOL = 0.20

RUNUP_DAYS = 7   # days of "pre-stocking" demand bump before Ramadan starts

# ── Hijri-anchored event windows (Gregorian dates, ±1 day) ───────────────────
# First day of Ramadan, per published astronomical/lunar-sighting estimates.
_RAMADAN_START: dict[int, date] = {
    2024: date(2024, 3, 11),
    2025: date(2025, 3, 1),
    2026: date(2026, 2, 18),
    2027: date(2027, 2, 8),
    2028: date(2028, 1, 28),
    2029: date(2029, 1, 16),
    2030: date(2030, 1, 5),
}
_RAMADAN_DURATION_DAYS = 30  # safe upper bound (29 or 30 in reality)

# Eid al-Adha ≈ 70 days after Eid al-Fitr (which is the day after Ramadan ends).
_EID_ADHA_START: dict[int, date] = {
    2024: date(2024, 6, 16),
    2025: date(2025, 6, 6),
    2026: date(2026, 5, 27),
    2027: date(2027, 5, 16),
    2028: date(2028, 5, 5),
    2029: date(2029, 4, 24),
    2030: date(2030, 4, 13),
}
_EID_DURATION_DAYS = 4


@dataclass
class EventWindow:
    name:        str
    name_ar:     str
    category:    str          # "religious" | "retail" | "seasonal"
    start:       date
    end:         date          # inclusive
    uplift_pct:  float         # e.g. 0.40 = +40% demand

    def overlap_days(self, window_start: date, window_end: date) -> int:
        latest_start = max(self.start, window_start)
        earliest_end = min(self.end, window_end)
        return max(0, (earliest_end - latest_start).days + 1)

    @property
    def duration_days(self) -> int:
        return (self.end - self.start).days + 1


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """weekday: Monday=0 ... Sunday=6. Returns the n-th such weekday in the month."""
    d = date(year, month, 1)
    count = 0
    while True:
        if d.weekday() == weekday:
            count += 1
            if count == n:
                return d
        d += timedelta(days=1)


def _black_friday(year: int) -> date:
    """US Thanksgiving = 4th Thursday of November. Black Friday = day after."""
    thanksgiving = _nth_weekday_of_month(year, 11, weekday=3, n=4)  # Thursday
    return thanksgiving + timedelta(days=1)


def get_events_for_year(year: int) -> list[EventWindow]:
    """All tracked events whose window starts in *year* (or the adjacent
    year, for events that span the New Year boundary)."""
    events: list[EventWindow] = []

    ramadan_start = _RAMADAN_START.get(year)
    if ramadan_start:
        events.append(EventWindow(
            name="Ramadan (pre-stocking)", name_ar="تجهيز ما قبل رمضان",
            category="religious",
            start=ramadan_start - timedelta(days=RUNUP_DAYS),
            end=ramadan_start - timedelta(days=1),
            uplift_pct=UPLIFT_RAMADAN_RUNUP,
        ))
        ramadan_end = ramadan_start + timedelta(days=_RAMADAN_DURATION_DAYS - 1)
        events.append(EventWindow(
            name="Ramadan", name_ar="شهر رمضان",
            category="religious",
            start=ramadan_start, end=ramadan_end,
            uplift_pct=UPLIFT_RAMADAN,
        ))
        eid_fitr_start = ramadan_end + timedelta(days=1)
        events.append(EventWindow(
            name="Eid al-Fitr", name_ar="عيد الفطر",
            category="religious",
            start=eid_fitr_start,
            end=eid_fitr_start + timedelta(days=_EID_DURATION_DAYS - 1),
            uplift_pct=UPLIFT_EID,
        ))

    eid_adha_start = _EID_ADHA_START.get(year)
    if eid_adha_start:
        events.append(EventWindow(
            name="Eid al-Adha", name_ar="عيد الأضحى",
            category="religious",
            start=eid_adha_start,
            end=eid_adha_start + timedelta(days=_EID_DURATION_DAYS - 1),
            uplift_pct=UPLIFT_EID,
        ))

    events.append(EventWindow(
        name="Black Friday", name_ar="الجمعة البيضاء (Black Friday)",
        category="retail",
        start=_black_friday(year),
        end=_black_friday(year) + timedelta(days=3),  # extended weekend
        uplift_pct=UPLIFT_BLACK_FRIDAY,
    ))

    events.append(EventWindow(
        name="Back to School", name_ar="موسم بداية الدراسة",
        category="seasonal",
        start=date(year, 9, 1), end=date(year, 9, 30),
        uplift_pct=UPLIFT_BACK_TO_SCHOOL,
    ))

    return events


def _events_in_range(window_start: date, window_end: date) -> list[EventWindow]:
    """All events from the relevant years that could plausibly overlap the range."""
    years = set(range(window_start.year - 1, window_end.year + 2))
    all_events: list[EventWindow] = []
    for y in years:
        all_events.extend(get_events_for_year(y))
    return [e for e in all_events if e.overlap_days(window_start, window_end) > 0]


@dataclass
class EventImpact:
    name_ar:        str
    category:       str
    overlap_days:   int
    uplift_pct:     float
    additional_units: float


def compute_event_impact(
    window_start: date,
    window_end: date,
    avg_daily_demand: float,
    max_combined_uplift: float = 0.80,
) -> list[EventImpact]:
    """
    For an item's forecast window [window_start, window_end] (inclusive),
    return the list of overlapping events with the additional demand
    (in units) each one is conventionally expected to add.

    additional_units per event = avg_daily_demand × overlap_days × uplift_pct

    Combined uplift across all overlapping events is capped at
    *max_combined_uplift* (default 80%) to avoid unrealistic stacking when
    two events sit back-to-back (e.g. Ramadan ending right into Eid).
    """
    if avg_daily_demand <= 0:
        return []

    events = _events_in_range(window_start, window_end)
    impacts: list[EventImpact] = []
    total_uplift_used = 0.0

    # Most impactful first, so the cap (if hit) drops the smaller events.
    for ev in sorted(events, key=lambda e: e.uplift_pct, reverse=True):
        remaining_budget = max(0.0, max_combined_uplift - total_uplift_used)
        if remaining_budget <= 0:
            break
        applied_uplift = min(ev.uplift_pct, remaining_budget)
        overlap = ev.overlap_days(window_start, window_end)
        additional_units = round(avg_daily_demand * overlap * applied_uplift, 2)
        if additional_units <= 0:
            continue
        impacts.append(EventImpact(
            name_ar=ev.name_ar, category=ev.category,
            overlap_days=overlap, uplift_pct=applied_uplift,
            additional_units=additional_units,
        ))
        total_uplift_used += applied_uplift

    return impacts


def upcoming_events(reference_date: date, horizon_days: int = 180) -> list[dict]:
    """
    Calendar-only view (no demand data needed) for the Executive Summary:
    "Ramadan starts in 23 days — expect +40% demand for ~30 days."
    Used so the frontend can show forward-looking context even for events
    that start after the 90-day forecast horizon ends.
    """
    horizon_end = reference_date + timedelta(days=horizon_days)
    events = _events_in_range(reference_date, horizon_end)

    out = []
    for ev in sorted(events, key=lambda e: e.start):
        if ev.end < reference_date:
            continue
        days_until = (ev.start - reference_date).days
        out.append({
            "name":         ev.name,
            "name_ar":      ev.name_ar,
            "category":     ev.category,
            "start":        ev.start.isoformat(),
            "end":          ev.end.isoformat(),
            "duration_days": ev.duration_days,
            "uplift_pct":   ev.uplift_pct,
            "days_until":   max(0, days_until),
            "is_ongoing":   ev.start <= reference_date <= ev.end,
        })
    return out
