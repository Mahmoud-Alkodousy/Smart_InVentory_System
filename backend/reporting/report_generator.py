"""
reporting/report_generator.py
──────────────────────────────
LLM Report Generator — openai/gpt-4o via OpenRouter  (default)
                        OR  llama3.1:latest via Ollama  (if OLLAMA=True)
"""

from __future__ import annotations

import json
import logging
import os

import requests

from ml.recommender import ItemRecommendation
from monitoring.drift_detector import DriftReport

logger = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────────────────

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
REPORT_MODEL       = os.getenv("REPORT_MODEL", "openai/gpt-4o")
REQUEST_TIMEOUT    = 300

# Comma-separated fallback chain tried (in order) if REPORT_MODEL fails with a
# payment/credit error. Defaults to a couple of commonly-free OpenRouter models.
# Override with REPORT_MODEL_FALLBACKS="model/a:free,model/b:free" in .env.
REPORT_MODEL_FALLBACKS = [
    m.strip()
    for m in os.getenv(
        "REPORT_MODEL_FALLBACKS",
        "openai/gpt-oss-120b:free,openrouter/free",
    ).split(",")
    if m.strip()
]

OLLAMA_BASE_URL     = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_REPORT_MODEL = "llama3.1:latest"

_USE_OLLAMA = os.getenv("OLLAMA", "false").strip().lower() in ("true", "1", "yes")


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
أنت مستشار سلسلة توريد (Supply Chain) خبير، تكتب تقارير لمدير عملية يقرأ تقريرك خلال دقيقتين ويحتاج
يتخذ قرار شراء على أساسه. أسلوبك أسلوب استشاري واثق: تبدأ بالنتيجة، تدعمها بالأرقام، وتقترح إجراءً محددًا.
لست مجرد "مترجم بيانات" — مهمتك هي التحليل والربط بين الأرقام، لا سردها فقط.

قواعد صارمة:

1. اكتب التقرير بالكامل بلغة عربية فصحى واضحة وسلسة، بأسلوب تقرير إداري محترف (مثل تقرير يصدره مستشار
   عمليات لمجلس إدارة) — لا لغة أكاديمية متكلفة، ولا لغة عامية. أرقام/أسماء المنتجات بالإنجليزية مقبولة.

2. لا تُلخّص الجدول وصفًا (مثل "المنتج X يحتاج كمية Y") إلا إذا كان هذا الرقم يدعم استنتاجًا. ابحث دائمًا
   عن النمط الأكبر: هل الأزمة مركّزة في فرع واحد؟ في فئة منتجات معينة؟ هل هي موسمية أم مستمرة؟ اربط بين
   الأرقام المعطاة لك في "ملخص المؤشرات" واستخدمها فعليًا في كلامك — لا تتجاهلها.

3. لا تكرّر نفس الحقائق بصيغ مختلفة في أكثر من قسم. كل قسم له غرض مختلف:
   - الملخص التنفيذي = "ما الذي يهم المدير الآن؟" في 3-4 جمل فقط.
     إذا كانت أرقام مالية (رأس المال المربوط، التوفير المتوقع) موجودة في ملخص المؤشرات،
     فيجب أن يكون أول جملة في الملخص التنفيذي هي الأثر المالي بالأرقام — مثل:
     "يُمثّل المخزون الموصى به إجمالاً X جنيهاً من رأس المال، منها Y جنيهاً في المنتجات العاجلة..."
     ثم الانتقال لتحليل الوضع والقرار المطلوب.
   - أبرز النتائج = أرقام وحقائق قابلة للقياس، لا انطباعات.
   - الأقسام التفصيلية = تفاصيل الأمر التنفيذي (ماذا تشتري، من أين، متى).

