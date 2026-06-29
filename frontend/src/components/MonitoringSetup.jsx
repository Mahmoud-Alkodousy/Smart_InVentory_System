import React, { useState } from 'react'

const API     = import.meta.env.VITE_API_URL || ''
const API_KEY = import.meta.env.VITE_API_KEY || ''

const SHEETS_ID_RE = /https:\/\/docs\.google\.com\/spreadsheets\/d\/([a-zA-Z0-9_-]+)/
const GID_RE       = /[#&?]gid=(\d+)/

async function fetchSheetAsCsv(url) {
  const id = SHEETS_ID_RE.exec(url)?.[1]
  if (!id) throw new Error('رابط Google Sheets غير صحيح.')
  const gid = GID_RE.exec(url)?.[1] ?? '0'
  const candidates = [
    `https://docs.google.com/spreadsheets/d/${id}/gviz/tq?tqx=out:csv&gid=${gid}`,
    `https://docs.google.com/spreadsheets/d/${id}/export?format=csv&gid=${gid}`,
    `https://docs.google.com/spreadsheets/d/${id}/pub?output=csv&gid=${gid}`,
  ]
  for (const u of candidates) {
    try {
      const res = await fetch(u, { credentials: 'omit' })
      if (!res.ok) continue
      const ct = res.headers.get('Content-Type') || ''
      if (ct.includes('text/html')) throw new Error('الجدول خاص — اذهب إلى مشاركة ← أي شخص لديه الرابط.')
      const text = await res.text()
      if (!text?.trim()) throw new Error('الجدول فارغ.')
      if (text.trimStart().startsWith('<')) throw new Error('الجدول خاص — اذهب إلى مشاركة ← أي شخص لديه الرابط.')
      return new Blob([text], { type: 'text/csv' })
    } catch (e) {
      if (e.message.includes('خاص') || e.message.includes('فارغ')) throw e
    }
  }
  throw new Error('تعذّر جلب الجدول. تأكد من مشاركته بوضع «أي شخص لديه الرابط».')
}

const FREQUENCIES = [
  { value: 'daily',      label: 'يومياً',      icon: '📅', desc: 'كل يوم الساعة 6 صباحاً UTC' },
  { value: 'weekly',     label: 'أسبوعياً',    icon: '📆', desc: 'كل إثنين' },
  { value: 'monthly',    label: 'شهرياً',      icon: '🗓️', desc: 'أول كل شهر' },
  { value: 'quarterly',  label: 'كل 3 أشهر',  icon: '📊', desc: 'يناير، أبريل، يوليو، أكتوبر' },
  { value: 'semiannual', label: 'كل 6 أشهر',  icon: '📈', desc: 'يناير ويوليو' },
]

export default function MonitoringSetup({ onBack }) {
  const [sheetsUrl,    setSheetsUrl]    = useState('')
  const [email,        setEmail]        = useState('')
  const [frequency,    setFrequency]    = useState('weekly')
  const [leadTime,     setLeadTime]     = useState(7)
  const [loading,      setLoading]      = useState(false)
  const [loadingLabel, setLoadingLabel] = useState('')
  const [error,        setError]        = useState('')
  const [registered,   setRegistered]   = useState(null)
  const [testLoading,  setTestLoading]  = useState(false)
  const [testMsg,      setTestMsg]      = useState('')

  const authHeaders = () => API_KEY ? { 'X-API-Key': API_KEY } : {}

  async function handleRegister() {
    if (!sheetsUrl.trim() || !email.trim()) return
    setLoading(true)
    setError('')
    try {
      setLoadingLabel('جارٍ جلب البيانات من Google...')
      const csvBlob = await fetchSheetAsCsv(sheetsUrl.trim())

      setLoadingLabel('جارٍ التسجيل...')
      const form = new FormData()
      form.append('file',           csvBlob, 'sheet.csv')
      form.append('email',          email.trim())
      form.append('frequency',      frequency)
      form.append('lead_time_days', leadTime)

      const res  = await fetch(`${API}/api/monitor/register-with-file`, {
        method: 'POST', headers: authHeaders(), body: form,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'فشل التسجيل')
      setRegistered(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
      setLoadingLabel('')
    }
  }

  async function handleTestRun() {
    if (!registered?.user?.user_id) return
    setTestLoading(true)
    setTestMsg('')
    try {
      const res  = await fetch(`${API}/api/monitor/users/${registered.user.user_id}/run`, {
        method: 'POST', headers: authHeaders(),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'فشل التشغيل')
      setTestMsg(`✅ بدأ التحليل — سيصلك إيميل على ${email} خلال دقيقة أو دقيقتين`)
    } catch (e) {
      setTestMsg('❌ ' + e.message)
    } finally {
      setTestLoading(false)
    }
  }

  const selectedFreq = FREQUENCIES.find(f => f.value === frequency)
  const canSubmit = sheetsUrl.trim() && email.trim() && email.includes('@') && !loading

  return (
    <div className="monitor-setup-page" style={{ maxWidth: '900px', margin: '0 auto', padding: '0 1.5rem', animation: 'fadeUp 0.4s ease forwards' }}>

      {/* Header */}
      <div style={{ marginBottom: '1.8rem' }}>
        <button onClick={onBack} style={s.backBtn}>← رجوع</button>
        <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '1rem', marginBottom: '0.3rem' }}>
          📬 إشعارات المخزون التلقائية
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          سجّل بياناتك مرة واحدة — وهتجيلك إيميل تلقائي بتحليل المخزون
        </p>
      </div>

      {!registered ? (
        <div className="monitor-setup-grid" style={{ ...s.card, display: 'grid', gridTemplateColumns: '1.1fr 0.9fr', gap: '2rem', alignItems: 'start' }}>

          {/* Left column: form fields */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>

            {/* Email */}
            <div style={s.field}>
              <label style={s.label}>📧 إيميلك</label>
              <input
                style={s.input}
                type="email"
                placeholder="example@gmail.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                dir="ltr"
              />
              <span style={s.hint}>هنا هيجيلك التقرير والإشعارات</span>
            </div>

            {/* Google Sheets URL */}
            <div style={s.field}>
              <label style={s.label}>📊 رابط Google Sheets</label>
              <input
                style={s.input}
                placeholder="https://docs.google.com/spreadsheets/d/..."
                value={sheetsUrl}
                onChange={e => setSheetsUrl(e.target.value)}
                dir="ltr"
              />
              <span style={s.hint}>تأكد أن الجدول مشارك بوضع «أي شخص لديه الرابط»</span>
            </div>

            {/* Lead time */}
            <div style={s.field}>
              <label style={s.label}>⏱ مدة التوريد (أيام)</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <input
                  type="range"
                  min="1"
                  max="60"
                  value={leadTime}
                  onChange={e => setLeadTime(Number(e.target.value))}
                  style={{ flex: 1, accentColor: 'var(--accent)' }}
                />
                <span style={{
                  minWidth: '44px', textAlign: 'center',
                  background: 'var(--bg-base)', border: '1px solid var(--border)',
                  borderRadius: 'var(--r-sm)', padding: '4px 8px',
                  color: 'var(--accent)', fontWeight: 600, fontSize: '0.85rem',
                }}>
                  {leadTime}
                </span>
              </div>
              <span style={s.hint}>الوقت المتوقع من إصدار الطلبية حتى وصول البضاعة</span>
            </div>

            {error && (
              <div style={s.error}>⚠️ {error}</div>
            )}

            <button
              style={s.primaryBtn(canSubmit)}
              onClick={handleRegister}
              disabled={!canSubmit}
            >
              {loading
                ? <><span style={s.spinner} /> {loadingLabel || 'جارٍ...'}</>
                : '🚀 تفعيل الإشعارات'}
            </button>
          </div>

          {/* Right column: frequency + how it works */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>

            {/* Frequency picker */}
            <div style={s.field}>
              <label style={s.label}>🔁 تكرار المتابعة</label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px', marginTop: '4px' }}>
                {FREQUENCIES.map(f => (
                  <button
                    key={f.value}
                    onClick={() => setFrequency(f.value)}
                    style={{
                      padding: '10px 8px',
                      borderRadius: 'var(--r-md)',
                      border: frequency === f.value
                        ? '1.5px solid var(--accent)'
                        : '1px solid var(--border)',
                      background: frequency === f.value
                        ? 'rgba(56,189,248,0.08)'
                        : 'var(--bg-base)',
                      color: frequency === f.value ? 'var(--accent)' : 'var(--text-secondary)',
                      fontSize: '0.8rem',
                      fontWeight: frequency === f.value ? 600 : 400,
                      cursor: 'pointer',
                      textAlign: 'center',
                      fontFamily: 'var(--font-ar)',
                      transition: 'all 0.18s ease',
                    }}
                  >
                    <div style={{ fontSize: '1.1rem', marginBottom: '3px' }}>{f.icon}</div>
                    {f.label}
                  </button>
                ))}
              </div>
              {selectedFreq && (
                <span style={{ ...s.hint, color: 'var(--accent)', opacity: 0.8, marginTop: '6px' }}>
                  ⏰ {selectedFreq.desc}
                </span>
              )}
            </div>
          </div>

        </div>

      ) : (
        /* Success state */
        <div style={s.card}>
          <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
            <div style={{
              width: '64px', height: '64px', borderRadius: '50%',
              background: 'rgba(52,211,153,0.1)', border: '2px solid rgba(52,211,153,0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '2rem', margin: '0 auto 1rem',
            }}>✅</div>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--success)', marginBottom: '0.4rem' }}>
              تم التسجيل بنجاح!
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem' }}>
              تم إرسال إيميل ترحيبي إلى <strong style={{ color: 'var(--accent)' }}>{registered.user?.email}</strong>
            </p>
          </div>

          {/* Summary */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '1.2rem' }}>
            {[
              { label: 'الإيميل', value: registered.user?.email, mono: true },
              { label: 'التكرار', value: FREQUENCIES.find(f => f.value === registered.user?.frequency)?.label || registered.user?.frequency },
              { label: 'مدة التوريد', value: `${registered.user?.lead_time_days} يوم` },
              { label: 'معرّفك', value: (registered.user?.user_id || '').slice(0, 8) + '…', mono: true },
            ].map(({ label, value, mono }) => (
              <div key={label} style={{
                background: 'var(--bg-base)', borderRadius: 'var(--r-sm)',
                padding: '10px 12px', border: '1px solid var(--border)',
              }}>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '3px' }}>{label}</div>
                <div style={{
                  fontSize: mono ? '0.78rem' : '0.9rem',
                  color: 'var(--text-primary)', fontWeight: 600,
                  fontFamily: mono ? 'var(--font-mono)' : 'var(--font-ar)',
                  wordBreak: 'break-all',
                }}>
                  {value}
                </div>
              </div>
            ))}
          </div>

          <button
            style={s.primaryBtn(!testLoading)}
            onClick={handleTestRun}
            disabled={testLoading}
          >
            {testLoading
              ? <><span style={s.spinner} /> جارٍ التحليل...</>
              : '🧪 جرّب الإشعار دلوقتي'}
          </button>

          {testMsg && (
            <div style={testMsg.startsWith('✅') ? s.success : s.error}>
              {testMsg}
            </div>
          )}

          <button onClick={onBack} style={{ ...s.backBtn, display: 'block', textAlign: 'center', marginTop: '12px', width: '100%' }}>
            ← رجوع للرئيسية
          </button>
        </div>
      )}
    </div>
  )
}

