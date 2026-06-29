import React, { useState } from 'react'

/* ── Feature name translations ─────────────────────── */
const FEATURE_AR = {
  sales_raw:           'المبيعات الخام',
  sales_lag_1:         'مبيعات اليوم السابق',
  sales_lag_7:         'مبيعات منذ أسبوع',
  sales_roll_mean_7:   'متوسط 7 أيام المتحرك',
  sales_roll_mean_28:  'متوسط 28 يوماً المتحرك',
  transactions:        'عدد المعاملات',
  onpromotion:         'نسبة العروض الترويجية',
}

function featureName(key) {
  return FEATURE_AR[key] || key
}

/* ── Deviation bar ─────────────────────────────────── */
function DeviationBar({ value, isDrifted }) {
  const pct = Math.min((value / 5) * 100, 100)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: '0.8rem', minWidth: '36px',
        color: isDrifted ? 'var(--danger)' : 'var(--success)',
        fontWeight: 600,
      }}>
        {value?.toFixed(2)}σ
      </span>
      <div style={{ flex: 1, height: '5px', background: 'var(--bg-panel)', borderRadius: '3px', overflow: 'hidden', minWidth: '60px' }}>
        <div style={{
          height: '100%', width: `${pct}%`,
          background: isDrifted
            ? 'linear-gradient(90deg, var(--warning), var(--danger))'
            : 'var(--success)',
          borderRadius: '3px', transition: 'width 0.6s ease',
        }} />
      </div>
    </div>
  )
}

