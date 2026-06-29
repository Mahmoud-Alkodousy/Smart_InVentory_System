import React, { useState, useEffect, useCallback, useRef } from 'react'
import FileUpload from './components/FileUpload'
import ForecastDashboard from './components/ForecastDashboard'
import ForecastTimeline from './components/ForecastTimeline'
import InventoryReport from './components/InventoryReport'
import DriftAlert from './components/DriftAlert'
import MonitoringSetup from './components/MonitoringSetup'
import PipelineDiagram from './components/PipelineDiagram'
import BusinessDashboard from './components/BusinessDashboard'

/* ── Demo Mode mock data ───────────────────────────────────────────────────── */
const DEMO_DATA = {
  route: 'direct', n_rows: 9125, n_stores: 3, n_items: 12,
  date_min: '2022-01-01', date_max: '2024-12-31', warnings: [],
  recommendations: [
    { store:1, item:1,  forecast_90d:2160, forecast_90d_low:1890, forecast_90d_high:2450, avg_daily_demand:24.0, cv:0.32, buffer_pct:0.20, recommended_stock:2940, reorder_point:168, seasonal_warning:false, warning_message:'', unit_price:85,  capital_tied_up:249900, safety_stock_value:66300, current_stock:3800, excess_units:860,  savings_value:73100, service_level_pct:93, supplier:'شركة الدلتا للتوريدات', supplier_lead_time_days:4 },
    { store:1, item:2,  forecast_90d:1440, forecast_90d_low:1200, forecast_90d_high:1680, avg_daily_demand:16.0, cv:0.18, buffer_pct:0.10, recommended_stock:1848, reorder_point:112, seasonal_warning:false, warning_message:'', unit_price:120, capital_tied_up:221760, safety_stock_value:49440, current_stock:2600, excess_units:752,  savings_value:90240, service_level_pct:87, supplier:'مصنع النور', supplier_lead_time_days:10 },
    { store:1, item:3,  forecast_90d:3600, forecast_90d_low:2800, forecast_90d_high:4200, avg_daily_demand:40.0, cv:0.61, buffer_pct:0.35, recommended_stock:5670, reorder_point:280, seasonal_warning:true,  warning_message:'يبلغ هذا المنتج ذروته تاريخياً في الربع الرابع (أكتوبر–ديسمبر) (68% من المبيعات السنوية). يُنصح بتوفير مخزون إضافي قبل هذه الفترة.', unit_price:45, capital_tied_up:255150, safety_stock_value:94050, current_stock:6200, excess_units:530,  savings_value:23850, service_level_pct:97.5, supplier:'الفجر للاستيراد', supplier_lead_time_days:18, event_tags:['شهر رمضان'], event_buffer_units:320, event_note:'يقع جزء من فترة التوقع ضمن: شهر رمضان. يُقترح هامش إضافي قدره 320 وحدة (زيادة طلب متوقعة +40%).', recommended_stock_with_events:5990 },
    { store:1, item:4,  forecast_90d:720,  forecast_90d_low:600,  forecast_90d_high:840,  avg_daily_demand:8.0,  cv:0.24, buffer_pct:0.20, recommended_stock:1008, reorder_point:56,  seasonal_warning:false, warning_message:'', unit_price:200, capital_tied_up:201600, safety_stock_value:57600, current_stock:900,  excess_units:0,    savings_value:0,     service_level_pct:93, supplier:'شركة الدلتا للتوريدات', supplier_lead_time_days:4 },
    { store:2, item:1,  forecast_90d:1800, forecast_90d_low:1550, forecast_90d_high:2050, avg_daily_demand:20.0, cv:0.29, buffer_pct:0.20, recommended_stock:2460, reorder_point:140, seasonal_warning:false, warning_message:'', unit_price:85,  capital_tied_up:209100, safety_stock_value:55500, current_stock:3100, excess_units:640,  savings_value:54400, service_level_pct:93, supplier:'شركة الدلتا للتوريدات', supplier_lead_time_days:4 },
    { store:2, item:2,  forecast_90d:900,  forecast_90d_low:750,  forecast_90d_high:1050, avg_daily_demand:10.0, cv:0.17, buffer_pct:0.10, recommended_stock:1155, reorder_point:70,  seasonal_warning:false, warning_message:'', unit_price:120, capital_tied_up:138600, safety_stock_value:30600, current_stock:300,  excess_units:0,    savings_value:0,     service_level_pct:87, supplier:'مصنع النور', supplier_lead_time_days:10 },
    { store:2, item:5,  forecast_90d:2700, forecast_90d_low:2200, forecast_90d_high:3100, avg_daily_demand:30.0, cv:0.55, buffer_pct:0.35, recommended_stock:4185, reorder_point:210, seasonal_warning:true,  warning_message:'يبلغ هذا المنتج ذروته تاريخياً في الربع الثاني (أبريل–يونيو) (52% من المبيعات السنوية). يُنصح بتوفير مخزون إضافي قبل هذه الفترة.', unit_price:30, capital_tied_up:125550, safety_stock_value:44550, current_stock:4500, excess_units:315,  savings_value:9450,  service_level_pct:97.5, supplier:'الفجر للاستيراد', supplier_lead_time_days:18 },
    { store:2, item:6,  forecast_90d:540,  forecast_90d_low:450,  forecast_90d_high:630,  avg_daily_demand:6.0,  cv:0.14, buffer_pct:0.10, recommended_stock:693,  reorder_point:42,  seasonal_warning:false, warning_message:'', unit_price:350, capital_tied_up:242550, safety_stock_value:53550, current_stock:700,  excess_units:7,    savings_value:2450,  service_level_pct:87, supplier:'مصنع النور', supplier_lead_time_days:10 },
    { store:3, item:7,  forecast_90d:4500, forecast_90d_low:3800, forecast_90d_high:5100, avg_daily_demand:50.0, cv:0.42, buffer_pct:0.20, recommended_stock:6120, reorder_point:350, seasonal_warning:false, warning_message:'', unit_price:15,  capital_tied_up:91800,  safety_stock_value:24300, current_stock:6000, excess_units:0,    savings_value:0,     service_level_pct:93, supplier:'توريدات الإسكندرية', supplier_lead_time_days:3 },
    { store:3, item:8,  forecast_90d:1080, forecast_90d_low:900,  forecast_90d_high:1260, avg_daily_demand:12.0, cv:0.22, buffer_pct:0.20, recommended_stock:1512, reorder_point:84,  seasonal_warning:false, warning_message:'', unit_price:75,  capital_tied_up:113400, safety_stock_value:32400, current_stock:2200, excess_units:688,  savings_value:51600, service_level_pct:93, supplier:'مصنع النور', supplier_lead_time_days:10 },
    { store:3, item:9,  forecast_90d:360,  forecast_90d_low:280,  forecast_90d_high:440,  avg_daily_demand:4.0,  cv:0.78, buffer_pct:0.35, recommended_stock:594,  reorder_point:28,  seasonal_warning:true,  warning_message:'يبلغ هذا المنتج ذروته تاريخياً في الربع الأول (يناير–مارس) (61% من المبيعات السنوية).', unit_price:500, capital_tied_up:297000, safety_stock_value:117000, current_stock:700, excess_units:106, savings_value:53000, service_level_pct:97.5, supplier:'الفجر للاستيراد', supplier_lead_time_days:25, event_tags:['عيد الأضحى'], event_buffer_units:45, event_note:'يقع جزء من فترة التوقع ضمن: عيد الأضحى. يُقترح هامش إضافي قدره 45 وحدة (زيادة طلب متوقعة +30%).', recommended_stock_with_events:639 },
    { store:3, item:10, forecast_90d:810,  forecast_90d_low:700,  forecast_90d_high:920,  avg_daily_demand:9.0,  cv:0.31, buffer_pct:0.20, recommended_stock:1104, reorder_point:63,  seasonal_warning:false, warning_message:'', unit_price:60,  capital_tied_up:66240,  safety_stock_value:17640, current_stock:1200, excess_units:96,   savings_value:5760,  service_level_pct:93, supplier:'توريدات الإسكندرية', supplier_lead_time_days:3 },
  ],
  suppliers: [
    { supplier:'الفجر للاستيراد', items_supplied:['3','5','9'], n_items:3, avg_lead_time_days:20.3, max_lead_time_days:25, risk_score:72.7, risk_level:'high', risk_level_ar:'مرتفع', value_exposed:677700, high_volatility_items:3, recommendation:'مدة توريد مرتفعة (20 يوم) — يُنصح بالبحث عن مورد بديل أسرع أو رفع المخزون الآمن لهذا المورد.' },
    { supplier:'مصنع النور', items_supplied:['2','6','8'], n_items:3, avg_lead_time_days:10, max_lead_time_days:10, risk_score:42.2, risk_level:'medium', risk_level_ar:'متوسط', value_exposed:716310, high_volatility_items:0, recommendation:'مدة توريد متوسطة (10 يوم) — راقب هذا المورد عند اقتراب موسم الذروة.' },
    { supplier:'شركة الدلتا للتوريدات', items_supplied:['1','4'], n_items:2, avg_lead_time_days:4, max_lead_time_days:4, risk_score:16, risk_level:'low', risk_level_ar:'منخفض', value_exposed:660600, high_volatility_items:0, recommendation:'مدة توريد جيدة (4 يوم) — مخاطر منخفضة.' },
    { supplier:'توريدات الإسكندرية', items_supplied:['7','10'], n_items:2, avg_lead_time_days:3, max_lead_time_days:3, risk_score:12, risk_level:'low', risk_level_ar:'منخفض', value_exposed:158040, high_volatility_items:0, recommendation:'مدة توريد جيدة (3 يوم) — مخاطر منخفضة.' },
  ],
  supplier_switches: [
    { item:'3', current_supplier:'الفجر للاستيراد', current_lead_time:18, suggested_supplier:'دلتا السريع', suggested_lead_time:6, days_saved:12 },
  ],
  transfers: [
    { item:'2', from_store:'1', to_store:'2', quantity:567, unit_price:120, value_saved:68040, from_store_stock_before:2600, from_store_stock_after:2033, to_store_stock_before:300, to_store_stock_after:867 },
  ],
  events: [
    { name:'Ramadan (pre-stocking)', name_ar:'تجهيز ما قبل رمضان', category:'religious', start:'2025-02-11', end:'2025-02-17', duration_days:7,  uplift_pct:0.25, days_until:12,  is_ongoing:false },
    { name:'Ramadan',               name_ar:'شهر رمضان',          category:'religious', start:'2025-02-18', end:'2025-03-19', duration_days:30, uplift_pct:0.40, days_until:19,  is_ongoing:false },
    { name:'Eid al-Fitr',           name_ar:'عيد الفطر',          category:'religious', start:'2025-03-20', end:'2025-03-23', duration_days:4,  uplift_pct:0.30, days_until:49,  is_ongoing:false },
    { name:'Back to School',        name_ar:'موسم بداية الدراسة', category:'seasonal',  start:'2025-09-01', end:'2025-09-30', duration_days:30, uplift_pct:0.20, days_until:259, is_ongoing:false },
    { name:'Black Friday',          name_ar:'الجمعة البيضاء (Black Friday)', category:'retail', start:'2025-11-28', end:'2025-12-01', duration_days:4, uplift_pct:0.60, days_until:347, is_ongoing:false },
  ],
}