4. لن تُكتب لك بيانات كل المنتجات — بل عيّنة تمثيلية فقط (أهم الحالات + عيّنة من الباقي)، إلى جانب
   "ملخص المؤشرات" المحسوب على كل المنتجات بدون استثناء. اعتمد على ملخص المؤشرات للأرقام الإجمالية،
   واستخدم العيّنة فقط للأمثلة والاستشهاد بحالات محددة. لا تكتب جدول "توصيات المخزون التفصيلية" بنفسك؛
   هذا الجدول الكامل (بكل المنتجات دون استثناء) يُضاف بعد كلامك تلقائيًا بكود منفصل — مهمتك فقط الأقسام
   التحليلية أدناه.

5. هيكل التقرير بهذا الترتيب الدقيق:

   ## الأثر المالي
   (أظهر هذا القسم فقط إذا كانت بيانات unit_price موجودة في ملخص المؤشرات — وإن لم تكن موجودة فاحذف القسم كاملاً)
   جملتان أو ثلاث: إجمالي رأس المال المربوط في المخزون الموصى به،
   وقيمة الهامش الأمني (safety stock) كتكلفة الحماية من نفاد المخزون.
   قارن بالبديل: "بدون هذا التحليل سيطلب المدير عشوائياً وقد يفاجأ بنفاد المخزون في موسم الذروة."

   ## ملخص تنفيذي
   (3-4 جمل: إذا وُجدت أرقام مالية ابدأ بها فوراً. اذكر رقمًا إجماليًا واحدًا على الأقل من ملخص المؤشرات.
   اختم بجملة توجيهية واحدة.)

   ## أبرز النتائج
   (4-6 نقاط، كل نقطة رقم أو حقيقة محددة وليست رأيًا عامًا)

   ## المنتجات التي تحتاج إعادة طلب عاجلة
   (فقط المنتجات ذات seasonal_warning=true أو cv > 1.0 الموجودة في العيّنة المُعطاة لك — إن لم توجد، اكتب "لا يوجد")

   ## المنتجات الموسمية التي تحتاج انتباهاً
   (المنتجات ذات تذبذب متوسط أو نمط موسمي الموجودة في العيّنة المُعطاة لك — إن لم توجد، اكتب "لا يوجد")

   ## تحذيرات جودة البيانات
   (تنبيهات جودة البيانات إن وُجدت — إن لم توجد، اكتب "لا توجد تحذيرات")

   ## خلاصة وتوصية
   (جملتان كحد أقصى: إجراء واحد محدد وقابل للتنفيذ هذا الأسبوع.)

   لا تكتب أي عنوان أو قسم بعد "خلاصة وتوصية" — توقف هناك، فالجدول التفصيلي الكامل يُضاف بعدك تلقائيًا.

6. لتحديد مستوى الأولوية (مستوى الأولوية) استخدم seasonal_warning و cv:
   - عاجل = seasonal_warning = true
   - مرتفع = cv > 1.0
   - متوسط = cv بين 0.5 و 1.0
   - منخفض = cv < 0.5

7. لتحديد مستوى التذبذب (مستوى التذبذب): buffer_pct=0.10 → منخفض، 0.20 → متوسط، 0.35 → مرتفع

8. إن وُجدت تحذيرات جودة بيانات، اذكرها بوضوح وبنغمة تحذير (⚠️) في القسم المخصص لها فقط،
   ولا تكررها في أقسام أخرى.

9. استخدم "ملخص المؤشرات" المُعطى لك في رسالة المستخدم كمصدر الأرقام الإجمالية — لا تُعيد حسابها بنفسك
   ولا تخترع أرقامًا غير موجودة في البيانات. العيّنة المُعطاة لك أمثلة فقط، وليست كل البيانات — لا تفترض
   أن عدد المنتجات هو عدد صفوف العيّنة، بل استخدم الرقم الموجود في "ملخص المؤشرات".

مثال على الأسلوب المطلوب (وليس المحتوى الحرفي):

---
## الأثر المالي
يُمثّل المخزون الموصى به إجمالي 847,000 جنيه من رأس المال الموظَّف، منها 312,000 جنيه هامش أمان
للحماية من تقلبات الطلب. الاستثمار في هذا الهامش يمنع خسائر نفاد المخزون المحتملة في موسم الذروة.

