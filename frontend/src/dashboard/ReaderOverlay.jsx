import React, { useEffect, useState } from 'react'
import DayNightToggle from './DayNightToggle'
import { fetchTickNarratives, listTickSections } from '../services/api'

// v2.47 — 全文阅读 overlay. 左侧节列表 + 右侧正文.

export default function ReaderOverlay({ novel, onClose }) {
  const [sections, setSections] = useState([])
  const [selIdx, setSelIdx] = useState(0)
  const [body, setBody] = useState([])

  useEffect(() => {
    if (!novel?.id) return undefined
    let cancelled = false
    async function load() {
      try {
        const r = await listTickSections(novel.id)
        const items = r?.sections || r?.items || []
        if (!cancelled) setSections(items)
      } catch {
        if (!cancelled) setSections([])
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [novel?.id])

  useEffect(() => {
    if (!novel?.id) return undefined
    const sel = sections[selIdx]
    let cancelled = false
    async function load() {
      try {
        const start = sel?.start_tick ?? 0
        const end = sel?.end_tick ?? 0
        const r = await fetchTickNarratives({ startTick: start, endTick: end, limit: 200 })
        if (!cancelled) setBody(r?.narratives || [])
      } catch {
        if (!cancelled) setBody([])
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [selIdx, sections, novel?.id])

  // Esc to close
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const selSec = sections[selIdx]
  const heading =
    selSec?.title ||
    selSec?.heading ||
    (selSec?.section ? `第 ${selSec.section} 节` : novel?.title || '正文')
  const range =
    selSec
      ? `tick ${selSec.start_tick ?? '—'}–${selSec.end_tick ?? '—'}`
      : '—'

  return (
    <div className="dc-root dc-reader">
      <div className="dc-reader-top">
        <span className="dc-reader-kicker">阅读 · READER</span>
        <span className="dc-reader-title">{novel?.title || novel?.id}</span>
        <div className="dc-reader-right">
          <DayNightToggle />
          <button
            type="button"
            onClick={onClose}
            className="dc-modal-close"
            title="关闭 · Esc"
            aria-label="关闭"
          >
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
              <path
                d="M3 3 L12 12 M12 3 L3 12"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>
      </div>

      <div className="dc-reader-body">
        <aside className="dc-reader-aside">
          <span className="dc-reader-aside-kicker">
            章节 · {sections.length} 节
          </span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {sections.map((s, i) => {
              const sec = s.section ?? s.index ?? s.id ?? i + 1
              const isActive = i === selIdx
              return (
                <div
                  key={`${sec}-${i}`}
                  className={`dc-reader-sec-row ${isActive ? 'is-active' : ''}`}
                  onClick={() => setSelIdx(i)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') setSelIdx(i)
                  }}
                >
                  <span className="dc-reader-sec-idx">
                    {String(sec).padStart(2, '0')}
                  </span>
                  <span className="dc-reader-sec-title">
                    {s.title || s.heading || `第 ${sec} 节`}
                  </span>
                </div>
              )
            })}
            {sections.length === 0 && (
              <div
                style={{
                  padding: '12px 14px',
                  font: "400 12px/1.6 'Inter', sans-serif",
                  color: 'var(--text3)',
                }}
              >
                作品尚未切节 — 推进 tick 至切节阈值后会出现.
              </div>
            )}
          </div>
        </aside>

        <div className="dc-reader-main">
          <article className="dc-reader-article">
            <div className="dc-reader-article-head">
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span
                  style={{
                    width: 16,
                    height: 1,
                    background: 'var(--accent)',
                  }}
                />
                <span
                  style={{
                    font: "500 11px/1 'JetBrains Mono', monospace",
                    color: 'var(--accent)',
                    letterSpacing: '0.18em',
                  }}
                >
                  {range}
                </span>
              </div>
              <h1>{heading}</h1>
            </div>
            {body.length === 0 ? (
              <p style={{ color: 'var(--text3)', textIndent: 0 }}>
                该节没有正文 — 推进到该 tick 区间后由 Narrator 写入.
              </p>
            ) : (
              body.map((n) => (
                <p key={n.tick}>{n.text}</p>
              ))
            )}
          </article>
        </div>
      </div>
    </div>
  )
}