const API          = import.meta.env.VITE_API_URL || ''
const API_KEY      = import.meta.env.VITE_API_KEY || ''
const POLL_MS      = 3000
const REPORT_RETRY = 5

/* ── Theme toggle button ───────────────────────────── */
function ThemeToggle({ theme, onToggle }) {
  const isDark = theme === 'dark'
  return (
    <button
      onClick={onToggle}
      title={isDark ? 'الوضع الفاتح' : 'الوضع الغامق'}
      style={{
        position: 'relative',
        width: '52px',
        height: '28px',
        borderRadius: '100px',
        background: isDark
          ? 'rgba(56,189,248,0.15)'
          : 'rgba(2,132,199,0.12)',
        border: `1px solid ${isDark ? 'rgba(56,189,248,0.3)' : 'rgba(2,132,199,0.25)'}`,
        cursor: 'pointer',
        padding: 0,
        flexShrink: 0,
        transition: 'all 0.3s ease',
      }}
    >
      {/* Track icons */}
      <span style={{
        position: 'absolute', left: '6px', top: '50%', transform: 'translateY(-50%)',
        fontSize: '11px', opacity: isDark ? 0.4 : 1, transition: 'opacity 0.3s',
        pointerEvents: 'none',
      }}>☀️</span>
      <span style={{
        position: 'absolute', right: '6px', top: '50%', transform: 'translateY(-50%)',
        fontSize: '11px', opacity: isDark ? 1 : 0.4, transition: 'opacity 0.3s',
        pointerEvents: 'none',
      }}>🌙</span>
      {/* Thumb */}
      <span style={{
        position: 'absolute',
        top: '3px',
        left: isDark ? 'calc(100% - 22px)' : '3px',
        width: '20px',
        height: '20px',
        borderRadius: '50%',
        background: isDark
          ? 'linear-gradient(135deg, #38bdf8, #818cf8)'
          : 'linear-gradient(135deg, #fbbf24, #f97316)',
        boxShadow: isDark
          ? '0 0 8px rgba(56,189,248,0.5)'
          : '0 0 8px rgba(251,191,36,0.5)',
        transition: 'left 0.3s cubic-bezier(0.34,1.56,0.64,1), background 0.3s, box-shadow 0.3s',
        pointerEvents: 'none',
      }} />
    </button>
  )
}

