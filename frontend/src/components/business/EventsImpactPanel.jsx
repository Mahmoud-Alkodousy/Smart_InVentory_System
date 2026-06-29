/**
 * components/business/EventsImpactPanel.jsx
 * ────────────────────────────────────────────
 * External Events Impact — Ramadan / Eid al-Fitr / Eid al-Adha /
 * Black Friday / Back-to-School.
 *
 * Why this matters: Chronos forecasts purely from historical sales
 * values — it has no notion of calendar dates, so it can't know that
 * Ramadan lands in February this year instead of March like last year
 * (the Hijri calendar shifts ~11 days earlier every Gregorian year).
 * This panel surfaces the explicit calendar layer the backend adds on
 * top of the statistical forecast (ml/events.py), and shows the extra
 * buffer it recommends — kept visibly separate from the core
 * recommended_stock number rather than silently folded into it.
 */

import React, { useMemo } from 'react'
import { card, cardTitle, kpiCard, fmt, EmptyState } from './shared'

const CATEGORY_ICON = { religious: '🌙', retail: '🛍️', seasonal: '🎒' }

export default function EventsImpactPanel({ events = [], recommendations = [] }) {
  const eventBufferTotal = useMemo(
    () => recommendations.reduce((s, r) => s + (r.event_buffer_units || 0), 0),
    [recommendations]
  )
  const affectedCount = useMemo(
    () => recommendations.filter(r => (r.event_tags || []).length > 0).length,
    [recommendations]
  )

  const upcoming = useMemo(
    () => [...events].sort((a, b) => a.days_until - b.days_until).slice(0, 6),
    [events]
  )

  return (
    <div style={card}>
      <p style={cardTitle}>🌙 External Events Impact — تأثير الأحداث الخارجية على الطلب</p>
      <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '1rem', lineHeight: 1.6 }}>
        نموذج Chronos يعتمد فقط على تاريخ المبيعات ولا "يعرف" تواريخ رمضان أو الأعياد
        لأنها تتحرك كل عام في التقويم الميلادي. هذه الطبقة تضيف وعياً تقويمياً صريحاً فوق التوقع الإحصائي.
      </p>

      {events.length === 0 ? (
        <EmptyState
          icon="🌙"
          title="لا توجد بيانات تقويمية متاحة لهذا التحليل"
          hint="تُحسب هذه الطبقة تلقائياً من تاريخ آخر بيانات مبيعات لديك — تأكد من وجود عمود date صالح."
        />
      ) : (
        <>
          {eventBufferTotal > 0 && (
            <div style={{ ...kpiCard('#fbbf24', 'rgba(251,191,36,0.08)'), marginBottom: '1rem' }}>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                📦 هامش إضافي موصى به بسبب أحداث ضمن نطاق التوقع الحالي (90 يوم)
              </span>
              <span style={{ fontSize: '1.8rem', fontWeight: 800, color: '#fbbf24', fontFamily: 'monospace', lineHeight: 1 }}>
                +{fmt(eventBufferTotal)} وحدة
              </span>
              <span style={{ fontSize: '0.73rem', color: 'var(--text-muted)' }}>
                يؤثر على {affectedCount} (صنف × فرع) — هذا الرقم إضافي ولا يُحسب تلقائياً ضمن "المخزون الموصى به" الأساسي
              </span>
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {upcoming.map((e, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px',
                padding: '10px 12px', borderRadius: 'var(--r-md)', flexWrap: 'wrap',
                background: e.is_ongoing ? 'rgba(56,189,248,0.06)' : 'var(--bg-panel)',
                border: `1px solid ${e.is_ongoing ? 'var(--accent)' : 'var(--border)'}`,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ fontSize: '1.3rem' }}>{CATEGORY_ICON[e.category] || '📅'}</span>
                  <div>
                    <p style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)' }}>{e.name_ar}</p>
                    <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      {e.is_ongoing ? 'جارٍ الآن' : `يبدأ بعد ${e.days_until} يوم`} · مدته {e.duration_days} يوم
                    </p>
                  </div>
                </div>
                <span style={{ fontFamily: 'monospace', fontWeight: 800, fontSize: '0.95rem', color: '#fbbf24' }}>
                  +{Math.round(e.uplift_pct * 100)}% طلب متوقع
                </span>
              </div>
            ))}
          </div>
          <p style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '10px' }}>
            * مواعيد رمضان والأعياد تقريبية (±يوم واحد) وفق التقديرات الفلكية المعتمدة — يُنصح بتأكيدها قرب الموعد.
          </p>
        </>
      )}
    </div>
  )
}
