import React from 'react'

/* ─────────────────────────────────────────────────────
   PipelineDiagram
   Visual explainer of the full system architecture —
   built for presenting to a judging panel: no jargon,
   one clear flow, the "smart" decision branch highlighted.
───────────────────────────────────────────────────── */

const STEPS = [
  {
    icon: '📁',
    title: 'رفع البيانات',
    desc: 'ملف Excel / CSV / JSON أو رابط Google Sheets — أي شكل، أي تسمية أعمدة.',
    color: 'var(--accent)',
  },
  {
    icon: '🤖',
    title: 'AI Cleaning Agent',
    desc: 'يفحص البيانات، يكتشف الأخطاء (تواريخ، أعمدة ناقصة، قيم غريبة)، ويصلحها تلقائياً.',
    color: 'var(--accent-2)',
    branch: true,
  },
  {
    icon: '📈',
    title: 'Chronos T5 — تنبؤ Zero-Shot',
    desc: 'نموذج LLM متخصص في السلاسل الزمنية يتنبأ بمبيعات 90 يوماً قادمة بدون أي تدريب مسبق على بياناتك.',
    color: 'var(--accent)',
  },
  {
    icon: '📦',
    title: 'التوصية الديناميكية',
    desc: 'هامش أمان يتغير حسب تذبذب كل منتج (Coefficient of Variation) — مش رقم ثابت للجميع.',
    color: 'var(--success)',
  },
  {
    icon: '🔬',
    title: 'فحص انحراف البيانات',
    desc: 'يقارن بيانات العميل الجديدة بإحصائيات سابقة وينبّه لو في تغيّر جوهري في نمط الطلب.',
    color: 'var(--warning)',
  },
  {
    icon: '📝',
    title: 'تقرير عربي بالذكاء الاصطناعي',
    desc: 'تقرير كامل بلغة عربية فصحى مفهومة لصاحب المحل — مش جداول تقنية.',
    color: 'var(--accent-2)',
  },
]

const branchSteps = [
  { ok: true,  label: 'البيانات نظيفة بالفعل', tag: 'مسار مباشر — سريع' },
  { ok: true,  label: 'مشاكل بسيطة (تنسيق / أعمدة)', tag: 'تنظيف تلقائي بـ pandas' },
  { ok: false, label: 'مشاكل معقدة لا يمكن إصلاحها بقواعد ثابتة', tag: 'LLM Agent يكتب ويختبر حل مخصص' },
]

export default function PipelineDiagram() {
  return (
    <div style={{ animation: 'fadeUp 0.4s ease forwards' }}>
      <div style={{ marginBottom: '1.4rem' }}>
        <h2 style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.4rem' }}>
          🧭 كيف يعمل النظام
        </h2>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          من رفع الملف إلى التقرير النهائي — ست مراحل، كل واحدة منها مستقلة وقابلة للمراقبة.
        </p>
      </div>

      {/* Vertical flow */}
      <div style={{ position: 'relative', paddingRight: '4px' }}>
        {STEPS.map((s, i) => (
          <div key={i} style={{ display: 'flex', gap: '1rem', position: 'relative' }}>
            {/* Connector column */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '44px', flexShrink: 0 }}>
              <div style={{
                width: '40px', height: '40px', borderRadius: '50%',
                background: 'var(--bg-card)', border: `2px solid ${s.color}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '1.1rem', boxShadow: `0 0 14px ${s.color}33`, zIndex: 1,
              }}>
                {s.icon}
              </div>
              {i < STEPS.length - 1 && (
                <div style={{ width: '2px', flex: 1, minHeight: '46px', background: 'var(--border-bright)', margin: '2px 0' }} />
              )}
            </div>

            {/* Content */}
            <div style={{ paddingBottom: i < STEPS.length - 1 ? '1.4rem' : 0, flex: 1 }}>
              <div style={{
                background: 'var(--bg-card)', border: '1px solid var(--border)',
                borderRadius: 'var(--r-md)', padding: '0.9rem 1.1rem',
              }}>
                <p style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.95rem', marginBottom: '4px' }}>
                  {i + 1}. {s.title}
                </p>
                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  {s.desc}
                </p>
              </div>

              {/* Self-healing decision branch — only under step 2 */}
              {s.branch && (
                <div style={{
                  marginTop: '0.7rem', marginRight: '0.4rem',
                  borderRight: '2px dashed var(--border-bright)', paddingRight: '1rem',
                  display: 'flex', flexDirection: 'column', gap: '6px',
                }}>
                  {branchSteps.map((b, j) => (
                    <div key={j} style={{
                      display: 'flex', alignItems: 'center', gap: '8px',
                      fontSize: '0.78rem', color: 'var(--text-muted)',
                    }}>
                      <span style={{ color: b.ok ? 'var(--success)' : 'var(--warning)' }}>
                        {b.ok ? '✓' : '⚡'}
                      </span>
                      <span style={{ color: 'var(--text-secondary)' }}>{b.label}</span>
                      <span style={{
                        fontSize: '0.7rem', padding: '1px 8px', borderRadius: '100px',
                        background: 'var(--bg-panel)', color: 'var(--text-muted)',
                        border: '1px solid var(--border)',
                      }}>
                        {b.tag}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Infra note */}
      <div style={{
        marginTop: '1.6rem', background: 'var(--bg-panel)', border: '1px solid var(--border)',
        borderRadius: 'var(--r-lg)', padding: '1.1rem 1.2rem',
      }}>
        <p style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--text-primary)', marginBottom: '8px' }}>
          ⚙️ البنية التحتية
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
          {[
            { icon: '⚡', label: 'Celery + Redis', desc: 'معالجة غير متزامنة — الـ API يفضل سريع مهما طالت المعالجة' },
            { icon: '⏰', label: 'مراقبة مجدولة', desc: 'تحديث تلقائي يومي / أسبوعي وتنبيه عند نفاد المخزون' },
            { icon: '🔐', label: 'API Key + Rate limiting', desc: 'حماية أساسية للاستخدام الإنتاجي' },
          ].map((b, i) => (
            <div key={i} style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{b.icon} {b.label}</span>
              <p style={{ color: 'var(--text-muted)', marginTop: '2px', lineHeight: 1.5 }}>{b.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
