/**
 * components/business/SupplierRiskPanel.jsx
 * ─────────────────────────────────────────────
 * Supplier Risk Analysis.
 *
 * Backed by ml/supplier_risk.py — only renders meaningfully when the
 * uploaded data includes a `supplier` column (optionally with
 * `supplier_lead_time_days`). Shows a clean empty-state otherwise,
 * explaining exactly which column names unlock the feature.
 */

import React from 'react'
import { card, cardTitle, kpiCard, fmt, RiskBadge, EmptyState } from './shared'

export default function SupplierRiskPanel({ suppliers = [], supplierSwitches = [] }) {
  const highRiskCount = suppliers.filter(s => s.risk_level === 'high').length
  const totalExposed  = suppliers.reduce((s, x) => s + (x.value_exposed || 0), 0)

  return (
    <div style={card}>
      <p style={cardTitle}>🚚 Supplier Risk Analysis — تحليل مخاطر الموردين</p>

      {suppliers.length === 0 ? (
        <EmptyState
          icon="🚚"
          title="لا توجد بيانات موردين في هذا الملف"
          hint={<>أضف عمود <code>supplier</code> (اسم المورد) واختيارياً <code>supplier_lead_time_days</code> (مدة التوريد بالأيام) لتفعيل هذا التحليل.</>}
        />
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '0.8rem', marginBottom: '1.2rem' }}>
            <div style={kpiCard('var(--danger)', 'rgba(248,113,113,0.07)')}>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                ⚠️ موردون مرتفعو الخطورة
              </span>
              <span style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--danger)', fontFamily: 'monospace', lineHeight: 1 }}>
                {highRiskCount}
              </span>
              <span style={{ fontSize: '0.73rem', color: 'var(--text-muted)' }}>من {suppliers.length} مورد</span>
            </div>
            {totalExposed > 0 && (
              <div style={kpiCard('var(--accent)', 'rgba(56,189,248,0.07)')}>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  💰 قيمة مخزون معرّضة
                </span>
                <span style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--accent)', fontFamily: 'monospace', lineHeight: 1 }}>
                  {fmt(totalExposed)}
                </span>
                <span style={{ fontSize: '0.73rem', color: 'var(--text-muted)' }}>عبر كل الموردين</span>
              </div>
            )}
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['المورد', 'عدد الأصناف', 'متوسط مدة التوريد', 'مستوى الخطورة', 'قيمة معرّضة', 'الإجراء المقترح']
                    .map(h => (
                      <th key={h} style={{ padding: '8px 10px', fontSize: '0.74rem', color: 'var(--text-muted)', textAlign: 'right', fontWeight: 600 }}>{h}</th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {suppliers.map((s, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '9px 10px', fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)' }}>{s.supplier}</td>
                    <td style={{ padding: '9px 10px', fontSize: '0.85rem', fontFamily: 'monospace', color: 'var(--text-secondary)' }}>{s.n_items}</td>
                    <td style={{ padding: '9px 10px', fontSize: '0.85rem', fontFamily: 'monospace' }}>{s.avg_lead_time_days} يوم</td>
                    <td style={{ padding: '9px 10px' }}><RiskBadge level={s.risk_level} label={s.risk_level_ar} /></td>
                    <td style={{ padding: '9px 10px', fontSize: '0.85rem', fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                      {s.value_exposed != null ? fmt(s.value_exposed) : '—'}
                    </td>
                    <td style={{ padding: '9px 10px', fontSize: '0.76rem', color: 'var(--text-muted)', maxWidth: '260px' }}>{s.recommendation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {supplierSwitches.length > 0 && (
            <div style={{ marginTop: '1.2rem', background: 'rgba(52,211,153,0.05)', border: '1px solid rgba(52,211,153,0.25)', borderRadius: 'var(--r-md)', padding: '0.9rem' }}>
              <p style={{ fontSize: '0.8rem', fontWeight: 700, color: '#34d399', marginBottom: '8px' }}>
                💡 اقتراحات لتبديل المورد (نفس الصنف يُورَّد من أكثر من مورد في بياناتك)
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {supplierSwitches.slice(0, 8).map((sw, i) => (
                  <p key={i} style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    صنف <b style={{ color: 'var(--text-primary)' }}>{sw.item}</b>: التحويل من{' '}
                    <span style={{ color: '#f87171' }}>{sw.current_supplier} ({sw.current_lead_time} يوم)</span> إلى{' '}
                    <span style={{ color: '#34d399', fontWeight: 700 }}>{sw.suggested_supplier} ({sw.suggested_lead_time} يوم)</span>
                    {' '}— توفير <b>{sw.days_saved} يوم</b> من مدة التوريد
                  </p>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