const s = {
  card:     { background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--r-lg)', padding: '1.8rem', display: 'flex', flexDirection: 'column', gap: '1.2rem' },
  field:    { display: 'flex', flexDirection: 'column', gap: '5px' },
  label:    { fontSize: '0.79rem', color: 'var(--text-secondary)', fontWeight: 600 },
  hint:     { fontSize: '0.72rem', color: 'var(--text-muted)' },
  input:    { width: '100%', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--r-sm)', padding: '10px 12px', fontSize: '0.86rem', color: 'var(--text-primary)', boxSizing: 'border-box', outline: 'none', fontFamily: 'var(--font-ar)' },
  backBtn:  { background: 'none', border: 'none', color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer', padding: 0, fontFamily: 'var(--font-ar)' },
  error:    { padding: '10px 14px', background: 'rgba(248,113,113,0.07)', border: '1px solid rgba(248,113,113,0.25)', borderRadius: 'var(--r-sm)', color: 'var(--danger)', fontSize: '0.84rem' },
  success:  { padding: '10px 14px', background: 'rgba(52,211,153,0.07)', border: '1px solid rgba(52,211,153,0.25)', borderRadius: 'var(--r-sm)', color: 'var(--success)', fontSize: '0.84rem' },
  spinner:  { display: 'inline-block', width: '14px', height: '14px', border: '2px solid rgba(255,255,255,0.3)', borderTop: '2px solid #fff', borderRadius: '50%', animation: 'spin 0.8s linear infinite' },
  primaryBtn: ok => ({
    width: '100%', padding: '13px', borderRadius: 'var(--r-md)', fontSize: '0.95rem',
    fontWeight: 700, fontFamily: 'var(--font-ar)', display: 'flex',
    alignItems: 'center', justifyContent: 'center', gap: '8px',
    background: ok ? 'linear-gradient(135deg, var(--accent), var(--accent-2))' : 'var(--bg-base)',
    color: ok ? '#fff' : 'var(--text-muted)',
    boxShadow: ok ? '0 4px 20px var(--accent-glow)' : 'none',
    cursor: ok ? 'pointer' : 'not-allowed',
    border: ok ? 'none' : '1px solid var(--border)',
    transition: 'all 0.2s ease',
  }),
  infoBox: {
    padding: '14px 16px',
    background: 'rgba(56,189,248,0.03)',
    border: '1px solid rgba(56,189,248,0.1)',
    borderRadius: 'var(--r-md)',
  },
}
