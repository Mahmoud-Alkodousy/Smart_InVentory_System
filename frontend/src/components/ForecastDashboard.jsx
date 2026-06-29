import React, { useMemo, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine, Area, AreaChart, Legend,
} from 'recharts'
import * as XLSX from 'xlsx'

/* ── Excel Export ────────────────────────────────────── */
function exportToExcel(recommendations) {
  const rows = recommendations.map(r => ({
    'الصنف':               r.item,
    'الفرع':               r.store,
    'التوقع 90 يوم':       r.forecast_90d,
    'حد أدنى التوقع':     r.forecast_90d_low ?? '',
    'حد أقصى التوقع':     r.forecast_90d_high ?? '',
    'الطلب اليومي':        r.avg_daily_demand,
    'المخزون الموصى به':   r.recommended_stock,
    'نقطة إعادة الطلب':   r.reorder_point,
    'المخزون الحالي':      r.current_stock ?? '',
    'وحدات زائدة':         r.excess_units ?? '',
    'سعر الوحدة':          r.unit_price ?? '',
    'رأس المال المربوط':   r.capital_tied_up ?? '',
    'وفر محتمل':           r.savings_value ?? '',
    'مستوى الخدمة %':      r.service_level_pct ?? '',
    'معامل التباين CV':    r.cv,
    'نسبة الهامش %':       (r.buffer_pct * 100) + '%',
    'تحذير موسمي':         r.seasonal_warning ? 'نعم' : 'لا',
    'ملاحظة':              r.warning_message ?? '',
    'المورد':              r.supplier ?? '',
    'مدة توريد المورد (يوم)': r.supplier_lead_time_days ?? '',
    'أحداث قادمة مؤثرة':   (r.event_tags && r.event_tags.length) ? r.event_tags.join('، ') : '',
    'هامش إضافي للأحداث':  r.event_buffer_units || '',
  }))
  const ws = XLSX.utils.json_to_sheet(rows)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'توصيات المخزون')
  ws['!cols'] = [
    {wch:10},{wch:8},{wch:14},{wch:14},{wch:14},{wch:12},{wch:16},{wch:16},
    {wch:14},{wch:12},{wch:12},{wch:16},{wch:12},{wch:14},{wch:14},{wch:14},{wch:12},{wch:30},
    {wch:18},{wch:16},{wch:20},{wch:16},
  ]
  XLSX.writeFile(wb, `inventory_${new Date().toISOString().slice(0,10)}.xlsx`)
}

/* ── Volatility map ─────────────────────────────────── */
const VOL = {
  0.10: { label: 'منخفض',  color: 'var(--success)', bg: 'rgba(52,211,153,0.12)',  border: 'rgba(52,211,153,0.3)'  },
  0.20: { label: 'متوسط',  color: 'var(--warning)', bg: 'rgba(251,191,36,0.12)',  border: 'rgba(251,191,36,0.3)'  },
  0.35: { label: 'مرتفع',  color: 'var(--danger)',  bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.3)' },
}

function getVol(bp) { return VOL[bp] || VOL[0.20] }

function fmt(n) {
  if (n == null || isNaN(n)) return '—'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K'
  return Math.round(n).toLocaleString('ar-EG')
}

const Tooltip_ = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--bg-panel)', border: '1px solid var(--border-bright)',
      borderRadius: 'var(--r-sm)', padding: '10px 14px',
      fontSize: '0.8rem', direction: 'rtl', minWidth: '140px',
      boxShadow: 'var(--shadow-md)',
    }}>
      <p style={{ color: 'var(--text-muted)', marginBottom: '6px', fontSize: '0.76rem' }}>{label}</p>
      {payload.map(p => (
        <p key={p.dataKey} style={{ color: p.color, marginBottom: '2px' }}>
          {p.name}: <strong style={{ fontFamily: 'var(--font-mono)' }}>{fmt(p.value)}</strong>
        </p>
      ))}
    </div>
  )
}

