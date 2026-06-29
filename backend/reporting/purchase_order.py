"""
reporting/purchase_order.py
──────────────────────────────
Auto Purchase Order Generator.

Turns a list of inventory recommendations into a ready-to-send PDF
purchase order — the system goes from "here's data" to "here's the
document you sign and email to the supplier."

Design notes
─────────────
- Structural labels (Purchase Order, Supplier, Item, Quantity, Unit
  Price, Total, Date, Notes...) are in English. Procurement documents
  in Egypt — like most B2B paperwork — are routinely issued in English
  even at Arabic-speaking companies, and it sidesteps a real technical
  risk: reportlab does not do Arabic glyph shaping or bidi reordering
  on its own.
- Item/product names coming from the user's own data MAY be Arabic.
  Those are reshaped (arabic_reshaper) and bidi-reordered (python-bidi)
  when those optional libraries are installed, using an embedded
  Arabic-capable TTF font when one can be found on the system. If
  neither the libraries nor a suitable font are available, Arabic
  item names still print (just without joined letterforms) instead of
  crashing PDF generation — degrade gracefully, never fail the request.
"""

from __future__ import annotations

import io
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

_FONT_CANDIDATES = [
    os.getenv("PO_ARABIC_FONT_PATH", ""),

    # Linux (Docker / production) — installed via fonts-dejavu-core /
    # fonts-freefont-ttf / fonts-noto-core apt packages
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
    "/usr/share/fonts/opentype/noto/NotoNaskhArabic-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",

    # Windows (local dev) — these ship with every Windows install, so no
    # extra setup is needed to see correct Arabic glyphs while developing.
    "C:\\Windows\\Fonts\\tahoma.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
    "C:\\Windows\\Fonts\\segoeui.ttf",
    "C:\\Windows\\Fonts\\arabtype.ttf",

    # macOS (local dev)
    "/System/Library/Fonts/Supplemental/Tahoma.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]

_FONT_NAME = "Helvetica"   # reportlab built-in fallback — always available
_FONT_BOLD = "Helvetica-Bold"
_font_registered = False


def _register_font_once() -> None:
    global _FONT_NAME, _FONT_BOLD, _font_registered
    if _font_registered:
        return
    _font_registered = True

    for path in _FONT_CANDIDATES:
        if path and os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont("POArabic", path))
                _FONT_NAME = "POArabic"
                _FONT_BOLD = "POArabic"  # single weight — TTF has no separate bold file
                logger.info("Purchase order PDF: using Arabic-capable font %s", path)
                return
            except Exception as exc:
                logger.warning("Could not register font %s: %s", path, exc)

    logger.warning(
        "Purchase order PDF: no Arabic-capable font found on this system — "
        "Arabic item names will render without joined letterforms. "
        "Install 'fonts-dejavu-core' or 'fonts-freefont-ttf', or set "
        "PO_ARABIC_FONT_PATH to a .ttf file with Arabic coverage."
    )


def _shape_arabic(text: str) -> str:
    """
    Pass-through. reportlab >= 4.0's Paragraph engine already detects RTL
    runs and reorders/shapes them correctly on its own, *provided* the
    active font actually contains Arabic glyphs (see _register_font_once).
    Manually reshaping with arabic_reshaper/python-bidi on top of that
    would double-process the text and likely garble it — verified
    empirically against reportlab 4.4.10 + DejaVuSans, so this function is
    intentionally a no-op kept only so call sites have one obvious place
    to hook in if a future reportlab version ever regresses this.
    """
    return text


@dataclass
class POLineItem:
    item:        str
    quantity:    float
    unit_price:  Optional[float] = None
    store:       Optional[str]   = None

    @property
    def line_total(self) -> Optional[float]:
        if self.unit_price is None:
            return None
        return round(self.quantity * self.unit_price, 2)


@dataclass
class PurchaseOrder:
    items:          list[POLineItem]
    supplier_name:  str = "—"
    po_number:      str = field(default_factory=lambda: f"PO-{uuid.uuid4().hex[:8].upper()}")
    issue_date:      date = field(default_factory=date.today)
    expected_delivery_days: Optional[int] = None
    notes:          str = ""
    currency:       str = "EGP"
    company_name:   str = "Smart Inventory Manager"

    @property
    def grand_total(self) -> Optional[float]:
        totals = [li.line_total for li in self.items if li.line_total is not None]
        if not totals or len(totals) != len(self.items):
            return None
        return round(sum(totals), 2)


_styles = getSampleStyleSheet()


