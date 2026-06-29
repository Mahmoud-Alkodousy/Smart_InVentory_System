import React, { useState, useRef, useCallback } from 'react'

const API     = import.meta.env.VITE_API_URL || ''
const API_KEY = import.meta.env.VITE_API_KEY || ''

// ── Google Sheets helpers ─────────────────────────────────────────────────────
const SHEETS_ID_RE = /https:\/\/docs\.google\.com\/spreadsheets\/d\/([a-zA-Z0-9_-]+)/
const GID_RE       = /[#&?]gid=(\d+)/

function extractSheetId(url) {
  const m = SHEETS_ID_RE.exec(url)
  return m ? m[1] : null
}

function extractGid(url) {
  const m = GID_RE.exec(url)
  return m ? m[1] : '0'
}

/**
 * Fetch the Google Sheet as CSV **from the browser** using multiple fallback URLs.
 * Returns a Blob (CSV) or throws an error with an Arabic message.
 */
async function fetchSheetAsCsv(url) {
  const id  = extractSheetId(url)
  if (!id) throw new Error('رابط Google Sheets غير صحيح.')

  const gid = extractGid(url)

  // Three different export endpoints — try them in order
  const candidates = [
    `https://docs.google.com/spreadsheets/d/${id}/gviz/tq?tqx=out:csv&gid=${gid}`,
    `https://docs.google.com/spreadsheets/d/${id}/export?format=csv&gid=${gid}`,
    `https://docs.google.com/spreadsheets/d/${id}/pub?output=csv&gid=${gid}`,
  ]

  let lastError = ''
  for (const candidate of candidates) {
    try {
      const res = await fetch(candidate, { credentials: 'omit' })

      if (!res.ok) {
        if (res.status === 401 || res.status === 403) {
          throw new Error(
            'تعذّر الوصول إلى الجدول (403). تأكد أن الجدول مشارك بوضع «أي شخص لديه الرابط - عارض».'
          )
        }
        lastError = `HTTP ${res.status}`
        continue
      }

      const contentType = res.headers.get('Content-Type') || ''

      // Google returns HTML when the sheet is private
      if (contentType.includes('text/html')) {
        throw new Error(
          'الجدول خاص أو يتطلب تسجيل دخول. اذهب إلى مشاركة ← أي شخص لديه الرابط ← عارض.'
        )
      }

      const text = await res.text()

      // Empty sheet
      if (!text || text.trim().length === 0) {
        throw new Error('الجدول فارغ أو لا يحتوي على بيانات.')
      }

      // Looks like HTML (private sheet returning redirect page)
      if (text.trimStart().startsWith('<!DOCTYPE') || text.trimStart().startsWith('<html')) {
        throw new Error(
          'الجدول خاص أو يتطلب تسجيل دخول. اذهب إلى مشاركة ← أي شخص لديه الرابط ← عارض.'
        )
      }

      return new Blob([text], { type: 'text/csv' })

    } catch (err) {
      // Re-throw explicit Arabic messages immediately
      if (err.message.includes('تعذّر') || err.message.includes('خاص') || err.message.includes('فارغ')) {
        throw err
      }
      lastError = err.message
      // Try next candidate
    }
  }

  throw new Error(
    `تعذّر جلب الجدول من Google Sheets. تأكد من:\n` +
    `1. أن الجدول مشارك بوضع «أي شخص لديه الرابط»\n` +
    `2. صحة الرابط\n` +
    `(${lastError})`
  )
}

// ─────────────────────────────────────────────────────────────────────────────

export default function FileUpload({ onJobStart, onDemoMode }) {
  const [tab, setTab]             = useState('file')
  const [file, setFile]           = useState(null)
  const [sheetsUrl, setSheetsUrl] = useState('')
  const [leadTime, setLeadTime]   = useState(7)
  const [context, setContext]     = useState('')
  const [unitPrice, setUnitPrice] = useState('')    // NEW: optional unit price
  const [dragging, setDragging]   = useState(false)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState('')
  const [fetchingSheet, setFetchingSheet] = useState(false)
  const inputRef = useRef()

  const onDrop = useCallback(e => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) setFile(f)
  }, [])

  const isReady = tab === 'file' ? !!file : sheetsUrl.trim().length > 10

  async function handleSubmit() {
    if (!isReady || loading) return
    setLoading(true)
    setError('')
    try {
      const form = new FormData()

      if (tab === 'sheets') {
        // ── Fetch CSV from browser, then upload as a regular file ──
        setFetchingSheet(true)
        let csvBlob
        try {
          csvBlob = await fetchSheetAsCsv(sheetsUrl)
        } finally {
          setFetchingSheet(false)
        }
        form.append('file', csvBlob, 'google_sheet.csv')
      } else {
        form.append('file', file)
      }

      form.append('lead_time_days', leadTime)
      form.append('extra_context', context)
      if (unitPrice !== '' && Number(unitPrice) > 0) {
        form.append('unit_price', Number(unitPrice))
      }

      const headers = {}
      if (API_KEY) headers['X-API-Key'] = API_KEY

      const res = await fetch(`${API}/api/upload`, { method: 'POST', headers, body: form })
      if (!res.ok) {
        let msg = 'فشل رفع الملف'
        try { const d = await res.json(); msg = d.detail || msg } catch { msg = await res.text().catch(() => msg) }
        throw new Error(msg)
      }
      const data = await res.json()
      onJobStart(data.job_id)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  // Loading label changes depending on stage
  const loadingLabel = fetchingSheet ? 'جارٍ جلب البيانات من Google...' : 'جارٍ الرفع...'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem', height: '100%' }}>

      {/* ── Demo Mode banner ────────────────────────── */}
      {onDemoMode && (
        <button
          onClick={onDemoMode}
          style={{
            width: '100%', padding: '10px 14px',
            background: 'linear-gradient(135deg, rgba(167,139,250,0.15), rgba(56,189,248,0.1))',
            border: '1px solid rgba(167,139,250,0.4)', borderRadius: 'var(--r-md)',
            color: '#a78bfa', fontWeight: 700, fontSize: '0.88rem', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
            letterSpacing: '0.02em', transition: 'all 0.2s',
            fontFamily: 'var(--font-ar)',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'linear-gradient(135deg, rgba(167,139,250,0.22), rgba(56,189,248,0.15))' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'linear-gradient(135deg, rgba(167,139,250,0.15), rgba(56,189,248,0.1))' }}
        >
          <span style={{ fontSize: '1.1rem' }}>🎯</span>
          <span>تجربة Demo Mode</span>
          <span style={{ fontSize: '0.72rem', fontWeight: 400, opacity: 0.8 }}>— بيانات واقعية جاهزة بدون Upload</span>
        </button>
      )}

      {/* ── Source tabs ─────────────────────────────── */}
      <div style={tabBarSt}>
        {[['file', '📁', 'رفع ملف'], ['sheets', '📊', 'Google Sheets']].map(([id, icon, label]) => (
          <button key={id} style={tabSt(tab === id)} onClick={() => setTab(id)}>
            <span>{icon}</span>
            <span>{label}</span>
          </button>
        ))}
      </div>

      {/* ── Drop zone / URL input ───────────────────── */}
      {tab === 'file' ? (
        <div
          style={dropzoneSt(dragging, !!file)}
          onDrop={onDrop}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onClick={() => inputRef.current?.click()}
        >
          <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls,.json"
            style={{ display: 'none' }} onChange={e => setFile(e.target.files[0])} />

          {file ? (
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>✅</div>
              <p style={{ fontWeight: 700, color: 'var(--success)', marginBottom: '0.6rem', fontSize: '0.9rem' }}>
                {file.name}
              </p>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                  {(file.size / 1024).toFixed(1)} KB
                </span>
                <button
                  onClick={e => { e.stopPropagation(); setFile(null) }}
                  style={{ background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.25)', color: 'var(--danger)', fontSize: '0.75rem', padding: '2px 8px', borderRadius: '4px' }}
                >
                  حذف
                </button>
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '2.2rem', marginBottom: '0.7rem', animation: 'float 3s ease-in-out infinite' }}>☁️</div>
              <p style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.3rem', fontSize: '0.9rem' }}>
                اسحب الملف هنا أو اضغط للاختيار
              </p>
              <div style={{ display: 'flex', gap: '5px', justifyContent: 'center', flexWrap: 'wrap', marginTop: '0.5rem' }}>
                {['.csv', '.xlsx', '.xls', '.json'].map(f => (
                  <span key={f} style={fmtBadgeSt}>{f}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={labelSt}>رابط Google Sheets (عام)</label>
          <input
            style={urlInputSt}
            placeholder="https://docs.google.com/spreadsheets/d/..."
            value={sheetsUrl}
            onChange={e => setSheetsUrl(e.target.value)}
            onFocus={e => e.target.style.borderColor = 'var(--border-focus)'}
            onBlur={e => e.target.style.borderColor = 'var(--border)'}
          />
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            تأكد من مشاركة الجدول بوضع «أي شخص لديه الرابط - عارض»
          </p>
        </div>
      )}

      {/* ── Options row ─────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.9rem' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
          <label style={labelSt}>⏱ مدة التوريد (أيام)</label>
          <input
            type="number" min="1" max="365"
            style={optInputSt}
            value={leadTime}
            onChange={e => setLeadTime(Number(e.target.value))}
          />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
          <label style={labelSt}>💬 معلومات إضافية <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(اختياري)</span></label>
          <input
            type="text"
            placeholder="مثال: اسم المتجر، الموسم..."
            style={optInputSt}
            value={context}
            onChange={e => setContext(e.target.value)}
          />
        </div>
      </div>

      {/* ── Unit price (optional — unlocks financial KPIs) ─── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
        <label style={labelSt}>
          💰 سعر الوحدة{' '}
          <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>
            (اختياري — يُفعِّل تحليل الأثر المالي في التقرير)
          </span>
        </label>
        <input
          type="number" min="0" step="0.01"
          placeholder="مثال: 45.50  (الوحدة: الجنيه أو الدولار)"
          style={optInputSt}
          value={unitPrice}
          onChange={e => setUnitPrice(e.target.value)}
        />
      </div>

      {/* ── Optional enrichment columns hint ─────────────────── */}
      <details style={{
        background: 'var(--bg-base)', border: '1px solid var(--border)',
        borderRadius: 'var(--r-sm)', padding: '8px 12px', fontSize: '0.78rem',
      }}>
        <summary style={{ cursor: 'pointer', color: 'var(--text-secondary)', fontWeight: 600 }}>
          📋 أعمدة اختيارية تفعّل تحليلات أكثر (سعر لكل صنف، مورّدين، فروع...)
        </summary>
        <div style={{ marginTop: '8px', color: 'var(--text-muted)', lineHeight: 1.8 }}>
          أضف أي من هذه الأعمدة في ملفك ليكتشفها النظام تلقائياً — كلها اختيارية:
          <ul style={{ margin: '6px 0 0', paddingInlineStart: '1.2rem' }}>
            <li><code>unit_price</code> أو <code>price</code> — سعر كل صنف على حدة بدل سعر عام واحد</li>
            <li><code>current_stock</code> أو <code>on_hand</code> أو <code>stock</code> — المخزون الحالي، لحساب الوفر واقتراحات النقل بين الفروع</li>
            <li><code>supplier</code> — اسم المورد، لتفعيل تحليل مخاطر الموردين</li>
            <li><code>supplier_lead_time_days</code> أو <code>lead_time_days</code> — مدة توريد كل مورد بالأيام</li>
          </ul>
        </div>
      </details>

      {/* ── Error ───────────────────────────────────── */}
      {error && (
        <div style={errorBoxSt}>⚠️ {error}</div>
      )}

      {/* ── Submit ──────────────────────────────────── */}
      <button
        style={submitBtnSt(!isReady || loading, loading)}
        onClick={handleSubmit}
        disabled={!isReady || loading}
      >
        {loading ? (
          <><span style={spinnerSt} /><span>{loadingLabel}</span></>
        ) : (
          <><span>🚀</span><span>تحليل البيانات وتوليد التوصيات</span></>
        )}
      </button>
    </div>
  )
}

/* ── Styles ────────────────────────────────────────── */
const tabBarSt = {
  display: 'flex', gap: '6px', padding: '4px',
  background: 'var(--bg-base)', border: '1px solid var(--border)',
  borderRadius: 'var(--r-md)',
}
const tabSt = active => ({
  flex: 1, padding: '9px 14px', borderRadius: '8px',
  fontSize: '0.86rem', fontWeight: 600, fontFamily: 'var(--font-ar)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
  background: active ? 'linear-gradient(135deg, var(--accent), var(--accent-2))' : 'transparent',
  color: active ? '#fff' : 'var(--text-secondary)',
  boxShadow: active ? '0 2px 12px var(--accent-glow)' : 'none',
  transition: 'all 0.2s',
})
const dropzoneSt = (drag, hasFile) => ({
  border: `2px dashed ${drag ? 'var(--accent)' : hasFile ? 'var(--success)' : 'var(--border-bright)'}`,
  borderRadius: 'var(--r-lg)', padding: '2rem 1.5rem',
  textAlign: 'center', cursor: 'pointer',
  background: drag ? 'rgba(56,189,248,0.05)' : hasFile ? 'rgba(52,211,153,0.03)' : 'transparent',
  transition: 'all 0.25s', flex: 1,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
})
const fmtBadgeSt = {
  background: 'rgba(56,189,248,0.07)', border: '1px solid var(--border)',
  borderRadius: '4px', padding: '2px 7px',
  fontSize: '0.72rem', color: 'var(--text-muted)',
  fontFamily: 'var(--font-mono)',
}
const labelSt = { fontSize: '0.78rem', color: 'var(--text-secondary)', fontWeight: 600 }
const urlInputSt = {
  width: '100%', background: 'var(--bg-base)',
  border: '1px solid var(--border)', borderRadius: 'var(--r-md)',
  padding: '11px 14px', fontSize: '0.86rem',
  color: 'var(--text-primary)', direction: 'ltr', transition: 'border-color 0.2s',
}
const optInputSt = {
  width: '100%', background: 'var(--bg-base)',
  border: '1px solid var(--border)', borderRadius: 'var(--r-sm)',
  padding: '10px 12px', fontSize: '0.86rem',
  color: 'var(--text-primary)', transition: 'border-color 0.2s',
}
const errorBoxSt = {
  padding: '10px 14px',
  background: 'rgba(248,113,113,0.07)',
  border: '1px solid rgba(248,113,113,0.25)',
  borderRadius: 'var(--r-sm)',
  color: 'var(--danger)', fontSize: '0.86rem',
  whiteSpace: 'pre-line',
}
const submitBtnSt = (disabled, loading) => ({
  width: '100%', padding: '13px',
  borderRadius: 'var(--r-md)', fontSize: '0.95rem',
  fontWeight: 700, fontFamily: 'var(--font-ar)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
  background: disabled ? 'var(--bg-base)' : 'linear-gradient(135deg, var(--accent), var(--accent-2))',
  color: disabled ? 'var(--text-muted)' : '#fff',
  boxShadow: disabled ? 'none' : '0 4px 20px var(--accent-glow)',
  cursor: disabled ? 'not-allowed' : 'pointer',
  border: disabled ? '1px solid var(--border)' : 'none',
  opacity: loading ? 0.85 : 1, marginTop: 'auto',
})
const spinnerSt = {
  display: 'inline-block', width: '15px', height: '15px',
  border: '2px solid rgba(255,255,255,0.3)',
  borderTop: '2px solid #fff',
  borderRadius: '50%', animation: 'spin 0.8s linear infinite',
}