export default function ForecastDashboard({ data }) {
  const {
    recommendations = [], warnings = [],
    route, n_rows, n_stores, n_items, date_min, date_max,
  } = data

  const [storeFilter, setStoreFilter] = useState('all')
  const [sort, setSort]               = useState('stock_desc')
  const [showSeasonalOnly, setShowSeasonalOnly] = useState(false)

  /* ── Derived ──────────────────────────────────────── */
  const stores = useMemo(() =>
    ['all', ...new Set(recommendations.map(r => String(r.store)))],
    [recommendations]
  )

  const filtered = useMemo(() => {
    let list = storeFilter === 'all'
      ? recommendations
      : recommendations.filter(r => String(r.store) === storeFilter)
    if (showSeasonalOnly) list = list.filter(r => r.seasonal_warning)
    if (sort === 'stock_desc')  list = [...list].sort((a, b) => b.recommended_stock - a.recommended_stock)
    if (sort === 'cv_desc')     list = [...list].sort((a, b) => b.cv - a.cv)
    if (sort === 'reorder_asc') list = [...list].sort((a, b) => b.reorder_point - a.reorder_point)
    if (sort === 'demand_desc') list = [...list].sort((a, b) => b.avg_daily_demand - a.avg_daily_demand)
    return list
  }, [recommendations, storeFilter, sort, showSeasonalOnly])

  /* ── Chart data ──────────────────────────────────── */
  const topChart = useMemo(() =>
    [...recommendations]
      .sort((a, b) => b.recommended_stock - a.recommended_stock)
      .slice(0, 8)
      .map(r => ({
        name:        `${r.item}  |  فرع ${r.store}`,
        توقع:        Math.round(r.forecast_90d),
        'حد أدنى':   Math.round(r.forecast_90d_low  ?? r.forecast_90d),
        'حد أقصى':   Math.round(r.forecast_90d_high ?? r.forecast_90d),
        موصى_به:     Math.round(r.recommended_stock),
      })),
    [recommendations]
  )

  const bufferDist = useMemo(() => [
    { name: 'منخفض (CV < 0.2)',  value: recommendations.filter(r => r.buffer_pct === 0.10).length, color: 'var(--success)' },
    { name: 'متوسط (CV < 0.5)',  value: recommendations.filter(r => r.buffer_pct === 0.20).length, color: 'var(--warning)' },
    { name: 'مرتفع (CV ≥ 0.5)',  value: recommendations.filter(r => r.buffer_pct === 0.35).length, color: 'var(--danger)'  },
  ], [recommendations])

  const totalForecast  = recommendations.reduce((s, r) => s + r.forecast_90d, 0)
  const totalStock     = recommendations.reduce((s, r) => s + r.recommended_stock, 0)
  const seasonalCount  = recommendations.filter(r => r.seasonal_warning).length
  const highVolatile   = recommendations.filter(r => r.buffer_pct === 0.35).length

  // Financial KPIs — only shown when unit_price was supplied
  const hasFinancial     = recommendations.some(r => r.capital_tied_up != null)
  const totalCapital     = hasFinancial ? recommendations.reduce((s, r) => s + (r.capital_tied_up    ?? 0), 0) : null
  const totalSafetyValue = hasFinancial ? recommendations.reduce((s, r) => s + (r.safety_stock_value ?? 0), 0) : null

  /* ── Render ──────────────────────────────────────── */
  return (
    <div style={{ animation: 'fadeUp 0.4s ease forwards' }}>

      {/* ── Header ──────────────────────────────────── */}
      <div style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.4rem' }}>
          📊 نتائج التنبؤ والتوصيات
        </h2>
        <div style={{ display: 'flex', gap: '1.2rem', flexWrap: 'wrap', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
          <span>
            <span style={{ color: route === 'direct' ? 'var(--success)' : 'var(--accent)' }}>● </span>
            {route === 'direct' ? 'بيانات نظيفة — مسار مباشر' : 'تم إصلاح البيانات بالذكاء الاصطناعي'}
          </span>
          {date_min && <span>📅 {date_min} ← {date_max}</span>}
          {n_rows   && <span>📋 {n_rows.toLocaleString('ar-EG')} سجل</span>}
          {n_stores && <span>🏪 {n_stores} فرع · {n_items} صنف</span>}
        </div>
      </div>

      {/* ── KPI cards ───────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(165px, 1fr))', gap: '0.8rem', marginBottom: '1.5rem' }}>
        {[
          { icon: '🎯', label: 'إجمالي الأصناف',       val: recommendations.length, sub: `${n_stores} فرع × ${n_items} صنف`, color: 'var(--accent)' },
          { icon: '📈', label: 'المبيعات المتوقعة 90يوم', val: fmt(totalForecast),     sub: 'متوسط + احتمالية', color: 'var(--accent-2)' },
          { icon: '📦', label: 'المخزون الموصى به',      val: fmt(totalStock),        sub: 'مع الهامش الأمني', color: 'var(--success)' },
          { icon: '⚠️', label: 'تحذيرات موسمية',        val: seasonalCount,          sub: 'منتج يحتاج انتباهاً', color: seasonalCount > 0 ? 'var(--warning)' : 'var(--text-muted)' },
          { icon: '🔴', label: 'تذبذب مرتفع',           val: highVolatile,           sub: 'CV ≥ 0.5', color: highVolatile > 0 ? 'var(--danger)' : 'var(--text-muted)' },
        ].map(({ icon, label, val, sub, color }) => (
          <div key={label} style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 'var(--r-md)', padding: '1.1rem',
          }}>
            <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '5px' }}>
              {icon} {label}
            </p>
            <p style={{ fontSize: '1.6rem', fontWeight: 700, color, lineHeight: 1, fontFamily: 'var(--font-mono)', marginBottom: '3px' }}>{val}</p>
            <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{sub}</p>
          </div>
        ))}

        {/* Financial KPI cards — shown only when unit_price was supplied */}
        {hasFinancial && (
          <>
            <div style={{
              background: 'linear-gradient(135deg, rgba(2,128,144,0.12) 0%, rgba(26,94,76,0.08) 100%)',
              border: '1px solid rgba(2,128,144,0.35)',
              borderRadius: 'var(--r-md)', padding: '1.1rem',
            }}>
              <p style={{ fontSize: '0.72rem', color: 'var(--accent)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '5px' }}>
                💰 رأس المال المربوط
              </p>
              <p style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--accent)', lineHeight: 1, fontFamily: 'var(--font-mono)', marginBottom: '3px' }}>
                {fmt(totalCapital)}
              </p>
              <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>إجمالي قيمة المخزون الموصى به</p>
            </div>
            <div style={{
              background: 'linear-gradient(135deg, rgba(52,211,153,0.10) 0%, rgba(52,211,153,0.04) 100%)',
              border: '1px solid rgba(52,211,153,0.3)',
              borderRadius: 'var(--r-md)', padding: '1.1rem',
            }}>
              <p style={{ fontSize: '0.72rem', color: 'var(--success)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '5px' }}>
                🛡️ قيمة الهامش الأمني
              </p>
              <p style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--success)', lineHeight: 1, fontFamily: 'var(--font-mono)', marginBottom: '3px' }}>
                {fmt(totalSafetyValue)}
              </p>
              <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>تكلفة الحماية من نفاد المخزون</p>
            </div>
          </>
        )}
      </div>

      {/* ── Warnings ────────────────────────────────── */}
      {warnings.length > 0 && (
        <div style={{ marginBottom: '1.2rem' }}>
          {warnings.map((w, i) => (
            <div key={i} style={{
              display: 'flex', gap: '10px', alignItems: 'flex-start',
              padding: '10px 14px', marginBottom: '6px',
              background: 'rgba(251,191,36,0.05)', border: '1px solid rgba(251,191,36,0.18)',
              borderRadius: 'var(--r-sm)', fontSize: '0.85rem', color: 'var(--warning)',
            }}>
              <span>⚠️</span><span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Charts row ──────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '3fr 1fr', gap: '1rem', marginBottom: '1.2rem' }}>

        {/* Bar chart — top items — pure CSS (Recharts RTL broken) */}
        <div style={cardSt}>
          <p style={cardTitleSt}>أعلى 8 أصناف — التوقع مقابل المخزون الموصى به</p>

          {/* Legend */}
          <div style={{ display: 'flex', gap: '16px', marginBottom: '14px', fontSize: '0.78rem', color: 'var(--text-muted)', justifyContent: 'center' }}>
            {[
              { color: 'rgba(56,189,248,0.35)', label: 'حد أدنى' },
              { color: 'var(--accent)',          label: 'توقع' },
              { color: 'var(--success)',          label: 'الموصى به' },
            ].map(({ color, label }) => (
              <span key={label} style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                <span style={{ width: 12, height: 12, borderRadius: 2, background: color, display: 'inline-block' }} />
                {label}
              </span>
            ))}
          </div>

          {/* Bars */}
          {(() => {
            const maxVal = Math.max(...topChart.map(d => d['موصى_به']))
            return (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {topChart.map((d, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '10px', direction: 'rtl' }}>
                    {/* Label */}
                    <div style={{
                      width: '160px', flexShrink: 0,
                      fontSize: '11px', fontWeight: 600,
                      color: 'var(--text-primary)', textAlign: 'right',
                      lineHeight: 1.3,
                    }}>
                      {d.name}
                    </div>
                    {/* Bars track */}
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '3px' }}>
                      {[
                        { val: d['حد أدنى'], color: 'rgba(56,189,248,0.35)' },
                        { val: d['توقع'],    color: 'var(--accent)' },
                        { val: d['موصى_به'], color: 'var(--success)' },
                      ].map(({ val, color }) => (
                        <div key={color} style={{ height: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', overflow: 'hidden', direction: 'ltr' }}>
                          <div style={{
                            height: '100%',
                            width: `${(val / maxVal) * 100}%`,
                            background: color,
                            borderRadius: '4px',
                            transition: 'width 0.8s ease',
                          }} />
                        </div>
                      ))}
                    </div>
                    {/* Value */}
                    <div style={{ width: '44px', flexShrink: 0, fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', textAlign: 'left' }}>
                      {fmt(d['موصى_به'])}
                    </div>
                  </div>
                ))}
              </div>
            )
          })()}
        </div>

        {/* Volatility distribution */}
        <div style={cardSt}>
          <p style={cardTitleSt}>توزيع التذبذب</p>
          <div style={{ marginTop: '0.8rem', display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {bufferDist.map(({ name, value, color }) => {
              const pct = recommendations.length ? (value / recommendations.length) * 100 : 0
              return (
                <div key={name}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}>
                    <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{name}</span>
                    <span style={{ fontSize: '0.78rem', color, fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                      {value}
                    </span>
                  </div>
                  <div style={{ height: '5px', background: 'var(--bg-panel)', borderRadius: '3px', overflow: 'hidden' }}>
                    <div style={{
                      height: '100%', width: `${pct}%`, background: color,
                      borderRadius: '3px', transition: 'width 1s ease',
                    }} />
                  </div>
                </div>
              )
            })}
          </div>
          <div style={{
            marginTop: '1.2rem', padding: '10px', background: 'var(--bg-panel)',
            borderRadius: 'var(--r-sm)', fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.6,
          }}>
            الهامش الأمني مبني على معامل التباين (CV) — يعكس تذبذب الطلب الفعلي
          </div>
        </div>
      </div>

      {/* ── Table ───────────────────────────────────── */}
      <div style={{ ...cardSt, overflow: 'hidden', padding: 0 }}>
        {/* Table header / controls */}
        <div style={{
          padding: '1rem 1.2rem', borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexWrap: 'wrap', gap: '10px',
        }}>
          <p style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.95rem' }}>
            توصيات المخزون التفصيلية
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--text-muted)', marginRight: '8px' }}>
              ({filtered.length} صنف)
            </span>
          </p>
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
            <button
              onClick={() => exportToExcel(recommendations)}
              title="تحميل كـ Excel"
              style={{
                padding: '5px 13px', borderRadius: '100px', fontSize: '0.78rem', fontWeight: 700,
                border: '1px solid rgba(52,211,153,0.4)',
                background: 'rgba(52,211,153,0.1)', color: '#34d399', cursor: 'pointer',
                fontFamily: 'var(--font-ar)', display: 'flex', alignItems: 'center', gap: '5px',
                transition: 'all 0.18s',
              }}
            >📥 Excel</button>
            {[
              { val: 'stock_desc',  label: '📦 الأعلى مخزوناً' },
              { val: 'cv_desc',     label: '📊 الأكثر تذبذباً' },
              { val: 'reorder_asc', label: '🔄 نقطة الطلب' },
              { val: 'demand_desc', label: '📈 الطلب اليومي' },
            ].map(({ val, label }) => (
              <button key={val} style={pillBtnSt(sort === val)} onClick={() => setSort(val)}>{label}</button>
            ))}
          </div>
        </div>

        {/* Store filter */}
        {stores.length > 2 && (
          <div style={{
            padding: '0.6rem 1.2rem', borderBottom: '1px solid var(--border)',
            display: 'flex', gap: '6px', overflowX: 'auto',
          }}>
            {stores.map(st => (
              <button key={st} style={pillBtnSt(storeFilter === st)} onClick={() => setStoreFilter(st)}>
                {st === 'all' ? '🏪 جميع الفروع' : `فرع ${st}`}
              </button>
            ))}
            {seasonalCount > 0 && (
              <button style={pillBtnSt(showSeasonalOnly)} onClick={() => setShowSeasonalOnly(p => !p)}>
                ⚠️ الموسمية فقط ({seasonalCount})
              </button>
            )}
          </div>
        )}

        {/* Table */}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {[
                  'الصنف', 'الفرع',
                  'التوقع (90 يوم)', 'نطاق التوقع ↓ / ↑',
                  'الطلب اليومي', 'الموصى به', 'نقطة الطلب',
                  ...(hasFinancial ? ['رأس المال المربوط'] : []),
                  'CV', 'التذبذب', 'تنبيه',
                ].map(h => (
                  <th key={h} style={thSt}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => {
                const vol = getVol(r.buffer_pct)
                const hasLowHigh = r.forecast_90d_low != null && r.forecast_90d_high != null
                return (
                  <tr key={i} style={{
                    background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)',
                    transition: 'background 0.15s',
                  }}
                    onMouseEnter={e => e.currentTarget.style.background = 'rgba(56,189,248,0.04)'}
                    onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)'}
                  >
                    <td style={{ ...tdSt, color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                      {r.item}
                    </td>
                    <td style={tdSt}>{r.store}</td>
                    <td style={{ ...tdSt, fontFamily: 'var(--font-mono)' }}>{fmt(r.forecast_90d)}</td>
                    <td style={{ ...tdSt, fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                      {hasLowHigh ? (
                        <>
                          <span style={{ color: 'var(--success)' }}>{fmt(r.forecast_90d_low)}</span>
                          <span style={{ color: 'var(--text-muted)', margin: '0 4px' }}>/</span>
                          <span style={{ color: 'var(--danger)' }}>{fmt(r.forecast_90d_high)}</span>
                        </>
                      ) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                    </td>
                    <td style={{ ...tdSt, fontFamily: 'var(--font-mono)' }}>{r.avg_daily_demand?.toFixed(1)}</td>
                    <td style={{ ...tdSt, fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--success)' }}>
                      {fmt(r.recommended_stock)}
                    </td>
                    <td style={{ ...tdSt, fontFamily: 'var(--font-mono)' }}>{fmt(r.reorder_point)}</td>
                    {hasFinancial && (
                      <td style={{ ...tdSt, fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontWeight: 600 }}>
                        {r.capital_tied_up != null ? fmt(r.capital_tied_up) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                      </td>
                    )}
                    <td style={{ ...tdSt, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                      {r.cv?.toFixed(3)}
                    </td>
                    <td style={tdSt}>
                      <span style={{
                        display: 'inline-block', padding: '2px 10px',
                        borderRadius: '100px', fontSize: '0.73rem', fontWeight: 700,
                        background: vol.bg, color: vol.color, border: `1px solid ${vol.border}`,
                      }}>
                        {vol.label}
                      </span>
                    </td>
                    <td style={tdSt}>
                      {r.seasonal_warning ? (
                        <span title={r.warning_message}
                          style={{ cursor: 'help', color: 'var(--warning)', fontSize: '0.82rem', fontWeight: 600 }}>
                          ⚠️ موسمي
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>—</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {filtered.length === 0 && (
            <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
              لا توجد نتائج مطابقة للفلتر المحدد
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── Shared styles ──────────────────────────────────── */
const cardSt = {
  background: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 'var(--r-lg)', padding: '1.2rem',
}
const cardTitleSt = {
  fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.8rem',
}
const thSt = {
  padding: '9px 12px', fontSize: '0.72rem', fontWeight: 600,
  color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em',
  borderBottom: '1px solid var(--border)', background: 'var(--bg-panel)',
  textAlign: 'right', whiteSpace: 'nowrap',
}
const tdSt = {
  padding: '10px 12px', fontSize: '0.85rem', color: 'var(--text-primary)',
  borderBottom: '1px solid rgba(56,189,248,0.05)', whiteSpace: 'nowrap',
}
const pillBtnSt = active => ({
  padding: '4px 11px', borderRadius: '100px', fontSize: '0.78rem', fontWeight: 600,
  border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
  background: active ? 'rgba(56,189,248,0.12)' : 'transparent',
  color: active ? 'var(--accent)' : 'var(--text-secondary)',
  cursor: 'pointer', whiteSpace: 'nowrap', fontFamily: 'var(--font-ar)',
  transition: 'all 0.18s',
})