/* ── Main component ──────────────────────────────────── */
export default function DriftAlert({ drift }) {
  const [showDetails, setShowDetails] = useState(false)

  if (!drift) return null

  const {
    has_drift, n_drifted, total_checked,
    alerts = [], feature_details = [],
    skipped_reason, summary,
    threshold,
  } = drift

  /* Skipped state */
  if (skipped_reason) {
    return (
      <div style={{ animation: 'fadeUp 0.4s ease forwards' }}>
        <h2 style={titleSt}>🔍 فحص جودة البيانات</h2>
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--r-lg)', padding: '3rem 2rem',
          textAlign: 'center',
        }}>
          <p style={{ fontSize: '2rem', marginBottom: '0.8rem' }}>⏭️</p>
          <p style={{ color: 'var(--text-secondary)', fontWeight: 600, marginBottom: '0.4rem' }}>
            تم تخطي فحص الجودة
          </p>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>{skipped_reason}</p>
        </div>
      </div>
    )
  }

  const borderColor = has_drift ? 'rgba(251,191,36,0.2)' : 'rgba(52,211,153,0.2)'
  const bgColor     = has_drift ? 'rgba(251,191,36,0.03)' : 'rgba(52,211,153,0.03)'

  return (
    <div style={{ animation: 'fadeUp 0.4s ease forwards' }}>
      <h2 style={titleSt}>🔍 فحص جودة البيانات</h2>

      <div style={{
        background: bgColor, border: `1px solid ${borderColor}`,
        borderRadius: 'var(--r-lg)', overflow: 'hidden',
      }}>
        {/* Banner */}
        <div style={{
          padding: '1.2rem 1.5rem',
          background: has_drift
            ? 'linear-gradient(135deg, rgba(251,191,36,0.1), rgba(248,113,113,0.06))'
            : 'linear-gradient(135deg, rgba(52,211,153,0.1), rgba(56,189,248,0.06))',
          borderBottom: `1px solid ${borderColor}`,
          display: 'flex', alignItems: 'center', gap: '14px',
        }}>
          <div style={{
            width: '44px', height: '44px', borderRadius: '50%', flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '1.4rem',
            background: has_drift ? 'rgba(251,191,36,0.12)' : 'rgba(52,211,153,0.12)',
            border: `1px solid ${borderColor}`,
          }}>
            {has_drift ? '⚠️' : '✅'}
          </div>
          <div>
            <p style={{
              fontSize: '1rem', fontWeight: 700, marginBottom: '3px',
              color: has_drift ? 'var(--warning)' : 'var(--success)',
            }}>
              {has_drift
                ? `مشاكل جودة: ${n_drifted} من أصل ${total_checked} فحص`
                : `لا مشاكل جودة — ${total_checked} فحص أُجري`}
            </p>
            <p style={{ fontSize: '0.83rem', color: 'var(--text-secondary)' }}>
              {has_drift
                ? 'بيانات المستخدم تختلف عن بيانات تدريب النموذج — قد تنخفض دقة التنبؤ'
                : 'بياناتك متوافقة مع بيانات التدريب — دقة التنبؤ مرتفعة'}
            </p>
          </div>
        </div>

        <div style={{ padding: '1.5rem' }}>
          {/* Alert items */}
          {alerts.length > 0 && (
            <div style={{ marginBottom: '1.2rem' }}>
              {alerts.map((alert, i) => (
                <div key={i} style={{
                  display: 'flex', gap: '10px', alignItems: 'flex-start',
                  padding: '10px 14px', marginBottom: '6px',
                  background: 'rgba(251,191,36,0.05)', border: '1px solid rgba(251,191,36,0.15)',
                  borderRadius: 'var(--r-sm)', fontSize: '0.85rem', color: 'var(--text-primary)',
                  lineHeight: 1.6, direction: 'rtl',
                }}>
                  <span style={{ color: 'var(--warning)', flexShrink: 0 }}>⚡</span>
                  <span>{alert}</span>
                </div>
              ))}
            </div>
          )}

          {/* Explanation */}
          <div style={{
            padding: '14px 16px', background: 'var(--bg-panel)',
            borderRadius: 'var(--r-sm)', border: '1px solid var(--border)',
            fontSize: '0.82rem', color: 'var(--text-secondary)',
            lineHeight: 1.7, direction: 'rtl', marginBottom: feature_details.length > 0 ? '1rem' : 0,
          }}>
            <strong style={{ color: 'var(--text-primary)' }}>ما هو فحص جودة البيانات؟</strong>
            {' '}النموذج تدرّب على بيانات بتوزيع إحصائي محدد. عندما تكون بياناتك مختلفة بشكل ملحوظ
            (مثلاً: حجم مبيعات مختلف جداً)، تنخفض دقة التوقعات.
            العتبة المستخدمة: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{threshold}σ</span>
          </div>

          {/* Details toggle */}
          {feature_details.length > 0 && (
            <>
              <button style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                padding: '7px 0', background: 'none',
                color: 'var(--accent)', fontSize: '0.83rem', fontWeight: 600,
                fontFamily: 'var(--font-ar)', cursor: 'pointer',
              }} onClick={() => setShowDetails(p => !p)}>
                <span style={{ transition: 'transform 0.2s', transform: showDetails ? 'rotate(90deg)' : 'none' }}>▶</span>
                {showDetails ? 'إخفاء تفاصيل الخصائص' : 'عرض تفاصيل الخصائص'}
              </button>

              {showDetails && (
                <div style={{ overflowX: 'auto', marginTop: '0.8rem' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', direction: 'rtl' }}>
                    <thead>
                      <tr>
                        {['الخاصية', 'القيمة المرجعية', 'قيمة بياناتك', 'درجة المشكلة', 'الحالة'].map(h => (
                          <th key={h} style={{
                            padding: '8px 12px', background: 'var(--bg-panel)',
                            color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.72rem',
                            textTransform: 'uppercase', letterSpacing: '0.05em',
                            borderBottom: '1px solid var(--border)', textAlign: 'right',
                            whiteSpace: 'nowrap',
                          }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {feature_details.map((fd, i) => (
                        <tr key={i} style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                          <td style={{ ...cellSt, color: 'var(--accent-2)' }}>
                            {featureName(fd.feature)}
                            <span style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                              {fd.feature}
                            </span>
                          </td>
                          <td style={{ ...cellSt, fontFamily: 'var(--font-mono)' }}>
                            {fd.train_mean?.toFixed(3)}
                          </td>
                          <td style={{
                            ...cellSt, fontFamily: 'var(--font-mono)',
                            color: fd.is_drifted ? 'var(--warning)' : 'var(--text-primary)',
                          }}>
                            {fd.incoming_mean?.toFixed(3)}
                          </td>
                          <td style={cellSt}>
                            <DeviationBar value={fd.deviation} isDrifted={fd.is_drifted} />
                          </td>
                          <td style={cellSt}>
                            <span style={{
                              display: 'inline-block', padding: '2px 9px',
                              borderRadius: '100px', fontSize: '0.72rem', fontWeight: 700,
                              background: fd.is_drifted ? 'rgba(248,113,113,0.1)' : 'rgba(52,211,153,0.1)',
                              color: fd.is_drifted ? 'var(--danger)' : 'var(--success)',
                              border: `1px solid ${fd.is_drifted ? 'rgba(248,113,113,0.25)' : 'rgba(52,211,153,0.25)'}`,
                            }}>
                              {fd.is_drifted ? '⚠ مشكلة' : '✓ جيد'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

const titleSt = {
  fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '1.2rem',
}
const cellSt = {
  padding: '9px 12px', borderBottom: '1px solid rgba(56,189,248,0.05)',
  color: 'var(--text-primary)', fontSize: '0.82rem',
}