/* ─────────────────────────────────────────────────────
   Processing steps — keys match backend STEP_* constants
───────────────────────────────────────────────────── */
const STEPS = [
  { key: 'load',      label: 'تحميل البيانات وفحصها',             icon: '📁' },
  { key: 'clean',     label: 'تشغيل AI Agent لتنظيف البيانات',      icon: '🤖' },
  { key: 'validate',  label: 'التحقق من جودة البيانات وتوحيدها',   icon: '⚙️' },
  { key: 'forecast',  label: 'نموذج Chronos T5 — التنبؤ 90 يوماً', icon: '📈' },
  { key: 'recommend', label: 'توصيات المخزون الديناميكية',          icon: '📦' },
  { key: 'drift',     label: 'فحص انحراف البيانات',                icon: '🔬' },
  { key: 'report',    label: 'توليد التقرير العربي',               icon: '📝' },
]

// Map step key → index
const STEP_INDEX = Object.fromEntries(STEPS.map((s, i) => [s.key, i]))

// Rotating facts shown during processing — keeps the screen alive on longer jobs
const PROCESSING_TIPS = [
  '💡 Chronos T5 موديل متخصص في السلاسل الزمنية — بيتنبأ على بياناتك مباشرة بدون أي تدريب مسبق.',
  '💡 كل منتج بياخد هامش أمان مختلف حسب تذبذب مبيعاته الفعلي — مش رقم ثابت للجميع.',
  '💡 المعالجة بتشتغل في عملية منفصلة (Celery) عشان النظام يفضل سريع مهما طالت المدة.',
  '💡 النظام بيقارن بياناتك الجديدة بإحصائيات سابقة لاكتشاف أي تغيّر مفاجئ في نمط الطلب.',
  '💡 التقرير النهائي هيتكتب بالكامل بلغة عربية فصحى مفهومة لصاحب المحل.',
]

