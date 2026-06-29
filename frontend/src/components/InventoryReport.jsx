import React, { useState } from 'react'

/* ── Inline markdown renderer ────────────────────────── */
function renderInline(text) {
  const parts = []
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g
  let last = 0, m
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    if (m[2]) parts.push(<strong key={m.index} style={{ fontWeight: 700 }}>{m[2]}</strong>)
    else if (m[3]) parts.push(<em key={m.index}>{m[3]}</em>)
    else if (m[4]) parts.push(
      <code key={m.index} style={{
        background: 'rgba(56,189,248,0.1)', padding: '1px 6px',
        borderRadius: '4px', fontSize: '0.85em', fontFamily: 'var(--font-mono)',
        color: 'var(--accent)',
      }}>{m[4]}</code>
    )
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts.length === 1 && typeof parts[0] === 'string' ? parts[0] : parts
}

function MarkdownRenderer({ text }) {
  const lines = text.split('\n')
  const elements = []
  let tableBuffer = []

  function flushTable(key) {
    if (tableBuffer.length < 2) {
      tableBuffer.forEach((l, idx) =>
        elements.push(<p key={`tf-${key}-${idx}`} style={{ margin: '4px 0' }}>{l}</p>)
      )
    } else {
      const rows = tableBuffer.filter(l => !l.match(/^\s*\|[\s:|-]+\|\s*$/))
      const parseRow = line =>
        line.split('|').map(c => c.trim()).filter((_, i, a) => i !== 0 && i !== a.length - 1)
      const header = parseRow(rows[0])
      const body = rows.slice(1)
      elements.push(
        <div key={`tbl-${key}`} style={{ overflowX: 'auto', margin: '1rem 0' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead>
              <tr>
                {header.map((h, hi) => (
                  <th key={hi} style={{
                    padding: '8px 12px', background: 'var(--bg-panel)',
                    border: '1px solid var(--border)', color: 'var(--accent)',
                    fontWeight: 600, textAlign: 'right', whiteSpace: 'nowrap',
                    fontSize: '0.8rem',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((row, ri) => (
                <tr key={ri} style={{ background: ri % 2 === 0 ? 'transparent' : 'rgba(56,189,248,0.02)' }}>
                  {parseRow(row).map((cell, ci) => (
                    <td key={ci} style={{
                      padding: '8px 12px', border: '1px solid var(--border)',
                      color: 'var(--text-primary)', textAlign: 'right',
                    }}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }
    tableBuffer = []
  }

  lines.forEach((line, i) => {
    if (line.trim().startsWith('|')) {
      tableBuffer.push(line)
      if (i === lines.length - 1) flushTable(i)
      return
    }
    if (tableBuffer.length) flushTable(i)

    if (line.startsWith('# '))
      elements.push(<h1 key={i} style={{
        fontSize: '1.3rem', fontWeight: 800, color: 'var(--text-primary)',
        margin: '1.6rem 0 0.6rem', paddingBottom: '0.5rem',
        borderBottom: '1px solid var(--border)',
      }}>{line.slice(2)}</h1>)
    else if (line.startsWith('## '))
      elements.push(<h2 key={i} style={{
        fontSize: '1.1rem', fontWeight: 700, color: 'var(--accent)',
        margin: '1.4rem 0 0.5rem',
      }}>{line.slice(3)}</h2>)
    else if (line.startsWith('### '))
      elements.push(<h3 key={i} style={{
        fontSize: '0.97rem', fontWeight: 700, color: 'var(--accent-2)',
        margin: '1rem 0 0.4rem',
      }}>{line.slice(4)}</h3>)
    else if (line.match(/^---+$/))
      elements.push(<hr key={i} style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '1rem 0' }} />)
    else if (line.match(/^[*-]\s+/)) {
      const content = line.replace(/^[*-]\s+/, '')
      elements.push(
        <div key={i} style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', margin: '4px 0', paddingRight: '4px' }}>
          <span style={{ color: 'var(--accent)', flexShrink: 0, marginTop: '5px', fontSize: '0.6rem' }}>◆</span>
          <span style={{ lineHeight: 1.8 }}>{renderInline(content)}</span>
        </div>
      )
    }
    else if (line.match(/^\d+\.\s+/)) {
      const num = line.match(/^(\d+)\./)[1]
      const content = line.replace(/^\d+\.\s+/, '')
      elements.push(
        <div key={i} style={{ display: 'flex', gap: '10px', alignItems: 'flex-start', margin: '4px 0' }}>
          <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', flexShrink: 0, minWidth: '18px', fontSize: '0.82rem' }}>{num}.</span>
          <span style={{ lineHeight: 1.8 }}>{renderInline(content)}</span>
        </div>
      )
    }
    else if (line.trim() === '')
      elements.push(<div key={i} style={{ height: '0.4rem' }} />)
    else
      elements.push(<p key={i} style={{ margin: '3px 0', lineHeight: 1.9 }}>{renderInline(line)}</p>)
  })

  return <>{elements}</>
}

/* ── Main component ──────────────────────────────────── */
export default function InventoryReport({ report, loading, reportError }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    if (!report) return
    try {
      await navigator.clipboard.writeText(report)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {}
  }

  return (
    <div style={{ animation: 'fadeUp 0.4s ease forwards' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)' }}>
          📝 التقرير العربي التفصيلي
        </h2>
        {report && (
          <button style={{
            display: 'flex', alignItems: 'center', gap: '7px',
            padding: '7px 16px', borderRadius: 'var(--r-sm)',
            background: copied ? 'rgba(52,211,153,0.1)' : 'var(--bg-card)',
            border: `1px solid ${copied ? 'rgba(52,211,153,0.3)' : 'var(--border)'}`,
            color: copied ? 'var(--success)' : 'var(--text-secondary)',
            fontSize: '0.82rem', fontWeight: 600,
          }} onClick={handleCopy}>
            {copied ? '✅ تم النسخ' : '📋 نسخ التقرير'}
          </button>
        )}
      </div>

      {/* Report box */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--r-lg)', overflow: 'hidden',
      }}>
        {/* Banner */}
        <div style={{
          padding: '0.9rem 1.4rem',
          background: 'linear-gradient(135deg, rgba(56,189,248,0.08), rgba(129,140,248,0.05))',
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: '12px',
        }}>
          <span style={{ fontSize: '1.5rem' }}>🤖</span>
          <div>
            <p style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '1px' }}>
              تقرير مولّد بالذكاء الاصطناعي
            </p>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              مخصص لصاحب المتجر · لغة عربية واضحة · مبني على توقعات Chronos T5
            </p>
          </div>
        </div>

        {/* Content */}
        {loading ? (
          <div style={{ padding: '3rem 2rem', textAlign: 'center' }}>
            <div style={{ marginBottom: '2rem' }}>
              {['75%','55%','88%','65%','45%','80%','35%'].map((w, i) => (
                <div key={i} style={{
                  height: '14px', width: w, marginBottom: '10px',
                  background: 'linear-gradient(90deg, var(--bg-panel) 25%, var(--bg-card-hover) 50%, var(--bg-panel) 75%)',
                  backgroundSize: '200% 100%', animation: `shimmer 1.5s infinite`,
                  animationDelay: `${i * 0.08}s`, borderRadius: '4px',
                  marginRight: 'auto',
                }} />
              ))}
            </div>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              ⏳ جارٍ توليد التقرير العربي...
            </p>
          </div>
        ) : reportError ? (
          <div style={{ padding: '3rem 2rem', textAlign: 'center' }}>
            <p style={{ fontSize: '2rem', marginBottom: '0.8rem' }}>⚠️</p>
            <p style={{ color: 'var(--warning)', fontWeight: 600, marginBottom: '0.5rem' }}>
              تعذّر توليد التقرير التلقائي
            </p>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', maxWidth: '400px', margin: '0 auto' }}>
              {reportError}
            </p>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '1rem' }}>
              💡 تحقق من إعداد <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>OPENROUTER_API_KEY</code> أو استخدم Ollama محلياً
            </p>
          </div>
        ) : report ? (
          <div style={{
            padding: '2rem', fontSize: '0.95rem', lineHeight: 2,
            color: 'var(--text-primary)', direction: 'rtl',
            fontFamily: 'var(--font-ar)', overflowX: 'auto',
          }}>
            <MarkdownRenderer text={report} />
          </div>
        ) : (
          <div style={{ padding: '4rem 2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            <p style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>📄</p>
            <p>لا يوجد تقرير بعد</p>
          </div>
        )}
      </div>
    </div>
  )
}
