import React, { useMemo, useState } from 'react'

/* ─────────────────────────────────────────────────────
   ForecastTimeline
   Interactive day-by-day chart: actual history → forecast
   median with a shaded low/high confidence band.

   Built as plain SVG (not Recharts) — Recharts' axis/tooltip
   layout breaks under RTL page direction in this app, same
   reason the bar chart in ForecastDashboard was hand-rolled.
───────────────────────────────────────────────────── */

const W = 880
const H = 320
const PAD = { top: 18, right: 18, bottom: 34, left: 50 }

function fmt(n) {
  if (n == null || isNaN(n)) return '—'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K'
  return Math.round(n).toLocaleString('ar-EG')
}

export default function ForecastTimeline({ timeseries = [] }) {
  const [selected, setSelected] = useState(0)
  const [hoverIdx, setHoverIdx] = useState(null)

  const series = timeseries[selected]

  /* ── Build a single chronological array: history then forecast ── */
  const points = useMemo(() => {
    if (!series) return []
    const hist = series.history.map(p => ({
      date: p.date, actual: p.sales, low: null, median: null, high: null,
    }))
    const fc = series.forecast.map(p => ({
      date: p.date, actual: null, low: p.low, median: p.median, high: p.high,
    }))
    return [...hist, ...fc]
  }, [series])

  const boundaryIdx = series ? series.history.length : 0

  const { xScale, yScale, maxY } = useMemo(() => {
    const n = points.length || 1
    const allVals = points.flatMap(p => [p.actual, p.high, p.median, p.low]).filter(v => v != null)
    const maxY = Math.max(1, ...allVals) * 1.12
    const innerW = W - PAD.left - PAD.right
    const innerH = H - PAD.top - PAD.bottom
    const xScale = i => PAD.left + (innerW * i) / Math.max(1, n - 1)
    const yScale = v => PAD.top + innerH - (innerH * v) / maxY
    return { xScale, yScale, maxY }
  }, [points])

  if (!timeseries.length) return null

  const bandPath = points.length
    ? [
        ...points.map((p, i) => p.high != null ? `${xScale(i)},${yScale(p.high)}` : null).filter(Boolean),
        ...points.map((p, i) => p.low != null ? `${xScale(i)},${yScale(p.low)}` : null).filter(Boolean).reverse(),
      ].join(' L ')
    : ''

  const actualLine = points
    .map((p, i) => (p.actual != null ? `${xScale(i)},${yScale(p.actual)}` : null))
    .filter(Boolean)
    .join(' L ')

  const medianLine = points
    .map((p, i) => (p.median != null ? `${xScale(i)},${yScale(p.median)}` : null))
    .filter(Boolean)
    .join(' L ')

  // Connect the last actual point to the first forecast point so the lines look continuous
  const bridgeLine = boundaryIdx > 0 && points[boundaryIdx]
    ? `${xScale(boundaryIdx - 1)},${yScale(points[boundaryIdx - 1].actual)} L ${xScale(boundaryIdx)},${yScale(points[boundaryIdx].median)}`
    : ''

  const yTicks = 4
  const tickVals = Array.from({ length: yTicks + 1 }, (_, i) => Math.round((maxY / yTicks) * i))

  // A handful of x-axis date labels
  const xTickCount = 6
  const xTickIdxs = Array.from({ length: xTickCount }, (_, i) =>
    Math.round((points.length - 1) * (i / (xTickCount - 1)))
  )

  const hovered = hoverIdx != null ? points[hoverIdx] : null

  return (
    <div style={cardSt}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px', marginBottom: '0.9rem' }}>
        <p style={cardTitleSt}>📈 السلسلة الزمنية — تاريخ المبيعات والتنبؤ (أعلى الأصناف)</p>
        <div style={{ display: 'flex', gap: '14px', fontSize: '0.76rem', color: 'var(--text-muted)' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ width: 14, height: 3, background: 'var(--accent-2)', display: 'inline-block', borderRadius: 2 }} />
            مبيعات فعلية
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ width: 14, height: 3, background: 'var(--accent)', display: 'inline-block', borderRadius: 2, opacity: 0.9 }} />
            التنبؤ (وسيط)
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ width: 14, height: 8, background: 'rgba(56,189,248,0.18)', display: 'inline-block', borderRadius: 2 }} />
            نطاق الثقة 10–90%
          </span>
        </div>
      </div>

      {/* Item selector pills */}
      <div style={{ display: 'flex', gap: '6px', overflowX: 'auto', marginBottom: '1rem', paddingBottom: '4px' }}>
        {timeseries.map((s, i) => (
          <button
            key={`${s.store}-${s.item}-${i}`}
            onClick={() => { setSelected(i); setHoverIdx(null) }}
            style={pillBtnSt(i === selected)}
          >
            {s.item} <span style={{ opacity: 0.6 }}>· فرع {s.store}</span>
          </button>
        ))}
      </div>

      {/* Chart */}
      <div style={{ position: 'relative' }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          style={{ width: '100%', height: 'auto', direction: 'ltr' }}
          onMouseLeave={() => setHoverIdx(null)}
        >
          {/* Y gridlines + labels */}
          {tickVals.map((v, i) => (
            <g key={i}>
              <line x1={PAD.left} x2={W - PAD.right} y1={yScale(v)} y2={yScale(v)}
                stroke="var(--border)" strokeWidth="1" />
              <text x={PAD.left - 8} y={yScale(v) + 4} textAnchor="end"
                fontSize="10" fill="var(--text-muted)" fontFamily="var(--font-mono)">
                {fmt(v)}
              </text>
            </g>
          ))}

          {/* X labels */}
          {xTickIdxs.map((idx, i) => points[idx] && (
            <text key={i} x={xScale(idx)} y={H - 10} textAnchor="middle"
              fontSize="10" fill="var(--text-muted)" fontFamily="var(--font-mono)">
              {points[idx].date.slice(5)}
            </text>
          ))}

          {/* Boundary line: history → forecast */}
          {boundaryIdx > 0 && boundaryIdx < points.length && (
            <line
              x1={xScale(boundaryIdx)} x2={xScale(boundaryIdx)}
              y1={PAD.top} y2={H - PAD.bottom}
              stroke="var(--border-bright)" strokeWidth="1" strokeDasharray="3,3"
            />
          )}

          {/* Confidence band */}
          {bandPath && <path d={`M ${bandPath} Z`} fill="rgba(56,189,248,0.16)" stroke="none" />}

          {/* Bridge between actual and forecast */}
          {bridgeLine && (
            <path d={`M ${bridgeLine}`} fill="none" stroke="var(--accent)" strokeWidth="1.5"
              strokeDasharray="4,3" opacity="0.7" />
          )}

          {/* Actual line */}
          {actualLine && (
            <path d={`M ${actualLine}`} fill="none" stroke="var(--accent-2)" strokeWidth="2" />
          )}

          {/* Forecast median line */}
          {medianLine && (
            <path d={`M ${medianLine}`} fill="none" stroke="var(--accent)" strokeWidth="2" strokeDasharray="5,3" />
          )}

          {/* Hover crosshair */}
          {hovered && (
            <line x1={xScale(hoverIdx)} x2={xScale(hoverIdx)} y1={PAD.top} y2={H - PAD.bottom}
              stroke="var(--text-muted)" strokeWidth="1" strokeDasharray="2,2" />
          )}

          {/* Invisible hover capture columns */}
          {points.map((p, i) => (
            <rect key={i}
              x={xScale(i) - (W / points.length) / 2} y={PAD.top}
              width={W / points.length} height={H - PAD.top - PAD.bottom}
              fill="transparent"
              onMouseEnter={() => setHoverIdx(i)}
            />
          ))}
        </svg>

        {/* Tooltip */}
        {hovered && (
          <div style={{
            position: 'absolute', top: 8, left: 8,
            background: 'var(--bg-panel)', border: '1px solid var(--border-bright)',
            borderRadius: 'var(--r-sm)', padding: '8px 12px', fontSize: '0.78rem',
            direction: 'rtl', pointerEvents: 'none', boxShadow: 'var(--shadow-md)',
          }}>
            <p style={{ color: 'var(--text-muted)', marginBottom: '4px' }}>{hovered.date}</p>
            {hovered.actual != null && (
              <p style={{ color: 'var(--accent-2)' }}>فعلي: <b style={{ fontFamily: 'var(--font-mono)' }}>{fmt(hovered.actual)}</b></p>
            )}
            {hovered.median != null && (
              <>
                <p style={{ color: 'var(--accent)' }}>تنبؤ: <b style={{ fontFamily: 'var(--font-mono)' }}>{fmt(hovered.median)}</b></p>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>
                  نطاق: {fmt(hovered.low)} – {fmt(hovered.high)}
                </p>
              </>
            )}
          </div>
        )}
      </div>

      <div style={{
        marginTop: '0.8rem', padding: '8px 10px', background: 'var(--bg-panel)',
        borderRadius: 'var(--r-sm)', fontSize: '0.74rem', color: 'var(--text-muted)',
      }}>
        الخط المتقطع الفاصل يفصل بين البيانات الفعلية والتنبؤ المستقبلي (90 يوماً) — المنطقة المظللة تمثل نطاق الثقة بين أفضل وأسوأ سيناريو.
      </div>
    </div>
  )
}

/* ── Shared styles (match ForecastDashboard conventions) ── */
const cardSt = {
  background: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 'var(--r-lg)', padding: '1.2rem', marginBottom: '1.2rem',
}
const cardTitleSt = {
  fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-primary)',
}
const pillBtnSt = active => ({
  padding: '5px 12px', borderRadius: '100px', fontSize: '0.78rem', fontWeight: 600,
  border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
  background: active ? 'rgba(56,189,248,0.12)' : 'transparent',
  color: active ? 'var(--accent)' : 'var(--text-secondary)',
  cursor: 'pointer', whiteSpace: 'nowrap', fontFamily: 'var(--font-ar)',
  transition: 'all 0.18s', flexShrink: 0,
})