/* ─────────────────────────────────────────────────────
   App
───────────────────────────────────────────────────── */
export default function App() {
  // Screens: upload | processing | results | error
  const [screen,       setScreen]       = useState('upload')
  const [jobId,        setJobId]        = useState(null)
  const [forecastData, setForecastData] = useState(null)
  const [report,       setReport]       = useState(null)
  const [reportLoading,setReportLoading]= useState(false)
  const [reportError,  setReportError]  = useState(null)
  const [drift,        setDrift]        = useState(null)
  const [error,        setError]        = useState(null)
  const [activeTab,    setActiveTab]    = useState('forecast')
  const [elapsed,      setElapsed]      = useState(0)
  const [currentStep,  setCurrentStep]  = useState('load') // real step from backend
  const [tipIdx,       setTipIdx]       = useState(0)

  // Theme
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('theme')
    if (saved) return saved
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])
  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark')

  // Rotate the "did you know" tip every few seconds while processing
  useEffect(() => {
    if (screen !== 'processing') return
    const id = setInterval(
      () => setTipIdx(i => (i + 1) % PROCESSING_TIPS.length),
      4000
    )
    return () => clearInterval(id)
  }, [screen])

  const pollRef           = useRef(null)
  const timerRef          = useRef(null)
  const reportRetryRef    = useRef(0)
  const reportIntervalRef = useRef(null)  // tracked so reset() can clean it up
  const reportDoneRef     = useRef(false) // true once report is received (avoids stale closure)

  const headers = useCallback(
    () => (API_KEY ? { 'X-API-Key': API_KEY } : {}),
    []
  )

  const stopAll = useCallback(() => {
    clearInterval(pollRef.current)
    clearInterval(timerRef.current)
    clearInterval(reportIntervalRef.current)
    reportIntervalRef.current = null
  }, [])

  /* ── Fetch report separately after forecast is done ─
     The backend generates the report in the same job,
     but it may arrive slightly after the forecast data.
     We retry up to REPORT_RETRY times before giving up.
  ─────────────────────────────────────────────────── */
  const fetchReport = useCallback(async (jid) => {
    // Already got the report — stop fetching (avoids stale closure bug)
    if (reportDoneRef.current) {
      clearInterval(reportIntervalRef.current)
      reportIntervalRef.current = null
      return
    }

    try {
      const res = await fetch(`${API}/api/report/${jid}`, { headers: headers() })

      // 404 = not ready yet (backend returns 404 when report key missing)
      if (res.status === 404) {
        reportRetryRef.current += 1
        if (reportRetryRef.current >= REPORT_RETRY) {
          reportDoneRef.current = true
          clearInterval(reportIntervalRef.current)
          reportIntervalRef.current = null
          setReportLoading(false)
          setReportError('تعذّر توليد التقرير. تحقق من إعداد OPENROUTER_API_KEY أو OLLAMA.')
        }
        return
      }

      if (!res.ok) {
        reportDoneRef.current = true
        clearInterval(reportIntervalRef.current)
        reportIntervalRef.current = null
        setReportLoading(false)
        setReportError(`خطأ في توليد التقرير (HTTP ${res.status})`)
        return
      }

      const data = await res.json()

      // Still processing (shouldn't happen since forecast is done, but just in case)
      if (data.status === 'processing') return

      if (data.report) {
        reportDoneRef.current = true
        clearInterval(reportIntervalRef.current)
        reportIntervalRef.current = null
        setReport(data.report)
        setReportLoading(false)
        setReportError(null)
      } else {
        reportRetryRef.current += 1
        if (reportRetryRef.current >= REPORT_RETRY) {
          reportDoneRef.current = true
          clearInterval(reportIntervalRef.current)
          reportIntervalRef.current = null
          setReportLoading(false)
          setReportError('تعذّر توليد التقرير التلقائي.')
        }
      }
    } catch {
      // Network error — retry handled by interval
    }
  }, [headers])

  /* ── Main polling loop ─────────────────────────── */
  const fetchResults = useCallback(async (jid) => {
    try {
      const res = await fetch(`${API}/api/forecast/${jid}`, { headers: headers() })
      if (!res.ok) return
      const data = await res.json()

      if (data.status === 'processing') {
        if (data.current_step) setCurrentStep(data.current_step)
        return   // keep polling
      }

      if (data.status === 'failed') {
        stopAll()
        setError({ message: data.error, attempts: data.attempt_errors || [] })
        setScreen('error')
        return
      }

      // ── Done: stop main poll, switch to results ──
      stopAll()
      setForecastData(data)
      setScreen('results')

      // Fetch drift (fire-and-forget, no retry needed)
      fetch(`${API}/api/drift/${jid}`, { headers: headers() })
        .then(r => r.ok ? r.json() : null)
        .then(d => { if (d?.drift) setDrift(d.drift) })
        .catch(() => {})

      // Start report polling (separate interval, slower)
      reportRetryRef.current = 0
      reportDoneRef.current  = false
      fetchReport(jid)
      reportIntervalRef.current = setInterval(() => {
        // reportDoneRef checked inside fetchReport itself — no stale closure issue
        fetchReport(jid)
      }, 4000)

    } catch {
      // Network error — keep polling
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stopAll, fetchReport, headers])

  /* ── Start a new job ─────────────────────────── */
  const startJob = useCallback((jid) => {
    stopAll()
    setJobId(jid)
    setScreen('processing')
    setElapsed(0)
    setForecastData(null)
    setReport(null)
    setDrift(null)
    setError(null)
    setReportLoading(true)
    setReportError(null)
    setActiveTab('forecast')
    reportRetryRef.current = 0

    setCurrentStep('load')
    reportDoneRef.current  = false
    reportRetryRef.current = 0
    timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000)
    pollRef.current  = setInterval(() => fetchResults(jid), POLL_MS)
    fetchResults(jid)
  }, [stopAll, fetchResults])

  /* ── Demo Mode ─────────────────────────────── */
  const handleDemoMode = useCallback(() => {
    stopAll()
    setForecastData(DEMO_DATA)
    setReport('📊 **Demo Mode** — البيانات الموضحة هي بيانات تجريبية واقعية تُظهر قدرات النظام الكاملة.\n\nتشمل التوصيات 12 صنفاً عبر 3 فروع، مع تحليل ABC، وحساب الوفر المالي، ومحاكاة What-If، وتحليل مخاطر الموردين، واقتراحات نقل المخزون بين الفروع، وتأثير الأحداث الموسمية (رمضان/الأعياد)، وإصدار أمر شراء تلقائي.')
    setDrift({ has_drift: false, n_drifted: 0, total_checked: 5, alerts: [], summary: 'لا يوجد انحراف ملحوظ في البيانات التجريبية.', skipped_reason: '', feature_details: [] })
    setScreen('results')
    setActiveTab('business')
    setReportLoading(false)
    setReportError(null)
    setError(null)
    setJobId(null)
  }, [stopAll])

  /* ── Reset ──────────────────────────────────── */
  const reset = useCallback(() => {
    stopAll()
    reportDoneRef.current  = false
    reportRetryRef.current = 0
    setScreen('upload')
    setJobId(null)
    setForecastData(null)
    setReport(null)
    setDrift(null)
    setError(null)
    setElapsed(0)
    setCurrentStep('load')
    setReportLoading(false)
    setReportError(null)
    setActiveTab('forecast')
  }, [stopAll])

  useEffect(() => () => stopAll(), [stopAll])

  /* ── Active step (real — from backend) ──────── */
  const activeStep = STEP_INDEX[currentStep] ?? 0

  /* ── Render ─────────────────────────────────── */
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)', position: 'relative', overflow: 'hidden' }}>
      {/* Background decoration */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0,
        backgroundImage: `
          linear-gradient(rgba(56,189,248,0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(56,189,248,0.03) 1px, transparent 1px)
        `,
        backgroundSize: '48px 48px',
      }} />
      <div style={{
        position: 'fixed', top: '-30vh', right: '-15vw', width: '700px', height: '700px',
        background: 'radial-gradient(circle, rgba(56,189,248,0.07) 0%, transparent 65%)',
        pointerEvents: 'none', zIndex: 0,
      }} />
      <div style={{
        position: 'fixed', bottom: '-20vh', left: '-10vw', width: '500px', height: '500px',
        background: 'radial-gradient(circle, rgba(129,140,248,0.05) 0%, transparent 65%)',
        pointerEvents: 'none', zIndex: 0,
      }} />

      {/* ── Navbar ───────────────────────────── */}
      <nav style={{
        position: 'sticky', top: 0, zIndex: 100,
        background: 'var(--bg-glass)', backdropFilter: 'blur(20px)',
        borderBottom: '1px solid var(--border)',
        padding: '0 2rem', height: '60px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Logo SVG — gradient demand bars rising into a forecast trend line */}
          <svg width="40" height="34" viewBox="0 0 40 34" fill="none" xmlns="http://www.w3.org/2000/svg">
            <style>{`
              @keyframes barRise {
                from { transform: scaleY(0); }
                to   { transform: scaleY(1); }
              }
              .bbar { transform-origin: bottom; animation: barRise 0.6s cubic-bezier(0.22,1,0.36,1) backwards; }
            `}</style>
            <rect className="bbar" x="2"  y="18" width="6" height="12" rx="1.5" fill="var(--accent-deep)" style={{ animationDelay: '0ms' }} />
            <rect className="bbar" x="11" y="10" width="6" height="20" rx="1.5" fill="var(--accent-deep)" style={{ animationDelay: '70ms' }} />
            <rect className="bbar" x="20" y="14" width="6" height="16" rx="1.5" fill="var(--accent)" style={{ animationDelay: '140ms' }} />
            <rect className="bbar" x="29" y="2"  width="6" height="28" rx="1.5" fill="var(--accent-2)" style={{ animationDelay: '210ms' }} />
            <path
              d="M5 16 L14 8 L23 12 L32 1"
              stroke="var(--success)"
              strokeWidth="1.4"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {[[5,16],[14,8],[23,12],[32,1]].map(([cx,cy],i) => (
              <circle key={i} cx={cx} cy={cy} r="1.5" fill="var(--success)" />
            ))}
          </svg>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {screen === 'processing' && (
            <>
              <span style={{ position: 'relative', display: 'inline-flex' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--accent)', display: 'block' }} />
                <span style={{ position: 'absolute', inset: 0, borderRadius: '50%', background: 'var(--accent)', animation: 'ping 1.5s cubic-bezier(0,0,0.2,1) infinite' }} />
              </span>
              <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                معالجة... {elapsed}ث
              </span>
            </>
          )}
          {screen === 'results' && (
            <>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--success)', display: 'block' }} />
              <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>اكتملت المعالجة</span>
            </>
          )}
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
          <button
            onClick={() => setScreen('how-it-works')}
            style={{
              background: screen === 'how-it-works'
                ? 'linear-gradient(135deg, var(--accent), var(--accent-2))'
                : 'var(--bg-card)',
              border: screen === 'how-it-works' ? 'none' : '1px solid var(--border)',
              borderRadius: 'var(--r-sm)',
              color: screen === 'how-it-works' ? '#fff' : 'var(--text-secondary)',
              fontSize: '0.8rem', fontWeight: 700,
              padding: '6px 14px', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '6px',
              fontFamily: 'var(--font-ar)',
              boxShadow: screen === 'how-it-works' ? '0 2px 12px var(--accent-glow)' : 'none',
              transition: 'all 0.2s ease',
            }}
          >
            <span style={{ fontSize: '0.9rem' }}>🧭</span>
            كيف يعمل النظام
          </button>
          <button
            onClick={() => setScreen('monitoring')}
            style={{
              background: screen === 'monitoring'
                ? 'linear-gradient(135deg, var(--accent), var(--accent-2))'
                : 'var(--bg-card)',
              border: screen === 'monitoring' ? 'none' : '1px solid var(--border)',
              borderRadius: 'var(--r-sm)',
              color: screen === 'monitoring' ? '#fff' : 'var(--text-secondary)',
              fontSize: '0.8rem', fontWeight: 700,
              padding: '6px 14px', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '6px',
              fontFamily: 'var(--font-ar)',
              boxShadow: screen === 'monitoring' ? '0 2px 12px var(--accent-glow)' : 'none',
              transition: 'all 0.2s ease',
            }}
          >
            <span style={{ fontSize: '0.9rem' }}>📬</span>
            إشعارات تلقائية
          </button>
          {screen !== 'upload' && (
            <button onClick={reset} style={{
              padding: '6px 14px', borderRadius: 'var(--r-sm)',
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              color: 'var(--text-secondary)', fontSize: '0.8rem', fontWeight: 600,
              fontFamily: 'var(--font-ar)',
            }}>
              ↩ تحليل جديد
            </button>
          )}
        </div>
      </nav>

      {/* ── Main content ─────────────────────── */}
      <main style={{ position: 'relative', zIndex: 1, maxWidth: '1320px', margin: '0 auto', padding: '2rem' }}>

        {/* ── How it works screen ───────────── */}
        {screen === 'how-it-works' && (
          <div style={{ maxWidth: '760px', margin: '0 auto' }}>
            <PipelineDiagram />
            <div style={{ marginTop: '1.5rem', textAlign: 'center' }}>
              <button onClick={() => setScreen('upload')} style={{
                padding: '8px 20px', borderRadius: 'var(--r-sm)',
                background: 'var(--bg-card)', border: '1px solid var(--border)',
                color: 'var(--text-secondary)', fontSize: '0.85rem', fontWeight: 600,
                fontFamily: 'var(--font-ar)', cursor: 'pointer',
              }}>
                ↩ رجوع لرفع البيانات
              </button>
            </div>
          </div>
        )}

        {/* ── Monitoring screen ──────────────── */}
        {screen === 'monitoring' && (
          <MonitoringSetup onBack={() => setScreen('upload')} />
        )}

        {/* ── Upload screen ─────────────────── */}
        {screen === 'upload' && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '3rem',
            alignItems: 'center',
            minHeight: 'calc(100vh - 100px)',
            padding: '2rem 0',
            animation: 'fadeUp 0.5s ease forwards',
          }}>

            {/* ── Left: Hero ───────────────────── */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>

              {/* Badge */}
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', width: 'fit-content',
                padding: '5px 16px', borderRadius: '100px',
                background: 'rgba(56,189,248,0.08)', border: '1px solid rgba(56,189,248,0.22)',
                color: 'var(--accent)', fontSize: '0.78rem', fontWeight: 700, letterSpacing: '0.06em',
              }}>
                ✨ مدعوم بالذكاء الاصطناعي
              </div>

              {/* Headline */}
              <div>
                <h1 style={{
                  fontSize: 'clamp(2rem, 3.5vw, 3rem)', fontWeight: 900,
                  color: 'var(--text-primary)', lineHeight: 1.15, letterSpacing: '-0.03em',
                  marginBottom: '1rem',
                }}>
                  توقّع الطلب،{'\n'}
                  <span style={{
                    color: 'var(--accent)',
                    textShadow: '0 0 40px rgba(56,189,248,0.4)',
                  }}>خطّط مخزونك</span>
                </h1>
                <p style={{ fontSize: '1rem', color: 'var(--text-secondary)', lineHeight: 1.8 }}>
                  توقعات دقيقة حتى 90 يوماً <span style={{ color: 'var(--accent)', fontWeight: 700 }}>+</span> توصيات مخزون ذكية <span style={{ color: 'var(--accent)', fontWeight: 700 }}>+</span> تقرير عربي مفصّل.
                </p>
              </div>

              {/* Live stats row */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
                {[
                  { value: '90', unit: 'يوم', label: 'توقع مستقبلي', color: 'var(--accent)' },
                  { value: '< 2', unit: 'دقيقة', label: 'وقت التحليل', color: 'var(--success)' },
                  { value: '100%', unit: '', label: 'تقرير عربي', color: 'var(--accent-2)' },
                ].map(({ value, unit, label, color }) => (
                  <div key={label} style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--r-md)',
                    padding: '14px 12px',
                    textAlign: 'center',
                  }}>
                    <div style={{ fontSize: '1.5rem', fontWeight: 900, color, lineHeight: 1 }}>
                      {value}<span style={{ fontSize: '0.75rem', fontWeight: 500, marginRight: '2px' }}>{unit}</span>
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>{label}</div>
                  </div>
                ))}
              </div>

              {/* Feature list */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {[
                  { icon: '📈', title: 'Chronos T5 للتنبؤ', desc: 'نموذج AI متخصص بتوقع السلاسل الزمنية' },
                  { icon: '🤖', title: 'إصلاح بيانات تلقائي', desc: 'AI Agent يكتشف ويصلح مشاكل البيانات' },
                  { icon: '📝', title: 'تقرير عربي فوري', desc: 'تقرير تفصيلي مكتوب بالعربية لصانع القرار' },
                  { icon: '🔬', title: 'كشف انحراف البيانات', desc: 'تنبيهات فورية عند تغير سلوك المبيعات' },
                  { icon: '📬', title: 'متابعة تلقائية بالإيميل', desc: 'إشعار أسبوعي أو شهري بحالة مخزونك' },
                ].map(f => (
                  <div key={f.title} style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                    <span style={{
                      width: '34px', height: '34px', borderRadius: 'var(--r-sm)',
                      background: 'rgba(56,189,248,0.08)', border: '1px solid rgba(56,189,248,0.15)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '1rem', flexShrink: 0,
                    }}>{f.icon}</span>
                    <div>
                      <p style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '1px' }}>{f.title}</p>
                      <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{f.desc}</p>
                    </div>
                  </div>
                ))}
              </div>

              {/* CTA for monitoring */}
              <button
                onClick={() => setScreen('monitoring')}
                style={{
                  display: 'flex', alignItems: 'center', gap: '10px',
                  padding: '13px 20px', borderRadius: 'var(--r-md)',
                  background: 'rgba(129,140,248,0.08)',
                  border: '1px solid rgba(129,140,248,0.25)',
                  color: 'var(--accent-2)', fontSize: '0.88rem', fontWeight: 700,
                  cursor: 'pointer', fontFamily: 'var(--font-ar)',
                  transition: 'all 0.2s ease',
                  width: '100%', justifyContent: 'center',
                }}
              >
                <span style={{ fontSize: '1.1rem' }}>📬</span>
                فعّل المتابعة التلقائية — اشترك بإيميلك مجاناً
                <span style={{ fontSize: '0.75rem', opacity: 0.7, marginRight: 'auto' }}>←</span>
              </button>
            </div>

            {/* ── Right: Upload panel ──────────── */}
            <div style={{
              background: 'var(--bg-panel)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--r-xl)',
              padding: '2rem',
              boxShadow: 'none',
              animation: 'borderPulse 3s ease-in-out infinite',
              display: 'flex',
              flexDirection: 'column',
              gap: '0',
            }}>
              {/* Panel header */}
              <div style={{ marginBottom: '1.4rem' }}>
                <h2 style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                  رفع بيانات المبيعات
                </h2>
                <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  اختر مصدر البيانات وابدأ التحليل خلال ثوانٍ
                </p>
              </div>

              <FileUpload onJobStart={startJob} onDemoMode={handleDemoMode} />
            </div>

          </div>
        )}

        {/* ── Processing screen ─────────────── */}
        {screen === 'processing' && (
          <div style={{ maxWidth: '660px', margin: '2.5rem auto', animation: 'fadeUp 0.5s ease forwards' }}>
            {/* ── Outer glow wrapper */}
            <div style={{
              position: 'relative',
              borderRadius: '24px',
              padding: '2px',
              background: `linear-gradient(135deg, rgba(56,189,248,0.5), rgba(129,140,248,0.4), rgba(52,211,153,0.3))`,
              boxShadow: '0 0 60px rgba(56,189,248,0.15), 0 0 100px rgba(129,140,248,0.08)',
              animation: 'borderGlow 3s ease-in-out infinite',
            }}>
              {/* ── Inner card */}
              <div style={{
                background: theme === 'dark'
                  ? 'linear-gradient(160deg, #0d1626 0%, #0a1020 60%, #0d1830 100%)'
                  : 'var(--bg-card)',
                borderRadius: '22px',
                padding: '0',
                overflow: 'hidden',
                position: 'relative',
              }}>

                {/* ── Subtle grid background */}
                <div style={{
                  position: 'absolute', inset: 0, pointerEvents: 'none',
                  backgroundImage: `
                    linear-gradient(rgba(56,189,248,0.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(56,189,248,0.03) 1px, transparent 1px)
                  `,
                  backgroundSize: '32px 32px',
                  maskImage: 'radial-gradient(ellipse 80% 80% at 50% 50%, black 40%, transparent 100%)',
                }} />

                {/* ── Top ambient glow orbs */}
                <div style={{
                  position: 'absolute', top: '-60px', left: '15%',
                  width: '200px', height: '200px', borderRadius: '50%',
                  background: 'radial-gradient(circle, rgba(56,189,248,0.12) 0%, transparent 70%)',
                  pointerEvents: 'none',
                }} />
                <div style={{
                  position: 'absolute', top: '-40px', right: '20%',
                  width: '150px', height: '150px', borderRadius: '50%',
                  background: 'radial-gradient(circle, rgba(129,140,248,0.10) 0%, transparent 70%)',
                  pointerEvents: 'none',
                }} />

                {/* ── Header bar */}
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '1rem 1.6rem',
                  borderBottom: '1px solid rgba(56,189,248,0.08)',
                  background: 'rgba(56,189,248,0.03)',
                  position: 'relative', zIndex: 1,
                }}>
                  {/* Traffic lights */}
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    {['#f87171','#fbbf24','#34d399'].map((c,i) => (
                      <div key={i} style={{
                        width: '10px', height: '10px', borderRadius: '50%',
                        background: c, opacity: 0.7,
                      }} />
                    ))}
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
                      color: 'rgba(56,189,248,0.4)', marginRight: '8px', letterSpacing: '0.05em',
                    }}>inventory-ai.process</span>
                  </div>
                  {/* Timer */}
                  <div style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
                    color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: '6px',
                    background: 'rgba(56,189,248,0.06)', padding: '3px 10px', borderRadius: '20px',
                    border: '1px solid rgba(56,189,248,0.15)',
                  }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#34d399', display: 'inline-block', animation: 'pulse 1.5s ease-in-out infinite' }} />
                    {elapsed}ث
                  </div>
                </div>

                {/* ── Main content */}
                <div style={{ padding: '1.8rem 2rem 2rem', position: 'relative', zIndex: 1 }}>

                  {/* ── Progress arc + percentage */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1.4rem', marginBottom: '1.8rem', direction: 'rtl' }}>
                    {/* Circular progress */}
                    <div style={{ position: 'relative', flexShrink: 0 }}>
                      <svg width="72" height="72" viewBox="0 0 72 72" style={{ transform: 'rotate(-90deg)' }}>
                        <circle cx="36" cy="36" r="30" fill="none" stroke="rgba(56,189,248,0.08)" strokeWidth="4" />
                        <circle
                          cx="36" cy="36" r="30" fill="none"
                          stroke="url(#progGrad)" strokeWidth="4"
                          strokeLinecap="round"
                          strokeDasharray={`${2 * Math.PI * 30}`}
                          strokeDashoffset={`${2 * Math.PI * 30 * (1 - activeStep / Math.max(1, STEPS.length - 1))}`}
                          style={{ transition: 'stroke-dashoffset 0.8s cubic-bezier(0.4,0,0.2,1)' }}
                        />
                        <defs>
                          <linearGradient id="progGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" stopColor="#38bdf8" />
                            <stop offset="100%" stopColor="#818cf8" />
                          </linearGradient>
                        </defs>
                      </svg>
                      <div style={{
                        position: 'absolute', inset: 0, display: 'flex',
                        alignItems: 'center', justifyContent: 'center',
                        flexDirection: 'column',
                      }}>
                        <span style={{
                          fontFamily: 'var(--font-mono)', fontSize: '1rem',
                          fontWeight: 700, color: 'var(--text-primary)',
                          lineHeight: 1,
                        }}>
                          {Math.round((activeStep / Math.max(1, STEPS.length - 1)) * 100)}
                        </span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.55rem', color: 'var(--text-muted)' }}>%</span>
                      </div>
                    </div>

                    {/* Active step headline */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{
                        fontSize: '0.7rem', color: 'rgba(56,189,248,0.5)',
                        fontFamily: 'var(--font-mono)', letterSpacing: '0.1em',
                        textTransform: 'uppercase', marginBottom: '4px',
                      }}>PROCESSING</p>
                      <p style={{
                        fontSize: '1rem', fontWeight: 800,
                        color: 'var(--text-primary)', lineHeight: 1.3,
                        animation: 'fadeIn 0.4s ease',
                      }}>
                        {STEPS[activeStep]?.label || 'جارٍ الإنهاء...'}
                      </p>
                      {/* Thin shimmer bar below headline */}
                      <div style={{
                        marginTop: '8px', height: '2px',
                        background: 'linear-gradient(90deg, transparent, var(--accent), var(--accent-2), transparent)',
                        backgroundSize: '200% 100%',
                        animation: 'shimmer 2s linear infinite',
                        borderRadius: '2px',
                        width: '70%',
                      }} />
                    </div>
                  </div>

                  {/* ── Steps grid — 2 columns */}
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: '8px',
                    direction: 'rtl',
                  }}>
                    {STEPS.map((step, i) => {
                      const done   = i < activeStep
                      const active = i === activeStep
                      return (
                        <div key={i} style={{
                          display: 'flex', alignItems: 'center', gap: '10px',
                          padding: '10px 12px',
                          borderRadius: '12px',
                          background: done
                            ? 'rgba(52,211,153,0.06)'
                            : active
                            ? 'rgba(56,189,248,0.08)'
                            : theme === 'dark' ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)',
                          border: `1px solid ${
                            done ? 'rgba(52,211,153,0.2)'
                            : active ? 'rgba(56,189,248,0.3)'
                            : theme === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.08)'
                          }`,
                          transition: 'all 0.4s ease',
                          position: 'relative',
                          overflow: 'hidden',
                          direction: 'rtl',
                        }}>
                          {/* Active shimmer sweep */}
                          {active && (
                            <div style={{
                              position: 'absolute', inset: 0,
                              background: 'linear-gradient(90deg, transparent 0%, rgba(56,189,248,0.06) 50%, transparent 100%)',
                              backgroundSize: '200% 100%',
                              animation: 'shimmer 1.8s linear infinite',
                            }} />
                          )}

                          {/* Status dot */}
                          <div style={{
                            width: '28px', height: '28px', borderRadius: '8px',
                            flexShrink: 0,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: done ? '0.8rem' : '0.9rem',
                            background: done
                              ? 'rgba(52,211,153,0.15)'
                              : active
                              ? 'rgba(56,189,248,0.15)'
                              : theme === 'dark' ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)',
                            border: `1px solid ${
                              done ? 'rgba(52,211,153,0.3)'
                              : active ? 'rgba(56,189,248,0.4)'
                              : theme === 'dark' ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.1)'
                            }`,
                            transition: 'all 0.4s',
                            position: 'relative',
                          }}>
                            {done ? (
                              <span style={{ color: '#34d399', fontWeight: 700, fontSize: '0.85rem' }}>✓</span>
                            ) : active ? (
                              <>
                                <span style={{ fontSize: '0.85rem' }}>{step.icon}</span>
                                <span style={{
                                  position: 'absolute', inset: '-3px', borderRadius: '10px',
                                  border: '1.5px solid rgba(56,189,248,0.5)',
                                  animation: 'ping 1.5s ease-in-out infinite',
                                }} />
                              </>
                            ) : (
                              <span style={{ fontSize: '0.85rem', opacity: 0.4 }}>{step.icon}</span>
                            )}
                          </div>

                          {/* Label */}
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <p style={{
                              fontSize: '0.78rem',
                              fontWeight: active ? 700 : done ? 600 : 500,
                              color: done ? 'var(--success)' : active ? 'var(--text-primary)' : 'var(--text-secondary)',
                              lineHeight: 1.3,
                              transition: 'color 0.4s',
                              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                            }}>
                              {step.label}
                            </p>
                            {done && (
                              <p style={{
                                fontSize: '0.62rem', color: 'var(--success)',
                                fontFamily: 'var(--font-mono)', marginTop: '2px',
                              }}>done</p>
                            )}
                            {active && (
                              <p style={{
                                fontSize: '0.62rem', color: 'var(--accent)',
                                fontFamily: 'var(--font-mono)', marginTop: '2px',
                                animation: 'pulse 1.5s ease-in-out infinite',
                              }}>running...</p>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  {/* ── Rotating tip — styled as terminal output */}
                  <div style={{
                    marginTop: '1.4rem',
                    padding: '12px 16px',
                    borderRadius: '10px',
                    background: theme === 'dark' ? 'rgba(0,0,0,0.3)' : 'rgba(0,0,0,0.04)',
                    border: '1px solid rgba(56,189,248,0.08)',
                    display: 'flex', gap: '10px', alignItems: 'flex-start', direction: 'rtl',
                  }}>
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
                      color: 'var(--success)', flexShrink: 0, marginTop: '1px',
                    }}>›</span>
                    <p key={tipIdx} style={{
                      fontSize: '0.76rem', color: 'var(--text-secondary)', lineHeight: 1.6,
                      animation: 'fadeIn 0.5s ease forwards',
                      fontFamily: 'var(--font-ar)',
                    }}>
                      {PROCESSING_TIPS[tipIdx]}
                    </p>
                  </div>

                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── Results screen ────────────────── */}
        {screen === 'results' && forecastData && (
          <div style={{ animation: 'fadeIn 0.4s ease forwards' }}>
            {/* Tab bar */}
            <div style={{
              display: 'flex', gap: '4px', padding: '5px',
              background: 'var(--bg-panel)', border: '1px solid var(--border)',
              borderRadius: 'var(--r-lg)', marginBottom: '2rem', overflowX: 'auto',
            }}>
              {[
                { id: 'business', label: '💼 Business Impact' },
                { id: 'forecast', label: '📊 التوصيات والتوقعات' },
                ...(forecastData?.timeseries?.length ? [{ id: 'timeline', label: '📈 السلسلة الزمنية' }] : []),
                {
                  id: 'report',
                  label: reportLoading ? '⏳ التقرير العربي...' : '📝 التقرير العربي',
                },
                { id: 'drift', label: '🔍 مراقبة البيانات' },
              ].map(({ id, label }) => (
                <button key={id} style={{
                  flex: 1, padding: '10px 18px', borderRadius: '10px',
                  fontSize: '0.88rem', fontWeight: 600, fontFamily: 'var(--font-ar)',
                  whiteSpace: 'nowrap',
                  background: activeTab === id
                    ? id === 'business'
                      ? 'linear-gradient(135deg, #7c3aed, #4f46e5)'
                      : 'linear-gradient(135deg, var(--accent), var(--accent-2))'
                    : 'transparent',
                  color: activeTab === id ? '#fff' : 'var(--text-secondary)',
                  boxShadow: activeTab === id ? '0 3px 12px var(--accent-glow)' : 'none',
                  transition: 'all 0.22s',
                }} onClick={() => setActiveTab(id)}>
                  {label}
                </button>
              ))}
            </div>

            {activeTab === 'business'  && <BusinessDashboard data={forecastData} />}
            {activeTab === 'forecast' && <ForecastDashboard data={forecastData} />}
            {activeTab === 'timeline'  && <ForecastTimeline timeseries={forecastData?.timeseries || []} />}
            {activeTab === 'report'   && (
              <InventoryReport
                report={report}
                loading={reportLoading}
                reportError={reportError}
              />
            )}
            {activeTab === 'drift'    && <DriftAlert drift={drift} />}
          </div>
        )}

        {/* ── Error screen ──────────────────── */}
        {screen === 'error' && error && (
          <div style={{ maxWidth: '660px', margin: '4rem auto' }}>
            <div style={{
              background: 'rgba(248,113,113,0.04)', border: '1px solid rgba(248,113,113,0.2)',
              borderRadius: 'var(--r-lg)', padding: '2.5rem', textAlign: 'center',
              animation: 'fadeUp 0.4s ease forwards',
            }}>
              <p style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>❌</p>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--danger)', marginBottom: '0.6rem' }}>
                تعذّرت معالجة الملف
              </h2>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
                {error.message}
              </p>
              {error.attempts?.length > 0 && (
                <div style={{
                  textAlign: 'right', direction: 'rtl', marginBottom: '1.5rem',
                  padding: '1rem', background: 'var(--bg-card)',
                  borderRadius: 'var(--r-sm)', fontSize: '0.82rem', color: 'var(--text-secondary)',
                }}>
                  <p style={{ marginBottom: '8px', fontWeight: 600, color: 'var(--text-primary)' }}>
                    محاولات الإصلاح:
                  </p>
                  {error.attempts.map((a, i) => (
                    <p key={i} style={{ marginBottom: '4px' }}>• {a}</p>
                  ))}
                </div>
              )}
              <button style={{
                padding: '10px 24px', borderRadius: 'var(--r-md)',
                background: 'var(--accent)', color: '#fff',
                fontFamily: 'var(--font-ar)', fontWeight: 600,
                fontSize: '0.9rem', boxShadow: '0 4px 16px var(--accent-glow)',
              }} onClick={reset}>
                ↩ حاول مجدداً
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer style={{
        textAlign: 'center', padding: '2rem',
        color: 'var(--text-muted)', fontSize: '0.75rem',
        borderTop: '1px solid var(--border)', marginTop: '4rem',
        position: 'relative', zIndex: 1,
      }}>
        مدير المخزون الذكي — مدعوم بـ Chronos T5 + LLM عربي · جميع البيانات تُحذف فور المعالجة
      </footer>
    </div>
  )
}