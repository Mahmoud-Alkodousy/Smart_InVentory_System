"""
monitoring_jobs/notifier.py
────────────────────────────
Email notification system using SMTP (Gmail / SendGrid / any SMTP provider).

Required env vars:
  SMTP_HOST        — e.g. smtp.gmail.com
  SMTP_PORT        — e.g. 587
  SMTP_USER        — sender email address
  SMTP_PASSWORD    — app password or SMTP password
  SMTP_FROM_NAME   — display name (default: "Smart Inventory Manager")

Optional:
  SMTP_USE_TLS     — "true" (default) or "false"
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

SMTP_HOST      = os.getenv("SMTP_HOST", "")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER      = os.getenv("SMTP_USER", "")
SMTP_PASSWORD  = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Smart Inventory Manager")
SMTP_USE_TLS   = os.getenv("SMTP_USE_TLS", "true").strip().lower() in ("true", "1", "yes")


# ── Core send function ────────────────────────────────────────────────────────

def send_email(
    to_email:    str,
    subject:     str,
    html_body:   str,
    plain_body:  Optional[str] = None,
) -> bool:
    """
    Send an HTML email via SMTP.
    Returns True on success, False on any failure (never raises).
    """
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD]):
        logger.warning("Email: SMTP_HOST / SMTP_USER / SMTP_PASSWORD not set — skipping")
        return False

    if not to_email or "@" not in to_email:
        logger.warning("Email: invalid to_email '%s' — skipping", to_email)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
        msg["To"]      = to_email

        if plain_body:
            msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        context = ssl.create_default_context()

        if SMTP_USE_TLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                server.starttls(context=context)
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, to_email, msg.as_string())
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, to_email, msg.as_string())

        logger.info("Email: sent to %s — '%s'", to_email, subject)
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("Email: SMTP authentication failed — check SMTP_USER / SMTP_PASSWORD")
        return False
    except smtplib.SMTPException as exc:
        logger.warning("Email: SMTP error — %s", exc)
        return False
    except Exception as exc:
        logger.warning("Email: unexpected error — %s", exc)
        return False


# ── HTML email templates ──────────────────────────────────────────────────────

def _base_template(title: str, content: str, color: str = "#38bdf8") -> str:
    return f"""
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #060810; margin: 0; padding: 0; direction: rtl; }}
  .wrapper {{ max-width: 600px; margin: 0 auto; padding: 24px 16px; }}
  .card {{ background: #101828; border: 1px solid rgba(56,189,248,0.15); border-radius: 16px; padding: 32px 28px; }}
  .logo {{ display: flex; align-items: center; gap: 10px; margin-bottom: 28px; }}
  .logo-icon {{ width: 40px; height: 40px; background: linear-gradient(135deg, {color}, #818cf8); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; }}
  .logo-text {{ color: #f0f6fc; font-size: 16px; font-weight: 600; }}
  h2 {{ color: #f0f6fc; font-size: 22px; font-weight: 700; margin: 0 0 8px; }}
  .subtitle {{ color: #8b98b0; font-size: 14px; margin-bottom: 24px; }}
  .divider {{ border: none; border-top: 1px solid rgba(56,189,248,0.1); margin: 20px 0; }}
  .content {{ color: #cbd5e1; font-size: 15px; line-height: 1.7; }}
  .footer {{ color: #3d4f68; font-size: 12px; text-align: center; margin-top: 24px; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="card">
    <div class="logo">
      <div class="logo-icon">📦</div>
      <div class="logo-text">Smart Inventory Manager</div>
    </div>
    <h2>{title}</h2>
    <hr class="divider">
    <div class="content">{content}</div>
  </div>
  <div class="footer">
    هذا بريد تلقائي من منظومة إدارة المخزون الذكية.<br>
    لإيقاف الإشعارات، تواصل مع المسؤول.
  </div>
</div>
</body>
</html>
"""


# ── Alert helpers ─────────────────────────────────────────────────────────────

def notify_low_stock_alert(
    email:   str,
    alerts:  list[dict],   # list of {item, store, current, reorder_point}
) -> bool:
    """Send a low-stock alert email."""
    if not alerts:
        return False

    count = len(alerts)
    subject = f"⚠️ تنبيه مخزون — {count} منتج {'يحتاج' if count == 1 else 'يحتاجون'} إعادة طلب"

    rows = ""
    for a in alerts[:20]:
        rows += f"""
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(56,189,248,0.08);color:#f0f6fc;">{a['item']}</td>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(56,189,248,0.08);color:#8b98b0;">{a['store']}</td>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(56,189,248,0.08);color:#f87171;font-weight:600;">{a['reorder_point']:.0f} وحدة</td>
        </tr>"""

    extra = f'<p style="color:#8b98b0;font-size:13px;margin-top:12px;">+ {count - 20} منتجات أخرى</p>' if count > 20 else ""

    content = f"""
    <p style="font-size:17px;font-weight:600;color:#f87171;margin-bottom:16px;">
      ⚠️ تحذير: {count} منتج قرب مخزونه على الانتهاء
    </p>
    <table style="width:100%;border-collapse:collapse;background:#0c1120;border-radius:10px;overflow:hidden;">
      <thead>
        <tr style="background:rgba(248,113,113,0.1);">
          <th style="padding:10px 14px;text-align:right;color:#8b98b0;font-size:13px;font-weight:500;">المنتج</th>
          <th style="padding:10px 14px;text-align:right;color:#8b98b0;font-size:13px;font-weight:500;">الفرع</th>
          <th style="padding:10px 14px;text-align:right;color:#8b98b0;font-size:13px;font-weight:500;">نقطة إعادة الطلب</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    {extra}
    <p style="margin-top:20px;color:#8b98b0;">يرجى مراجعة المخزون واتخاذ الإجراء اللازم في أقرب وقت.</p>
    """

    html = _base_template("تنبيه مخزون منخفض", content, color="#f87171")
    plain = f"تنبيه: {count} منتج يحتاج إعادة طلب.\n" + "\n".join(
        f"- {a['item']} (متجر {a['store']}): نقطة إعادة الطلب {a['reorder_point']:.0f} وحدة"
        for a in alerts[:20]
    )
    return send_email(email, subject, html, plain)


def notify_analysis_done(
    email:    str,
    n_items:  int,
    n_stores: int,
    job_id:   str,
    report:   Optional[str] = None,
) -> bool:
    """Send a quiet 'analysis complete' confirmation email."""
    subject = "✅ اكتمل تحليل المخزون"

    report_section = ""
    if report:
        # Trim report to reasonable email length
        trimmed = report[:2000] + ("…" if len(report) > 2000 else "")
        report_section = f"""
        <hr style="border:none;border-top:1px solid rgba(56,189,248,0.1);margin:20px 0;">
        <p style="color:#8b98b0;font-size:13px;margin-bottom:10px;">ملخص التقرير:</p>
        <div style="background:#0c1120;border-radius:10px;padding:16px;color:#cbd5e1;font-size:14px;line-height:1.7;white-space:pre-wrap;">{trimmed}</div>
        """

    content = f"""
    <div style="display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap;">
      <div style="background:#0c1120;border:1px solid rgba(52,211,153,0.2);border-radius:10px;padding:16px 20px;flex:1;min-width:120px;">
        <div style="color:#8b98b0;font-size:12px;margin-bottom:4px;">المنتجات</div>
        <div style="color:#34d399;font-size:26px;font-weight:700;">{n_items}</div>
      </div>
      <div style="background:#0c1120;border:1px solid rgba(56,189,248,0.2);border-radius:10px;padding:16px 20px;flex:1;min-width:120px;">
        <div style="color:#8b98b0;font-size:12px;margin-bottom:4px;">الفروع</div>
        <div style="color:#38bdf8;font-size:26px;font-weight:700;">{n_stores}</div>
      </div>
      <div style="background:#0c1120;border:1px solid rgba(129,140,248,0.2);border-radius:10px;padding:16px 20px;flex:1;min-width:120px;">
        <div style="color:#8b98b0;font-size:12px;margin-bottom:4px;">رقم التحليل</div>
        <div style="color:#818cf8;font-size:14px;font-weight:600;margin-top:6px;">{job_id[:8]}…</div>
      </div>
    </div>
    <p style="color:#8b98b0;">تم تحليل بياناتك بنجاح وإنشاء توصيات المخزون للـ 90 يوم القادمة.</p>
    {report_section}
    """

    html = _base_template("اكتمل تحليل المخزون ✅", content, color="#34d399")
    plain = (
        f"تم اكتمال تحليل المخزون.\n"
        f"المنتجات: {n_items} | الفروع: {n_stores} | رقم التحليل: {job_id[:8]}\n"
        + (f"\n{report[:500]}" if report else "")
    )
    return send_email(email, subject, html, plain)


def notify_welcome(email: str, user_id: str, frequency: str, sheets_url: str) -> bool:
    """Send a welcome email when a new user registers."""
    freq_ar = {
        "daily":       "يومياً",
        "weekly":      "أسبوعياً",
        "monthly":     "شهرياً",
        "quarterly":   "كل 3 أشهر",
        "semiannual":  "كل 6 أشهر",
    }.get(frequency, frequency)

    subject = "🚀 تم تفعيل إشعارات المخزون"

    content = f"""
    <p style="font-size:17px;font-weight:600;color:#34d399;margin-bottom:20px;">أهلاً! تم تسجيلك بنجاح 🎉</p>
    <div style="background:#0c1120;border-radius:10px;padding:16px 20px;margin-bottom:20px;">
      <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(56,189,248,0.08);">
        <span style="color:#8b98b0;">معرّفك</span>
        <span style="color:#818cf8;font-family:monospace;font-size:13px;">{user_id[:12]}…</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(56,189,248,0.08);">
        <span style="color:#8b98b0;">تكرار التحليل</span>
        <span style="color:#f0f6fc;">{freq_ar}</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 0;">
        <span style="color:#8b98b0;">مصدر البيانات</span>
        <span style="color:#38bdf8;font-size:13px;">{"Google Sheets" if sheets_url != "__file__" else "ملف محمّل"}</span>
      </div>
    </div>
    <p style="color:#8b98b0;">سيبدأ النظام بتحليل مخزونك تلقائياً وفق الجدول المحدد، وستصلك إشعارات فورية عند اقتراب نفاد أي منتج.</p>
    """

    html = _base_template("مرحباً بك في Smart Inventory Manager", content)
    plain = f"تم تسجيلك بنجاح.\nمعرّفك: {user_id}\nتكرار التحليل: {freq_ar}"
    return send_email(email, subject, html, plain)
