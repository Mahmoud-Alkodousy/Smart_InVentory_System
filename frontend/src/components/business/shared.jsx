/**
 * components/business/shared.jsx
 * ─────────────────────────────────
 * Shared presentation helpers for the Business Impact Layer panels
 * (SupplierRiskPanel, MultiBranchPanel, EventsImpactPanel, PurchaseOrderPanel).
 *
 * Deliberately mirrors the look & feel already established in
 * BusinessDashboard.jsx (same card/kpiCard/fmt/pct/Gauge conventions) so
 * the new sections feel native rather than bolted on. Kept as a separate
 * module instead of importing from BusinessDashboard.jsx so the existing,
 * working file never needs to change its internals.
 */

import React from 'react'

export function fmt(n, currency = false) {
  if (n == null || isNaN(n)) return '—'
  const prefix = currency ? 'EGP ' : ''
  if (n >= 1_000_000) return prefix + (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000)     return prefix + (n / 1_000).toFixed(1) + 'K'
  return prefix + Math.round(n).toLocaleString('ar-EG')
}

export function pct(n) {
  if (n == null || isNaN(n)) return '—'
  return n.toFixed(1) + '%'
}

export const card = {
  background: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 'var(--r-lg)', padding: '1.2rem',
}

export const cardTitle = {
  fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-primary)',
  marginBottom: '1rem', letterSpacing: '0.02em',
}

export const kpiCard = (accent = 'var(--accent)', glow = 'rgba(56,189,248,0.08)') => ({
  background: glow, border: `1px solid ${accent}30`,
  borderRadius: 'var(--r-md)', padding: '1rem 1.1rem',
  display: 'flex', flexDirection: 'column', gap: '4px',
})

/* Risk-level badge (used by SupplierRiskPanel) — low/medium/high */
export const RISK_STYLE = {
  low:    { color: '#34d399', bg: 'rgba(52,211,153,0.12)', border: 'rgba(52,211,153,0.3)' },
  medium: { color: '#fbbf24', bg: 'rgba(251,191,36,0.12)', border: 'rgba(251,191,36,0.3)'  },
  high:   { color: '#f87171', bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.3)' },
}

export function RiskBadge({ level, label }) {
  const s = RISK_STYLE[level] || RISK_STYLE.medium
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: '100px',
      fontSize: '0.73rem', fontWeight: 700,
      background: s.bg, color: s.color, border: `1px solid ${s.border}`,
    }}>{label}</span>
  )
}

/* Consistent "feature needs more data" placeholder used by several panels */
export function EmptyState({ icon = 'ℹ️', title, hint }) {
  return (
    <div style={{
      textAlign: 'center', padding: '1.6rem 1rem',
      color: 'var(--text-muted)', fontSize: '0.85rem',
      background: 'var(--bg-panel)', borderRadius: 'var(--r-md)',
      border: '1px dashed var(--border)',
    }}>
      <div style={{ fontSize: '1.6rem', marginBottom: '0.4rem' }}>{icon}</div>
      <p style={{ fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '4px' }}>{title}</p>
      {hint && <p style={{ fontSize: '0.76rem' }}>{hint}</p>}
    </div>
  )
}

export function Gauge({ value, max = 100, color = 'var(--accent)', label }) {
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
        <path
          d={`M ${toXY(-90).x} ${toXY(-90).y} A ${r} ${r} 0 1 1 ${toXY(90).x} ${toXY(90).y}`}
          fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="10" strokeLinecap="round"
        />
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

export const API     = import.meta.env.VITE_API_URL || ''
export const API_KEY = import.meta.env.VITE_API_KEY || ''

export function authHeaders() {
  return API_KEY ? { 'X-API-Key': API_KEY } : {}
}
