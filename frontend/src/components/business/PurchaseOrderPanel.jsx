/**
 * components/business/PurchaseOrderPanel.jsx
 * ──────────────────────────────────────────────
 * Auto Purchase Order Generator.
 *
 * Builds a filtered list of line items straight from the in-memory
 * `recommendations` (works identically for a real job AND for Demo
 * Mode data — no job_id required) and POSTs it to the backend, which
 * returns a ready-to-send PDF (reporting/purchase_order.py). The
 * request only needs the FastAPI server reachable, not Chronos/Celery,
 * since PDF rendering is pure CPU work independent of the forecasting
 * pipeline.
 */

import React, { useMemo, useState } from 'react'
import { card, cardTitle, fmt, API, authHeaders } from './shared'

export default function PurchaseOrderPanel({ recommendations = [] }) {
  const supplierOptions = useMemo(() => {
    const names = recommendations.map(r => r.supplier).filter(Boolean)
    return Array.from(new Set(names))
  }, [recommendations])

  const [supplier, setSupplier]       = useState('الكل')
  const [customSupplier, setCustomSupplier] = useState('')
  const [onlyAtRisk, setOnlyAtRisk]   = useState(false)
  const [topN, setTopN]               = useState(20)
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState('')
  const [lastPoNumber, setLastPoNumber] = useState('')

  async function handleGenerate() {
    setLoading(true)
    setError('')
    try {
      let rows = recommendations
      if (supplier !== 'الكل') rows = rows.filter(r => r.supplier === supplier)
      if (onlyAtRisk) rows = rows.filter(r => r.seasonal_warning || (r.cv ?? 0) > 0.7)

      rows = [...rows].sort((a, b) => (b.recommended_stock ?? 0) - (a.recommended_stock ?? 0))
      if (topN) rows = rows.slice(0, topN)

      if (rows.length === 0) {
        setError('لا توجد أصناف مطابقة لهذه الفلاتر.')
        setLoading(false)
        return
      }

      const items = rows.map(r => ({
        item:       String(r.item),
        quantity:   Math.max(1, Math.round(r.recommended_stock ?? 1)),
        unit_price: r.unit_price ?? null,
        store:      r.store != null ? String(r.store) : null,
      }))

      const supplierName = supplier !== 'الكل' ? supplier : (customSupplier.trim() || 'Primary Supplier')

      const res = await fetch(`${API}/api/purchase-order`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items,
          supplier_name: supplierName,
          notes: 'This purchase order was generated automatically based on AI inventory recommendations. Please review before sending to the supplier.',
        }),
      })

      if (!res.ok) {
        let detail = `HTTP ${res.status}`
        try { detail = (await res.json()).detail || detail } catch { /* ignore */ }
        throw new Error(detail)
      }

      const disposition = res.headers.get('Content-Disposition') || ''
      const match = disposition.match(/filename="?([^"]+)"?/)
      const filename = match ? match[1] : `purchase_order_${new Date().toISOString().slice(0, 10)}.pdf`

      const blob = await res.blob()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href = url; a.download = filename
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(url)
      setLastPoNumber(filename.replace('.pdf', ''))
    } catch (err) {
      setError('تعذّر إنشاء أمر الشراء — تأكد من أن الخادم الخلفي (Backend) يعمل. ' + (err?.message || ''))
    } finally {
      setLoading(false)
    }
  }

  const selectStyle = {
    padding: '7px 10px', borderRadius: 'var(--r-sm)', border: '1px solid var(--border)',
    background: 'var(--bg-panel)', color: 'var(--text-primary)', fontSize: '0.82rem',
  }

  return (
    <div style={card}>
      <p style={cardTitle}>🧾 Auto Purchase Order Generator — إصدار أمر شراء تلقائي (PDF)</p>
      <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
        يحوّل النظام التوصيات إلى مستند PDF جاهز للإرسال للمورد — بدلاً من عرض الأرقام فقط، النظام يتخذ خطوة فعلية نحو القرار.
      </p>

      <div style={{ display: 'flex', gap: '0.8rem', flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: '1rem' }}>
        <div>
          <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '4px' }}>المورد</label>
          <select style={selectStyle} value={supplier} onChange={e => setSupplier(e.target.value)}>
            <option value="الكل">كل الأصناف (مورد واحد افتراضي)</option>
            {supplierOptions.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        {supplier === 'الكل' && (
          <div>
            <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '4px' }}>اسم المورد على المستند</label>
            <input
              style={selectStyle} placeholder="Primary Supplier"
              value={customSupplier} onChange={e => setCustomSupplier(e.target.value)}
            />
          </div>
        )}

        <div>
          <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '4px' }}>أعلى عدد من الأصناف</label>
          <input
            type="number" min="1" max="200" style={{ ...selectStyle, width: '90px' }}
            value={topN} onChange={e => setTopN(Number(e.target.value) || 1)}
          />
        </div>

        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', color: 'var(--text-secondary)', paddingBottom: '8px', cursor: 'pointer' }}>
          <input type="checkbox" checked={onlyAtRisk} onChange={e => setOnlyAtRisk(e.target.checked)} />
          فقط الأصناف المعرضة للخطر
        </label>

        <button
          onClick={handleGenerate} disabled={loading}
          style={{
            padding: '9px 18px', borderRadius: 'var(--r-md)', border: 'none', cursor: loading ? 'wait' : 'pointer',
            background: 'var(--accent)', color: '#04111d', fontWeight: 700, fontSize: '0.85rem',
            opacity: loading ? 0.7 : 1,
          }}
        >
          {loading ? 'جارٍ الإصدار…' : '🧾 إصدار أمر شراء (PDF)'}
        </button>
      </div>

      {error && (
        <p style={{ fontSize: '0.78rem', color: '#f87171', background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.25)', borderRadius: 'var(--r-md)', padding: '8px 12px' }}>
          {error}
        </p>
      )}
      {!error && lastPoNumber && (
        <p style={{ fontSize: '0.78rem', color: '#34d399' }}>
          ✅ تم إصدار {lastPoNumber} وتحميله بنجاح.
        </p>
      )}
    </div>
  )
}
