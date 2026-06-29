/**
 * components/business/MultiBranchPanel.jsx
 * ────────────────────────────────────────────
 * Multi-Branch Optimization — "move it, don't buy it".
 *
 * Backed by ml/multi_branch.py — needs at least 2 stores and a
 * `current_stock` column to produce suggestions. Shows a clean
 * empty-state otherwise.
 */

import React, { useMemo } from 'react'
import { card, cardTitle, kpiCard, fmt, EmptyState } from './shared'

export default function MultiBranchPanel({ transfers = [] }) {
  const totalSaved = useMemo(
    () => transfers.reduce((s, t) => s + (t.value_saved || 0), 0),
    [transfers]
  )
  const totalUnits = useMemo(
    () => transfers.reduce((s, t) => s + (t.quantity || 0), 0),
    [transfers]
  )

  return (
    <div style={card}>
      <p style={cardTitle}>🔁 Multi-Branch Optimization — نقل المخزون بين الفروع</p>

      {transfers.length === 0 ? (
        <EmptyState
          icon="🔁"
          title="لا توجد اقتراحات نقل بين الفروع حالياً"
          hint={<>تحتاج هذه الميزة لعمود <code>current_stock</code> وأكثر من فرع/متجر واحد في بياناتك — أو أن المخزون متوازن فعلاً بين الفروع 👍</>}
        />
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '0.8rem', marginBottom: '1.2rem' }}>
            <div style={kpiCard('#34d399', 'rgba(52,211,153,0.08)')}>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                💚 توفير محتمل من النقل (بدل الشراء)
              </span>
              <span style={{ fontSize: '1.7rem', fontWeight: 800, color: '#34d399', fontFamily: 'monospace', lineHeight: 1 }}>
                {fmt(totalSaved)}
              </span>
              <span style={{ fontSize: '0.73rem', color: 'var(--text-muted)' }}>عبر {transfers.length} عملية نقل مقترحة</span>
            </div>
            <div style={kpiCard('var(--accent)', 'rgba(56,189,248,0.07)')}>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                📦 إجمالي الوحدات المنقولة
              </span>
              <span style={{ fontSize: '1.7rem', fontWeight: 800, color: 'var(--accent)', fontFamily: 'monospace', lineHeight: 1 }}>
                {fmt(totalUnits)}
              </span>
              <span style={{ fontSize: '0.73rem', color: 'var(--text-muted)' }}>وحدة بدلاً من طلبها من المورد</span>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {transfers.slice(0, 20).map((t, i) => (
              <div key={i} style={{
                padding: '10px 12px', borderRadius: 'var(--r-md)',
                background: 'var(--bg-panel)', border: '1px solid var(--border)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-primary)' }}>
                    نقل <b style={{ color: 'var(--accent)', fontFamily: 'monospace' }}>{fmt(t.quantity)}</b> وحدة من صنف{' '}
                    <b>{t.item}</b> — من فرع <span style={{ color: '#f87171', fontWeight: 700 }}>{t.from_store}</span>{' '}
                    إلى فرع <span style={{ color: '#34d399', fontWeight: 700 }}>{t.to_store}</span>
                  </p>
                  {t.value_saved != null && (
                    <span style={{
                      fontFamily: 'monospace', fontWeight: 800, fontSize: '0.85rem', color: '#34d399',
                      background: 'rgba(52,211,153,0.1)', padding: '3px 10px', borderRadius: '100px',
                      border: '1px solid rgba(52,211,153,0.3)',
                    }}>
                      وفّر {fmt(t.value_saved)}
                    </span>
                  )}
                </div>
                <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                  فرع {t.from_store}: {fmt(t.from_store_stock_before)} ← {fmt(t.from_store_stock_after)} وحدة
                  {'  ·  '}
                  فرع {t.to_store}: {fmt(t.to_store_stock_before)} → {fmt(t.to_store_stock_after)} وحدة
                </p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
