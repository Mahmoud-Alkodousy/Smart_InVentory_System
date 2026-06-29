/**
 * BusinessDashboard.jsx
 * ─────────────────────
 * Business Impact Layer for Smart Inventory Manager.
 *
 * Sections:
 *   1. Executive Summary       — لغة المدير, لا أرقام تقنية
 *   2. External Events Impact  — رمضان/الأعياد/Black Friday/بداية الدراسة
 *   3. Service Level KPI       — estimated SL%, Fill Rate, Stockout Risk
 *   4. Cost Saving Calculator  — Current vs Recommended inventory value
 *   5. ABC Analysis (Pareto)   — A=top 80% value, B=next 15%, C=bottom 5%
 *   6. Supplier Risk Analysis  — lead-time risk per supplier
 *   7. Multi-Branch Optimization — transfer suggestions between stores
 *   8. What-If Simulation      — demand shock slider, re-computes on the fly
 *   9. Auto Purchase Order Generator — one-click PDF for the supplier
 */

import React, { useMemo, useState } from 'react'
import EventsImpactPanel  from './business/EventsImpactPanel'
import SupplierRiskPanel  from './business/SupplierRiskPanel'
import MultiBranchPanel   from './business/MultiBranchPanel'
import PurchaseOrderPanel from './business/PurchaseOrderPanel'

/* ── Helpers ──────────────────────────────────────────────────────────────── */

function fmt(n, currency = false) {
  if (n == null || isNaN(n)) return '—'
  const prefix = currency ? 'EGP ' : ''
  if (n >= 1_000_000) return prefix + (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000)     return prefix + (n / 1_000).toFixed(1) + 'K'
  return prefix + Math.round(n).toLocaleString('ar-EG')
}

function pct(n) {
  if (n == null || isNaN(n)) return '—'
  return n.toFixed(1) + '%'
}

/* ABC: sort by annual value desc, cumulative until 80% = A, next 15% = B, rest = C */
function classifyABC(recs) {
  const withValue = recs.map(r => ({
    ...r,
    annualValue: r.forecast_90d * (365 / 90) * (r.unit_price ?? 1),
  })).sort((a, b) => b.annualValue - a.annualValue)

  const total = withValue.reduce((s, r) => s + r.annualValue, 0)
  let cumulative = 0
  return withValue.map(r => {
    cumulative += r.annualValue
    const cumPct = total > 0 ? (cumulative / total) * 100 : 0
    const cls = cumPct <= 80 ? 'A' : cumPct <= 95 ? 'B' : 'C'
    return { ...r, abc: cls, cumPct, annualValue: r.annualValue }
  })
}

/* ── Card styles ──────────────────────────────────────────────────────────── */
const card = {
  background: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 'var(--r-lg)', padding: '1.2rem',
}
const cardTitle = {
  fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-primary)',
  marginBottom: '1rem', letterSpacing: '0.02em',
}

const kpiCard = (accent = 'var(--accent)', glow = 'rgba(56,189,248,0.08)') => ({
  background: glow, border: `1px solid ${accent}30`,
  borderRadius: 'var(--r-md)', padding: '1rem 1.1rem',
  display: 'flex', flexDirection: 'column', gap: '4px',
})

/* ── Gauge component ──────────────────────────────────────────────────────── */
function Gauge({ value, max = 100, color = 'var(--accent)', label }) {
  const pctVal = Math.min(100, Math.max(0, (value / max) * 100))
  const angle  = (pctVal / 100) * 180
  const r = 52, cx = 60, cy = 60
  const toXY = (deg) => {
    const rad = ((deg - 90) * Math.PI) / 180
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
  }
  const start = toXY(-90)
  const end   = toXY(-90 + angle)
  const large = angle > 180 ? 1 : 0

  return (
    <div style={{ textAlign: 'center' }}>
      <svg viewBox="0 0 120 70" width="130" height="75">
        {/* Track */}
        <path
          d={`M ${toXY(-90).x} ${toXY(-90).y} A ${r} ${r} 0 1 1 ${toXY(90).x} ${toXY(90).y}`}
          fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="10" strokeLinecap="round"
        />
        {/* Value arc */}
        {pctVal > 0 && (
          <path
            d={`M ${start.x} ${start.y} A ${r} ${r} 0 ${large} 1 ${end.x} ${end.y}`}
            fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
          />
        )}
        <text x={cx} y={cy + 8} textAnchor="middle" fill="var(--text-primary)"
          fontSize="16" fontWeight="700" fontFamily="monospace">
          {pctVal.toFixed(0)}%
        </text>
      </svg>
      {label && <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '-4px' }}>{label}</p>}
    </div>
  )
}