## ملخص تنفيذي
847,000 جنيه إجمالي رأس المال المطلوب للمخزون الموصى به، منها 127,000 جنيه في 4 منتجات عاجلة (27% من
الإجمالي) تتركز في فرع القاهرة. باقي المخزون مستقر نسبيًا. القرار الأهم الآن هو تأمين كمية HEATER
قبل دخول الموسم.
---

اتبع هذا المستوى من الدقة والربط بين الأرقام، لكن بمحتوى مبني فعليًا على البيانات المُعطاة لك أدناه.
"""


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_report(
    recommendations: list[ItemRecommendation],
    drift_report: DriftReport,
    extra_context: str = "",
) -> str:
    user_message = _build_user_message(recommendations, drift_report, extra_context)

    if _USE_OLLAMA:
        analysis_text = _call_ollama(user_message)
    else:
        analysis_text = _call_openrouter(user_message)

    full_table_md = _build_full_table_markdown(recommendations)

    return f"{analysis_text}\n\n## توصيات المخزون التفصيلية\n\n{full_table_md}"


# ── OpenRouter backend ────────────────────────────────────────────────────────

def _call_openrouter(user_message: str) -> str:
    api_key = _get_openrouter_key()

    models_to_try = [REPORT_MODEL] + REPORT_MODEL_FALLBACKS
    last_error: Exception | None = None

    for model_name in models_to_try:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            "temperature": 0.2,
            "max_tokens":  4000,
        }

        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                    "HTTP-Referer":  "https://smart-inventory-manager",
                    "X-Title":       "Smart Inventory Manager - Report",
                },
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            last_error = ReportGeneratorError(f"Report LLM request timed out (model: {model_name}).")
            continue
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            last_error = ReportGeneratorError(f"Report LLM HTTP error ({model_name}): {exc}")
            # 402 (payment/credits) or 429 (rate-limited) → try next model in the chain.
            # Anything else (e.g. 401 bad key) won't be fixed by switching models, but we
            # still try the chain in case it's a model-specific outage.
            if status in (402, 429) and model_name != models_to_try[-1]:
                logger.warning(
                    "Report model %s failed with %s — falling back to next model.",
                    model_name, status,
                )
                continue
            continue
        except requests.exceptions.RequestException as exc:
            last_error = ReportGeneratorError(f"Report LLM network error ({model_name}): {exc}")
            continue

        data = response.json()
        try:
            report = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            last_error = ReportGeneratorError(f"Unexpected response from Report LLM ({model_name}): {data}")
            continue

        if not report:
            last_error = ReportGeneratorError(f"Report LLM ({model_name}) returned an empty response.")
            continue

        if model_name != REPORT_MODEL:
            logger.info("Report generated successfully using fallback model: %s", model_name)
        return report

    # Every model in the chain failed — surface the last error.
    raise last_error or ReportGeneratorError("All report models failed with no specific error captured.")


# ── Ollama backend ────────────────────────────────────────────────────────────

def _call_ollama(user_message: str) -> str:
    url = f"{OLLAMA_BASE_URL}/api/chat"

    payload = {
        "model": OLLAMA_REPORT_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        "options": {"temperature": 0.2, "num_predict": 4000},
        "stream": False,
    }

    try:
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise ReportGeneratorError(f"Ollama Report request timed out (model: {OLLAMA_REPORT_MODEL}).")
    except requests.exceptions.HTTPError as exc:
        raise ReportGeneratorError(f"Ollama Report HTTP error: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise ReportGeneratorError(
            f"Ollama Report network error: {exc}\nIs Ollama running? Check: {OLLAMA_BASE_URL}"
        ) from exc

    data = response.json()

    try:
        report = data["message"]["content"].strip()
    except (KeyError, TypeError) as exc:
        raise ReportGeneratorError(f"Unexpected response format from Ollama: {data}") from exc

    if not report:
        raise ReportGeneratorError("Ollama Report returned an empty response.")

    return report


# ── Message builder ───────────────────────────────────────────────────────────

# Hard cap on how many rows we ever send to the LLM, regardless of how many
# products the dataset actually has (540 or 1,000,000 — doesn't matter, the
# sample sent to the model stays roughly this size). The full, unabridged
# table is built separately by _build_full_table_markdown() in pure Python
# and appended after the model's analysis — it never goes through the LLM.
MAX_SAMPLE_ROWS = 40

# Hard cap on how many rows are ever rendered in the displayed report table,
# independent of the LLM entirely. This protects the browser/job-store from
# an extreme dataset (tens of thousands+ rows), not from LLM cost — see
# _build_full_table_markdown for the prioritization logic when this triggers.
MAX_TABLE_ROWS = 1000


def _build_sample(recommendations: list[ItemRecommendation]) -> list[dict]:
    """
    Pick a small, bounded, representative sample of rows to give the LLM as
    *examples* for its analysis — NOT the full dataset. The model never sees
    every row; the KPI summary (computed over ALL rows) carries the totals,
    and the full table is rendered separately in Python (see
    _build_full_table_markdown). This keeps the LLM payload roughly constant
    in size no matter whether there are 50 products or 50,000.

    Priority order, capped at MAX_SAMPLE_ROWS total:
      1. Urgent items (seasonal_warning=True)      — most important to discuss
      2. High-volatility items (cv > 1.0)           — second most important
      3. A small fixed-seed random sample of the rest, for general flavour
    """
    if len(recommendations) <= MAX_SAMPLE_ROWS:
        return [r.to_dict() for r in recommendations]

    urgent = [r for r in recommendations if r.seasonal_warning]
    high   = [r for r in recommendations if not r.seasonal_warning and r.cv > 1.0]

    selected: list[ItemRecommendation] = []
    seen_ids: set[int] = set()

    for bucket in (urgent, high):
        for r in bucket:
            if len(selected) >= MAX_SAMPLE_ROWS:
                break
            if id(r) not in seen_ids:
                selected.append(r)
                seen_ids.add(id(r))
        if len(selected) >= MAX_SAMPLE_ROWS:
            break

    if len(selected) < MAX_SAMPLE_ROWS:
        import random
        rng = random.Random(42)  # fixed seed → same sample every run on the same data
        remaining = [r for r in recommendations if id(r) not in seen_ids]
        rng.shuffle(remaining)
        for r in remaining:
            if len(selected) >= MAX_SAMPLE_ROWS:
                break
            selected.append(r)

    return [r.to_dict() for r in selected]


def _build_full_table_markdown(recommendations: list[ItemRecommendation]) -> str:
    """
    Render the COMPLETE "توصيات المخزون التفصيلية" table for every single
    product — no sampling, no truncation, no LLM involved. Built directly
    from recs_data in Python, so it scales to any dataset size (540 rows or
    5 million rows) at zero extra API cost and zero risk of the model
    skipping, summarizing, or cutting rows off mid-table.

    Includes a display cap (MAX_TABLE_ROWS): if the dataset is larger than
    that, we keep urgent + high-volatility rows first, then fill the rest
    by original order, and add a clear note about how many rows were
    omitted (with guidance to export the full data separately). This is a
    rendering/UX safeguard, not an LLM-cost safeguard — at 1,000 rows the
    table is still only ~80KB of text, well within what a browser table or
    the job-store record can hold comfortably; the cap exists purely so an
    extreme dataset (tens of thousands+ of rows) can't make the report page
    itself unusable.
    """
    if not recommendations:
        return "لا توجد بيانات منتجات."

    has_capital = any(r.capital_tied_up is not None for r in recommendations)

    headers = ["المنتج", "الفرع", "الكمية المتوقعة (90 يوم)", "الكمية الموصى بها"]
    if has_capital:
        headers.append("رأس المال المربوط")
    headers += ["مستوى الأولوية", "مستوى التذبذب"]

    def priority_of(r: ItemRecommendation) -> str:
        if r.seasonal_warning:
            return "عاجل"
        if r.cv > 1.0:
            return "مرتفع"
        if r.cv >= 0.5:
            return "متوسط"
        return "منخفض"

    def volatility_of(r: ItemRecommendation) -> str:
        if r.buffer_pct >= 0.35:
            return "مرتفع"
        if r.buffer_pct >= 0.20:
            return "متوسط"
        return "منخفض"

    total = len(recommendations)
    omitted_note = ""

    if total > MAX_TABLE_ROWS:
        urgent = [r for r in recommendations if r.seasonal_warning]
        high   = [r for r in recommendations if not r.seasonal_warning and r.cv > 1.0]
        priority_ids = {id(r) for r in urgent} | {id(r) for r in high}
        rest = [r for r in recommendations if id(r) not in priority_ids]

        rows_to_show = (urgent + high)[:MAX_TABLE_ROWS]
        remaining_slots = MAX_TABLE_ROWS - len(rows_to_show)
        if remaining_slots > 0:
            rows_to_show += rest[:remaining_slots]

        omitted = total - len(rows_to_show)
        omitted_note = (
            f"\n\n> ⚠️ تنبيه: يحتوي مجموع البيانات على {total:,} منتج. لعرض تقرير سريع وقابل "
            f"للتصفح، يُظهر هذا الجدول أهم {len(rows_to_show):,} منتج (كل المنتجات العاجلة ومرتفعة "
            f"التذبذب أولاً، ثم عيّنة من الباقي) — تم استبعاد {omitted:,} منتج من العرض هنا. "
            f"لمراجعة كل المنتجات دون استثناء، يُرجى تصدير البيانات الكاملة (CSV/Excel) من الواجهة."
        )
    else:
        rows_to_show = recommendations

    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for r in rows_to_show:
        row = [
            str(r.item),
            str(r.store),
            f"{r.forecast_90d:,.0f}",
            f"{r.recommended_stock:,.0f}",
        ]
        if has_capital:
            row.append(f"{r.capital_tied_up:,.0f}" if r.capital_tied_up is not None else "—")
        row += [priority_of(r), volatility_of(r)]
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines) + omitted_note


def _build_user_message(
    recommendations: list[ItemRecommendation],
    drift_report: DriftReport,
    extra_context: str,
) -> str:

    sample_data    = _build_sample(recommendations)
    is_full_data   = len(sample_data) == len(recommendations)

    # Data quality section (renamed from "drift")
    if drift_report.has_drift:
        drift_section = (
            "\n\nDATA QUALITY WARNINGS (mention these clearly in the تحذيرات جودة البيانات section):\n"
            + "\n".join(f"- {a}" for a in drift_report.alerts)
        )
    elif drift_report.skipped_reason:
        drift_section = f"\n\nData quality check: skipped — {drift_report.skipped_reason}"
    else:
        drift_section = "\n\nData quality check: No issues detected."

    kpi_section = _build_kpi_summary(recommendations)

    message = (
        f"Generate the analytical sections of an Arabic inventory report.\n"
        f"Total products in the full dataset: {len(recommendations)}\n"
    )

    if is_full_data:
        message += (
            "The data below contains ALL products (the dataset is small enough to include in full).\n"
        )
    else:
        message += (
            f"IMPORTANT: The {len(sample_data)} rows below are a SAMPLE only "
            f"(urgent + high-volatility items, plus a small random sample of the rest) — "
            f"NOT the full {len(recommendations)}-product dataset. Use them only as concrete examples "
            f"to illustrate points; for any totals, percentages, or counts, use ONLY the numbers in "
            f"'ملخص المؤشرات' below, which were computed over the complete dataset.\n"
            f"Do NOT write the detailed product-by-product table yourself — it is generated separately "
            f"and appended automatically after your text.\n"
        )

    message += (
        f"NOTE: All warning_message fields in the data are already in Arabic — use them as-is.\n"
        f"\nملخص المؤشرات (use these exact aggregate numbers in your executive summary and highlights — "
        f"do not recompute, do not invent other totals):\n{kpi_section}\n"
    )

    if extra_context:
        message += f"\nAdditional context: {extra_context}\n"

    sample_label = "Full recommendations data (JSON)" if is_full_data else "Sample recommendations data (JSON) — examples only, see note above"
    message += f"\n{sample_label}:\n{json.dumps(sample_data, ensure_ascii=False, indent=2)}"
    message += drift_section
    message += "\n\nWrite the analytical sections now, in the exact order specified in the system prompt, then stop."

    return message


# ── KPI aggregation ───────────────────────────────────────────────────────────

def _build_kpi_summary(recommendations: list[ItemRecommendation]) -> str:
    """
    Pre-compute aggregate numbers so the LLM analyzes/uses them instead of
    inventing or skipping over them. Includes financial impact when unit_price
    is available.
    """
    total = len(recommendations)
    if total == 0:
        return "- لا توجد بيانات منتجات."

    urgent = [r for r in recommendations if r.seasonal_warning]
    high   = [r for r in recommendations if not r.seasonal_warning and r.cv > 1.0]
    medium = [r for r in recommendations if not r.seasonal_warning and 0.5 <= r.cv <= 1.0]
    low    = [r for r in recommendations if not r.seasonal_warning and r.cv < 0.5]

    total_recommended_stock  = sum(r.recommended_stock for r in recommendations)
    urgent_recommended_stock = sum(r.recommended_stock for r in urgent)

    # Branch with the most urgent items
    branch_urgent_counts: dict[str, int] = {}
    for r in urgent:
        key = str(r.store)
        branch_urgent_counts[key] = branch_urgent_counts.get(key, 0) + 1
    top_branch       = max(branch_urgent_counts, key=branch_urgent_counts.get) if branch_urgent_counts else None
    top_branch_count = branch_urgent_counts.get(top_branch, 0) if top_branch else 0

    pct = lambda n: round((n / total) * 100, 1)

    lines = [
        f"- إجمالي عدد المنتجات: {total}",
        f"- عاجل (seasonal_warning): {len(urgent)} منتج ({pct(len(urgent))}%)",
        f"- مرتفع التذبذب (cv>1.0): {len(high)} منتج ({pct(len(high))}%)",
        f"- متوسط التذبذب (0.5<=cv<=1.0): {len(medium)} منتج ({pct(len(medium))}%)",
        f"- منخفض التذبذب (cv<0.5): {len(low)} منتج ({pct(len(low))}%)",
        f"- إجمالي الكمية الموصى بطلبها (كل المنتجات): {total_recommended_stock:,.0f} وحدة",
        f"- إجمالي الكمية الموصى بطلبها للمنتجات العاجلة فقط: {urgent_recommended_stock:,.0f} وحدة",
    ]
    if top_branch:
        lines.append(
            f"- الفرع الأكثر تأثرًا بالحالات العاجلة: {top_branch} "
            f"({top_branch_count} من {len(urgent)} حالة عاجلة)"
        )

    # ── Financial KPIs (only when unit_price was provided) ───────────────────
    recs_with_price = [r for r in recommendations if r.capital_tied_up is not None]
    if recs_with_price:
        total_capital        = sum(r.capital_tied_up    for r in recs_with_price)
        total_safety_value   = sum(r.safety_stock_value for r in recs_with_price if r.safety_stock_value is not None)
        urgent_capital       = sum(r.capital_tied_up    for r in urgent          if r.capital_tied_up is not None)
        unit_price_sample    = recs_with_price[0].unit_price  # same price for all

        lines += [
            "",
            "── الأثر المالي (بناءً على سعر الوحدة المُدخل) ──",
            f"- سعر الوحدة المُستخدم في الحساب: {unit_price_sample:,.2f}",
            f"- إجمالي رأس المال المربوط في المخزون الموصى به: {total_capital:,.0f}",
            f"- قيمة الهامش الأمني (safety stock): {total_safety_value:,.0f} "
            f"(تكلفة الحماية من نفاد المخزون)",
            f"- رأس المال في المنتجات العاجلة فقط: {urgent_capital:,.0f}",
        ]

    return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_openrouter_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise ReportGeneratorError("OPENROUTER_API_KEY environment variable is not set.")
    return key


class ReportGeneratorError(Exception):
    """Raised when the Report LLM call fails."""