def generate_purchase_order_pdf(po: PurchaseOrder) -> bytes:
    """Render a PurchaseOrder into a polished one-page(ish) PDF and
    return the raw PDF bytes (ready to stream back over HTTP)."""
    _register_font_once()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Purchase Order {po.po_number}",
    )

    title_style = ParagraphStyle(
        "POTitle", fontName=_FONT_BOLD, fontSize=20, leading=24,
        textColor=colors.HexColor("#0f172a"),
    )
    meta_style = ParagraphStyle(
        "POMeta", fontName=_FONT_NAME, fontSize=9.5, leading=14,
        textColor=colors.HexColor("#475569"),
    )
    section_style = ParagraphStyle(
        "POSection", fontName=_FONT_BOLD, fontSize=10.5, leading=14,
        textColor=colors.HexColor("#0369a1"), spaceBefore=4, spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "POBody", fontName=_FONT_NAME, fontSize=9.5, leading=13,
        textColor=colors.HexColor("#1e293b"),
    )
    notes_style = ParagraphStyle(
        "PONotes", fontName=_FONT_NAME, fontSize=8.5, leading=12,
        textColor=colors.HexColor("#64748b"),
    )

    elements = []

    # ── Header ────────────────────────────────────────────────────────────────
    header_table = Table(
        [[
            Paragraph("PURCHASE ORDER", title_style),
            Paragraph(
                f"<b>{po.company_name}</b><br/>"
                f"Smart Inventory Manager — AI Demand Forecasting",
                meta_style,
            ),
        ]],
        colWidths=[None, 70 * mm],
    )
    header_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 4 * mm))
    elements.append(HRFlowable(width="100%", color=colors.HexColor("#0369a1"), thickness=1.4))
    elements.append(Spacer(1, 5 * mm))

    # ── PO meta + Supplier ───────────────────────────────────────────────────
    meta_rows = [
        [Paragraph("<b>PO Number</b>", meta_style), Paragraph(po.po_number, body_style)],
        [Paragraph("<b>Issue Date</b>", meta_style), Paragraph(po.issue_date.isoformat(), body_style)],
        [
            Paragraph("<b>Expected Lead Time</b>", meta_style),
            Paragraph(
                f"{po.expected_delivery_days} days" if po.expected_delivery_days else "—",
                body_style,
            ),
        ],
    ]
    supplier_para = Paragraph(_shape_arabic(po.supplier_name), body_style)
    info_table = Table(
        [
            [Paragraph("<b>SUPPLIER</b>", section_style), ""],
            [supplier_para, Table(meta_rows, colWidths=[35 * mm, 35 * mm])],
        ],
        colWidths=[90 * mm, 70 * mm],
    )
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("SPAN", (0, 0), (1, 0)),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 7 * mm))

    # ── Line items table ──────────────────────────────────────────────────────
    has_prices = po.grand_total is not None
    head = ["#", "Item", "Branch", "Quantity"]
    if has_prices:
        head += [f"Unit Price ({po.currency})", f"Line Total ({po.currency})"]

    table_data = [head]
    for i, li in enumerate(po.items, start=1):
        row = [
            str(i),
            Paragraph(_shape_arabic(str(li.item)), body_style),
            Paragraph(_shape_arabic(str(li.store)) if li.store is not None else "—", body_style),
            f"{li.quantity:,.0f}",
        ]
        if has_prices:
            row += [
                f"{li.unit_price:,.2f}" if li.unit_price is not None else "—",
                f"{li.line_total:,.2f}" if li.line_total is not None else "—",
            ]
        table_data.append(row)

    col_widths = [10 * mm, None, 28 * mm, 22 * mm]
    if has_prices:
        col_widths += [28 * mm, 30 * mm]

    items_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), _FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0369a1")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    items_table.setStyle(TableStyle(style_cmds))
    elements.append(items_table)
    elements.append(Spacer(1, 4 * mm))

    # ── Grand total ───────────────────────────────────────────────────────────
    if po.grand_total is not None:
        total_table = Table(
            [["", "GRAND TOTAL", f"{po.grand_total:,.2f} {po.currency}"]],
            colWidths=[None, 35 * mm, 35 * mm],
        )
        total_table.setStyle(TableStyle([
            ("FONTNAME", (1, 0), (-1, 0), _FONT_BOLD),
            ("FONTSIZE", (1, 0), (-1, 0), 11),
            ("ALIGN", (1, 0), (-1, 0), "RIGHT"),
            ("LINEABOVE", (1, 0), (-1, 0), 1, colors.HexColor("#0369a1")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("TEXTCOLOR", (1, 0), (-1, 0), colors.HexColor("#0369a1")),
        ]))
        elements.append(total_table)
        elements.append(Spacer(1, 6 * mm))
    else:
        elements.append(Paragraph(
            "* Unit price not provided for one or more items — totals omitted. "
            "Add a unit_price/price column to your data to enable cost totals.",
            notes_style,
        ))
        elements.append(Spacer(1, 6 * mm))

    # ── Notes ─────────────────────────────────────────────────────────────────
    if po.notes:
        elements.append(Paragraph("<b>Notes</b>", section_style))
        elements.append(Paragraph(_shape_arabic(po.notes), body_style))
        elements.append(Spacer(1, 6 * mm))

    elements.append(HRFlowable(width="100%", color=colors.HexColor("#cbd5e1"), thickness=0.7))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(
        f"Generated automatically by Smart Inventory Manager — AI demand "
        f"forecasting & inventory recommendation system · "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        notes_style,
    ))

    doc.build(elements)
    return buf.getvalue()


def build_auto_po_from_recommendations(
    recommendations: list,           # list[dict] — recommender output
    supplier_name: str = "Primary Supplier",
    expected_delivery_days: Optional[int] = None,
    only_at_risk: bool = False,
    top_n: Optional[int] = None,
) -> PurchaseOrder:
    """
    Convenience builder: turn raw recommendation dicts into a PurchaseOrder,
    optionally filtered down to at-risk items only (seasonal_warning or
    high CV) and/or capped to the top N by recommended quantity.
    """
    rows = list(recommendations)
    if only_at_risk:
        rows = [r for r in rows if r.get("seasonal_warning") or (r.get("cv") or 0) > 0.7]

    rows.sort(key=lambda r: r.get("recommended_stock", 0), reverse=True)
    if top_n:
        rows = rows[:top_n]

    items = [
        POLineItem(
            item=str(r.get("item")),
            quantity=round(r.get("recommended_stock", 0)),
            unit_price=r.get("unit_price"),
            store=str(r.get("store")) if r.get("store") is not None else None,
        )
        for r in rows
    ]

    return PurchaseOrder(
        items=items,
        supplier_name=supplier_name,
        expected_delivery_days=expected_delivery_days,
        notes=(
            "This purchase order was generated automatically based on "
            "AI inventory recommendations. Please review before sending "
            "to the supplier."
        ),
    )