/* ── ABC Badge ────────────────────────────────────────────────────────────── */
const ABC_STYLE = {
  A: { color: '#34d399', bg: 'rgba(52,211,153,0.12)', border: 'rgba(52,211,153,0.3)' },
  B: { color: '#fbbf24', bg: 'rgba(251,191,36,0.12)', border: 'rgba(251,191,36,0.3)'  },
  C: { color: '#94a3b8', bg: 'rgba(148,163,184,0.10)', border: 'rgba(148,163,184,0.2)' },
}
function ABCBadge({ cls }) {
  const s = ABC_STYLE[cls] || ABC_STYLE.C
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: '100px',
      fontSize: '0.73rem', fontWeight: 800, fontFamily: 'monospace',
      background: s.bg, color: s.color, border: `1px solid ${s.border}`,
    }}>{cls}</span>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/*  MAIN COMPONENT                                                              */
/* ═══════════════════════════════════════════════════════════════════════════ */

export default function BusinessDashboard({ data }) {
  const {
    recommendations = [],
    suppliers = [],
    supplier_switches: supplierSwitches = [],
    transfers = [],
    events = [],
  } = data
  const [shock, setShock] = useState(0)        // What-If demand shock %
  const [abcPage, setAbcPage] = useState(0)    // ABC table pagination

  const abcRecs = useMemo(() => classifyABC(recommendations), [recommendations])

  /* ── Aggregate KPIs ─────────────────────────────────────────── */
  const kpis = useMemo(() => {
    const hasSavings  = abcRecs.some(r => r.savings_value != null)
    const hasCapital  = abcRecs.some(r => r.capital_tied_up != null)
    const hasStock    = abcRecs.some(r => r.current_stock != null)

    const totalSavings     = hasSavings ? abcRecs.reduce((s, r) => s + (r.savings_value ?? 0), 0) : null
    const totalExcessUnits = hasStock   ? abcRecs.reduce((s, r) => s + (r.excess_units  ?? 0), 0) : null
    const totalCapital     = hasCapital ? abcRecs.reduce((s, r) => s + (r.capital_tied_up ?? 0), 0) : null
    const totalCurrentVal  = hasStock   ? abcRecs.reduce((s, r) => s + ((r.current_stock ?? r.recommended_stock) * (r.unit_price ?? 0)), 0) : null

    const atRisk    = abcRecs.filter(r => r.seasonal_warning || r.buffer_pct === 0.35).length
    const critical  = abcRecs.filter(r => r.buffer_pct === 0.35 && r.cv > 0.7).length

    // Weighted average service level
    const totalDemand = abcRecs.reduce((s, r) => s + r.forecast_90d, 0)
    const weightedSL  = totalDemand > 0
      ? abcRecs.reduce((s, r) => s + (r.service_level_pct ?? 90) * r.forecast_90d, 0) / totalDemand
      : 90

    const aCount = abcRecs.filter(r => r.abc === 'A').length
    const bCount = abcRecs.filter(r => r.abc === 'B').length
    const cCount = abcRecs.filter(r => r.abc === 'C').length

    return {
      atRisk, critical, totalSavings, totalExcessUnits, totalCapital,
      totalCurrentVal, weightedSL, hasSavings, hasCapital, hasStock,
      aCount, bCount, cCount,
    }
  }, [abcRecs])

  /* ── What-If computation ─────────────────────────────────────── */
  const whatIf = useMemo(() => {
    const factor = 1 + shock / 100
    return abcRecs.map(r => {
      const newForecast = r.forecast_90d * factor
      const newRec      = r.forecast_90d_high * factor * (1 + r.buffer_pct)
      const additionalUnits = Math.max(0, newRec - r.recommended_stock)
      const additionalCost  = additionalUnits * (r.unit_price ?? 0)
      const newlyAtRisk     = additionalUnits > r.recommended_stock * 0.15
      return { ...r, newForecast, newRec, additionalUnits, additionalCost, newlyAtRisk }
    })
  }, [abcRecs, shock])

  const whatIfTotals = useMemo(() => ({
    additionalUnits: whatIf.reduce((s, r) => s + r.additionalUnits, 0),
    additionalCost:  whatIf.reduce((s, r) => s + r.additionalCost,  0),
    atRisk:          whatIf.filter(r => r.newlyAtRisk).length,
  }), [whatIf])

  const PAGE_SIZE = 10
  const abcSlice  = abcRecs.slice(abcPage * PAGE_SIZE, (abcPage + 1) * PAGE_SIZE)
  const totalPages = Math.ceil(abcRecs.length / PAGE_SIZE)

  /* ═══════════════════════════════════════════════════════════════ */
  return (
    <div style={{ animation: 'fadeUp 0.4s ease forwards', display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>

      {/* ── 1. EXECUTIVE SUMMARY ─────────────────────────────────── */}
      <div style={card}>
        <p style={cardTitle}>🏢 AI Executive Summary</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '0.8rem' }}>

          <div style={kpiCard('var(--danger)', 'rgba(248,113,113,0.07)')}>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              🚨 منتجات في خطر
            </span>
            <span style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--danger)', fontFamily: 'monospace', lineHeight: 1 }}>
              {kpis.atRisk}
            </span>
            <span style={{ fontSize: '0.73rem', color: 'var(--text-muted)' }}>
              {kpis.critical} منهم حرجة جداً (CV &gt; 0.7)
            </span>
          </div>

          <div style={kpiCard('var(--warning)', 'rgba(251,191,36,0.07)')}>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              📦 منتجات فئة A
            </span>
            <span style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--warning)', fontFamily: 'monospace', lineHeight: 1 }}>
              {kpis.aCount}
            </span>
            <span style={{ fontSize: '0.73rem', color: 'var(--text-muted)' }}>
              مسؤولة عن 80% من قيمة المخزون
            </span>
          </div>

          {kpis.totalCapital != null && (
            <div style={kpiCard('var(--accent)', 'rgba(56,189,248,0.07)')}>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                💰 رأس المال الموصى به
              </span>
              <span style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--accent)', fontFamily: 'monospace', lineHeight: 1 }}>
                {fmt(kpis.totalCapital)}
              </span>
              <span style={{ fontSize: '0.73rem', color: 'var(--text-muted)' }}>إجمالي قيمة المخزون المثالي</span>
            </div>
          )}

          {kpis.totalSavings != null && kpis.totalSavings > 0 && (
            <div style={kpiCard('#34d399', 'rgba(52,211,153,0.08)')}>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                💚 وفر محتمل
              </span>
              <span style={{ fontSize: '1.6rem', fontWeight: 800, color: '#34d399', fontFamily: 'monospace', lineHeight: 1 }}>
                {fmt(kpis.totalSavings)}
              </span>
              <span style={{ fontSize: '0.73rem', color: 'var(--text-muted)' }}>
                من تحرير {fmt(kpis.totalExcessUnits)} وحدة زائدة
              </span>
            </div>
          )}

          <div style={kpiCard('#a78bfa', 'rgba(167,139,250,0.07)')}>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              🎯 مستوى الخدمة المتوقع
            </span>
            <span style={{ fontSize: '2.2rem', fontWeight: 800, color: '#a78bfa', fontFamily: 'monospace', lineHeight: 1 }}>
              {kpis.weightedSL.toFixed(0)}%
            </span>
            <span style={{ fontSize: '0.73rem', color: 'var(--text-muted)' }}>
              بعد تطبيق التوصيات
            </span>
          </div>

        </div>
      </div>

      {/* ── 2. EXTERNAL EVENTS IMPACT ────────────────────────────── */}
      <EventsImpactPanel events={events} recommendations={recommendations} />

      {/* ── 3. SERVICE LEVEL KPIs ────────────────────────────────── */}
      <div style={card}>
        <p style={cardTitle}>📊 Service Level KPIs</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem', alignItems: 'center' }}>

          <div style={{ textAlign: 'center' }}>
            <Gauge value={kpis.weightedSL} color="#a78bfa" label="Service Level %" />
            <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
              احتمال تلبية الطلب بالكامل
            </p>
          </div>

          <div style={{ textAlign: 'center' }}>
            <Gauge value={kpis.weightedSL - 2} color="#34d399" label="Fill Rate %" />
            <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
              % الطلبات المكتملة فوراً
            </p>
          </div>

          <div style={{ textAlign: 'center' }}>
            <Gauge value={100 - kpis.weightedSL} max={30} color="#f87171" label="Stockout Risk %" />
            <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
              خطر نفاد المخزون
            </p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {[
              { label: 'منتجات تذبذب منخفض (CV < 0.2)', sl: 87, count: abcRecs.filter(r => r.buffer_pct === 0.10).length, color: '#34d399' },
              { label: 'منتجات تذبذب متوسط (CV < 0.5)', sl: 93, count: abcRecs.filter(r => r.buffer_pct === 0.20).length, color: '#fbbf24' },
              { label: 'منتجات تذبذب مرتفع (CV ≥ 0.5)', sl: 97, count: abcRecs.filter(r => r.buffer_pct === 0.35).length, color: '#f87171' },
            ].map(({ label, sl, count, color }) => count > 0 && (
              <div key={label}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)' }}>{label}</span>
                  <span style={{ fontSize: '0.73rem', color, fontFamily: 'monospace', fontWeight: 700 }}>SL {sl}%</span>
                </div>
                <div style={{ height: '4px', background: 'var(--bg-panel)', borderRadius: '2px' }}>
                  <div style={{ height: '100%', width: `${sl}%`, background: color, borderRadius: '2px', transition: 'width 1s ease' }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── 4. COST SAVING CALCULATOR ────────────────────────────── */}
      {kpis.hasSavings && kpis.totalSavings > 0 && (
        <div style={card}>
          <p style={cardTitle}>💰 Cost Saving Calculator</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.2rem' }}>

            <div style={{ background: 'rgba(248,113,113,0.07)', border: '1px solid rgba(248,113,113,0.2)', borderRadius: 'var(--r-md)', padding: '1rem' }}>
              <p style={{ fontSize: '0.72rem', color: '#f87171', fontWeight: 600, marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                📦 المخزون الحالي (مقدّر)
              </p>
              <p style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f87171', fontFamily: 'monospace', marginBottom: '4px' }}>
                {fmt(kpis.totalCurrentVal ?? 0, true)}
              </p>
              <p style={{ fontSize: '0.73rem', color: 'var(--text-muted)' }}>رأس مال مُجمَّد حالياً</p>
            </div>

            <div style={{ background: 'rgba(52,211,153,0.07)', border: '1px solid rgba(52,211,153,0.2)', borderRadius: 'var(--r-md)', padding: '1rem' }}>
              <p style={{ fontSize: '0.72rem', color: '#34d399', fontWeight: 600, marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                ✅ المخزون الموصى به
              </p>
              <p style={{ fontSize: '1.5rem', fontWeight: 800, color: '#34d399', fontFamily: 'monospace', marginBottom: '4px' }}>
                {fmt(kpis.totalCapital ?? 0, true)}
              </p>
              <p style={{ fontSize: '0.73rem', color: 'var(--text-muted)' }}>المخزون المثالي بالذكاء الاصطناعي</p>
            </div>
          </div>

          {/* Savings breakdown bars */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', fontWeight: 600 }}>أعلى 8 منتجات بوفر محتمل:</p>
            {abcRecs
              .filter(r => (r.savings_value ?? 0) > 0)
              .sort((a, b) => (b.savings_value ?? 0) - (a.savings_value ?? 0))
              .slice(0, 8)
              .map((r, i) => {
                const maxSaving = abcRecs.reduce((m, x) => Math.max(m, x.savings_value ?? 0), 0)
                const pctBar = maxSaving > 0 ? (r.savings_value / maxSaving) * 100 : 0
                return (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '10px', direction: 'rtl' }}>
                    <ABCBadge cls={r.abc} />
                    <span style={{ width: '90px', flexShrink: 0, fontSize: '0.78rem', color: 'var(--text-primary)', textAlign: 'right', fontWeight: 600 }}>
                      صنف {r.item}
                    </span>
                    <div style={{ flex: 1, height: '12px', background: 'rgba(255,255,255,0.04)', borderRadius: '6px', overflow: 'hidden', direction: 'ltr' }}>
                      <div style={{ height: '100%', width: `${pctBar}%`, background: 'linear-gradient(90deg, #34d399, #22c55e)', borderRadius: '6px', transition: 'width 0.8s ease' }} />
                    </div>
                    <span style={{ width: '90px', flexShrink: 0, fontSize: '0.78rem', fontFamily: 'monospace', color: '#34d399', fontWeight: 700, textAlign: 'left' }}>
                      {fmt(r.savings_value)} وفر
                    </span>
                    <span style={{ width: '80px', flexShrink: 0, fontSize: '0.72rem', color: 'var(--text-muted)', textAlign: 'left' }}>
                      {fmt(r.excess_units)} وحدة زائدة
                    </span>
                  </div>
                )
              })
            }
          </div>

          {/* Summary box */}
          <div style={{
            marginTop: '1.2rem', padding: '1rem', borderRadius: 'var(--r-md)',
            background: 'linear-gradient(135deg, rgba(52,211,153,0.1), rgba(56,189,248,0.06))',
            border: '1px solid rgba(52,211,153,0.25)', display: 'flex', gap: '2rem', flexWrap: 'wrap', alignItems: 'center',
          }}>
            <div>
              <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '2px' }}>🔓 رأس مال يمكن تحريره</p>
              <p style={{ fontSize: '1.4rem', fontWeight: 800, color: '#34d399', fontFamily: 'monospace' }}>{fmt(kpis.totalSavings, true)}</p>
            </div>
            <div>
              <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '2px' }}>📦 وحدات زائدة</p>
              <p style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--accent)', fontFamily: 'monospace' }}>{fmt(kpis.totalExcessUnits)}</p>
            </div>
            <div style={{ flex: 1, fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
              بتطبيق توصيات الذكاء الاصطناعي، يمكن تحرير رأس المال المُجمَّد في المخزون الزائد، مما يُحسّن 
              التدفق النقدي ويُقلل تكلفة التخزين بشكل مباشر.
            </div>
          </div>
        </div>
      )}

      {/* ── 5. ABC ANALYSIS ──────────────────────────────────────── */}
      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <p style={cardTitle}>🏅 ABC Analysis (Pareto)</p>
          <div style={{ display: 'flex', gap: '8px' }}>
            {['A', 'B', 'C'].map(cls => {
              const count = abcRecs.filter(r => r.abc === cls).length
              const s     = ABC_STYLE[cls]
              return (
                <span key={cls} style={{
                  padding: '3px 12px', borderRadius: '100px', fontSize: '0.78rem',
                  fontWeight: 700, background: s.bg, color: s.color, border: `1px solid ${s.border}`,
                }}>
                  {cls}: {count} صنف
                </span>
              )
            })}
          </div>
        </div>

        {/* ABC description */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.8rem', marginBottom: '1.2rem' }}>
          {[
            { cls: 'A', title: 'فئة A — الأولوية القصوى', desc: 'الـ 20% من المنتجات المسؤولة عن 80% من القيمة. تحتاج متابعة يومية.', pct: '80%', color: '#34d399' },
            { cls: 'B', title: 'فئة B — الأولوية المتوسطة', desc: 'الـ 30% التالية من المنتجات. مراجعة أسبوعية كافية.', pct: '15%', color: '#fbbf24' },
            { cls: 'C', title: 'فئة C — الأولوية المنخفضة', desc: 'باقي المنتجات. تُشكّل 5% فقط من القيمة الإجمالية.', pct: '5%', color: '#94a3b8' },
          ].map(({ cls, title, desc, pct: p, color }) => (
            <div key={cls} style={{ background: 'var(--bg-panel)', borderRadius: 'var(--r-sm)', padding: '0.8rem', border: `1px solid ${ABC_STYLE[cls].border}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <span style={{ fontSize: '0.78rem', fontWeight: 700, color }}>{title}</span>
                <span style={{ fontSize: '0.72rem', fontFamily: 'monospace', color, fontWeight: 800 }}>{p}</span>
              </div>
              <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>{desc}</p>
            </div>
          ))}
        </div>

        {/* ABC Table */}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['الرتبة', 'الصنف', 'الفرع', 'ABC', 'القيمة السنوية (متوقعة)', 'التوقع 90 يوم', 'الموصى به', 'سعر الوحدة', '% تراكمي'].map(h => (
                  <th key={h} style={{ padding: '8px 10px', fontSize: '0.68rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid var(--border)', background: 'var(--bg-panel)', textAlign: 'right', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {abcSlice.map((r, i) => (
                <tr key={i}
                  style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(56,189,248,0.04)'}
                  onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)'}
                >
                  <td style={{ padding: '9px 10px', fontSize: '0.8rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>{abcPage * PAGE_SIZE + i + 1}</td>
                  <td style={{ padding: '9px 10px', fontSize: '0.85rem', color: 'var(--accent)', fontFamily: 'monospace', fontWeight: 700 }}>{r.item}</td>
                  <td style={{ padding: '9px 10px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{r.store}</td>
                  <td style={{ padding: '9px 10px' }}><ABCBadge cls={r.abc} /></td>
                  <td style={{ padding: '9px 10px', fontSize: '0.85rem', fontFamily: 'monospace', fontWeight: 700, color: ABC_STYLE[r.abc]?.color }}>
                    {r.unit_price ? fmt(r.annualValue) : fmt(r.annualValue) + ' *'}
                  </td>
                  <td style={{ padding: '9px 10px', fontSize: '0.85rem', fontFamily: 'monospace' }}>{fmt(r.forecast_90d)}</td>
                  <td style={{ padding: '9px 10px', fontSize: '0.85rem', fontFamily: 'monospace', color: '#34d399', fontWeight: 700 }}>{fmt(r.recommended_stock)}</td>
                  <td style={{ padding: '9px 10px', fontSize: '0.85rem', fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                    {r.unit_price != null ? fmt(r.unit_price) : <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>—</span>}
                  </td>
                  <td style={{ padding: '9px 10px', fontSize: '0.8rem', fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                    {r.cumPct?.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: '6px', marginTop: '0.8rem' }}>
            <button
              style={{ padding: '4px 12px', borderRadius: 'var(--r-sm)', border: '1px solid var(--border)', background: 'var(--bg-panel)', color: 'var(--text-muted)', cursor: abcPage > 0 ? 'pointer' : 'not-allowed', fontSize: '0.78rem' }}
              onClick={() => setAbcPage(p => Math.max(0, p - 1))} disabled={abcPage === 0}
            >← السابق</button>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', padding: '4px 8px' }}>{abcPage + 1} / {totalPages}</span>
            <button
              style={{ padding: '4px 12px', borderRadius: 'var(--r-sm)', border: '1px solid var(--border)', background: 'var(--bg-panel)', color: 'var(--text-muted)', cursor: abcPage < totalPages - 1 ? 'pointer' : 'not-allowed', fontSize: '0.78rem' }}
              onClick={() => setAbcPage(p => Math.min(totalPages - 1, p + 1))} disabled={abcPage === totalPages - 1}
            >التالي →</button>
          </div>
        )}
        {!abcRecs.some(r => r.unit_price) && (
          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '8px' }}>
            * القيمة محسوبة بالطلب فقط. أضف عمود <code>unit_price</code> أو <code>price</code> في بياناتك للحصول على القيمة المالية الدقيقة.
          </p>
        )}
      </div>

      {/* ── 6. SUPPLIER RISK ANALYSIS ────────────────────────────── */}
      <SupplierRiskPanel suppliers={suppliers} supplierSwitches={supplierSwitches} />

      {/* ── 7. MULTI-BRANCH OPTIMIZATION ─────────────────────────── */}
      <MultiBranchPanel transfers={transfers} />

      {/* ── 8. WHAT-IF SIMULATION ─────────────────────────────────── */}
      <div style={card}>
        <p style={cardTitle}>🔮 What-If Simulation — ماذا يحدث لو تغيّر الطلب؟</p>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1.2rem', marginBottom: '1.2rem', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: '200px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', fontWeight: 600 }}>
                تغيير الطلب: <span style={{ color: shock >= 0 ? 'var(--danger)' : '#34d399', fontFamily: 'monospace', fontWeight: 800 }}>
                  {shock >= 0 ? '+' : ''}{shock}%
                </span>
              </span>
              <button
                onClick={() => setShock(0)}
                style={{ fontSize: '0.72rem', color: 'var(--text-muted)', background: 'transparent', border: '1px solid var(--border)', borderRadius: 'var(--r-sm)', padding: '2px 8px', cursor: 'pointer' }}
              >Reset</button>
            </div>
            <input
              type="range" min="-50" max="100" value={shock}
              onChange={e => setShock(Number(e.target.value))}
              style={{ width: '100%', accentColor: shock >= 0 ? 'var(--danger)' : '#34d399' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--text-muted)' }}>
              <span>-50% (انخفاض حاد)</span>
              <span>0</span>
              <span>+100% (ضغف الطلب)</span>
            </div>
          </div>

          {/* Quick scenarios */}
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            {[
              { label: 'رمضان +40%', val: 40 },
              { label: 'أعياد +30%', val: 30 },
              { label: 'Black Friday +60%', val: 60 },
              { label: 'كساد -20%', val: -20 },
            ].map(({ label, val }) => (
              <button key={label} onClick={() => setShock(val)} style={{
                padding: '5px 10px', borderRadius: 'var(--r-sm)', fontSize: '0.75rem', fontWeight: 600,
                border: `1px solid ${shock === val ? 'var(--accent)' : 'var(--border)'}`,
                background: shock === val ? 'rgba(56,189,248,0.12)' : 'var(--bg-panel)',
                color: shock === val ? 'var(--accent)' : 'var(--text-secondary)', cursor: 'pointer',
              }}>{label}</button>
            ))}
          </div>
        </div>

        {/* What-If Results */}
        {shock !== 0 && (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.8rem', marginBottom: '1rem' }}>
              <div style={kpiCard(shock > 0 ? 'var(--danger)' : '#34d399', shock > 0 ? 'rgba(248,113,113,0.07)' : 'rgba(52,211,153,0.07)')}>
                <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  {shock > 0 ? '📦 وحدات إضافية مطلوبة' : '📉 وحدات يمكن تخفيضها'}
                </span>
                <span style={{ fontSize: '1.8rem', fontWeight: 800, color: shock > 0 ? 'var(--danger)' : '#34d399', fontFamily: 'monospace', lineHeight: 1 }}>
                  {fmt(Math.abs(whatIfTotals.additionalUnits))}
                </span>
              </div>
              {whatIfTotals.additionalCost > 0 && (
                <div style={kpiCard('var(--warning)', 'rgba(251,191,36,0.07)')}>
                  <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    💸 تكلفة إضافية
                  </span>
                  <span style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--warning)', fontFamily: 'monospace', lineHeight: 1 }}>
                    {fmt(whatIfTotals.additionalCost)}
                  </span>
                </div>
              )}
              <div style={kpiCard('var(--danger)', 'rgba(248,113,113,0.07)')}>
                <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  🚨 منتجات ستنفد
                </span>
                <span style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--danger)', fontFamily: 'monospace', lineHeight: 1 }}>
                  {whatIfTotals.atRisk}
                </span>
              </div>
            </div>

            {/* At-risk items */}
            {whatIfTotals.atRisk > 0 && (
              <div style={{ background: 'rgba(248,113,113,0.04)', border: '1px solid rgba(248,113,113,0.2)', borderRadius: 'var(--r-md)', padding: '0.8rem' }}>
                <p style={{ fontSize: '0.78rem', color: '#f87171', fontWeight: 600, marginBottom: '8px' }}>
                  ⚠️ المنتجات المعرضة لنفاد المخزون في هذا السيناريو:
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {whatIf.filter(r => r.newlyAtRisk).slice(0, 15).map((r, i) => (
                    <span key={i} style={{
                      padding: '3px 10px', borderRadius: '100px', fontSize: '0.75rem',
                      background: 'rgba(248,113,113,0.1)', color: '#f87171', border: '1px solid rgba(248,113,113,0.25)',
                      fontFamily: 'monospace', fontWeight: 600,
                    }}>صنف {r.item} — فرع {r.store}</span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {shock === 0 && (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            اضغط على أحد السيناريوهات أو حرّك الـ Slider لمحاكاة تأثير تغيير الطلب على مخزونك
          </div>
        )}
      </div>

      {/* ── 9. AUTO PURCHASE ORDER GENERATOR ─────────────────────── */}
      <PurchaseOrderPanel recommendations={recommendations} />

    </div>
  )
}
