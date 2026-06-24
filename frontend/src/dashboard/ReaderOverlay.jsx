import React, { useEffect, useState } from 'react'
import DayNightToggle from './DayNightToggle'
import {
  fetchCharacterStates,
  fetchTickNarratives,
  fetchTickOpenLoops,
  listTickSections,
} from '../services/api'

// v2.47 — 全文阅读 overlay. 左侧节列表 + 右侧正文.

export default function ReaderOverlay({ novel, onClose }) {
  const [sections, setSections] = useState([])
  const [selIdx, setSelIdx] = useState(0)
  const [body, setBody] = useState([])
  // v2.48 — § Arc/OpenLoops 侧栏 (移植 ReaderView 的 Phase 6-C narrative_critic 面板).
  // 这是 reader 唯一回答 "这一节为什么此刻重要" 的视图.
  const [loopsData, setLoopsData] = useState({ loops: [], count: 0, closed_total: 0 })
  const [arcStates, setArcStates] = useState([])
  const [sideLoading, setSideLoading] = useState(false)

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

  // v2.48 — Side panels: loops + arc states. 失败不阻塞阅读, 仅清空.
  useEffect(() => {
    if (!novel?.id) return undefined
    let cancelled = false
    async function load() {
      setSideLoading(true)
      try {
        const [loops, chars] = await Promise.all([
          fetchTickOpenLoops(50),
          fetchCharacterStates(),
        ])
        if (cancelled) return
        setLoopsData({
          loops: loops?.loops || [],
          count: loops?.count ?? 0,
          closed_total: loops?.closed_total ?? 0,
        })
        setArcStates(chars?.states || chars?.character_states || [])
      } catch {
        if (!cancelled) {
          setLoopsData({ loops: [], count: 0, closed_total: 0 })
          setArcStates([])
        }
      } finally {
        if (!cancelled) setSideLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [novel?.id])

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

        {/* v2.48 — § 叙事状态侧栏: 当前角色弧线 + open loops */}
        <aside className="dc-reader-side">
          <ArcSnapshotPanel arcs={arcStates} loading={sideLoading} />
          <OpenLoopsPanel
            loops={loopsData.loops}
            count={loopsData.count}
            closedTotal={loopsData.closed_total}
            loading={sideLoading}
          />
        </aside>
      </div>
    </div>
  )
}

function ArcSnapshotPanel({ arcs, loading }) {
  return (
    <div className="dc-reader-side-card">
      <div className="dc-reader-side-head">
        <span>角色弧线 · ARC</span>
        <span className="dc-reader-side-count">{arcs.length}</span>
      </div>
      <div className="dc-reader-side-body">
        {loading && arcs.length === 0 && (
          <div className="dc-reader-side-empty">加载中…</div>
        )}
        {!loading && arcs.length === 0 && (
          <div className="dc-reader-side-empty">尚无角色弧线</div>
        )}
        {arcs.map((c) => {
          const progress = Math.max(0, Math.min(1, Number(c.arc_progress) || 0))
          const pct = Math.round(progress * 100)
          return (
            <div key={c.character_id || c.name} className="dc-reader-arc-row">
              <div className="dc-reader-arc-head">
                <span className="dc-reader-arc-name">
                  {c.name || c.character_id}
                </span>
                {c.arc_stage && (
                  <span className="dc-reader-arc-stage">{c.arc_stage}</span>
                )}
              </div>
              {c.arc_goal && (
                <div className="dc-reader-arc-goal">目标 · {c.arc_goal}</div>
              )}
              <div className="dc-reader-arc-track">
                <div
                  className="dc-reader-arc-fill"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <div className="dc-reader-arc-meta">
                {pct}%
                {c.arc_stage_entered_tick != null && (
                  <span> · 进入 stage @ t{c.arc_stage_entered_tick}</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function OpenLoopsPanel({ loops, count, closedTotal, loading }) {
  return (
    <div className="dc-reader-side-card">
      <div className="dc-reader-side-head">
        <span>伏笔 · OPEN LOOPS</span>
        <span className="dc-reader-side-count">
          {count} 开 · {closedTotal} 关
        </span>
      </div>
      <div className="dc-reader-side-body">
        {loading && loops.length === 0 && (
          <div className="dc-reader-side-empty">加载中…</div>
        )}
        {!loading && loops.length === 0 && (
          <div className="dc-reader-side-empty">无开放伏笔</div>
        )}
        {loops.map((l) => {
          const u = Number(l.urgency) || 0
          const bucket = u >= 8 ? 'high' : u >= 5 ? 'mid' : 'low'
          return (
            <div
              key={l.id}
              className={`dc-reader-loop-row dc-reader-loop-${bucket}`}
            >
              <div className="dc-reader-loop-head">
                <span className="dc-reader-loop-urg">u{u}</span>
                <span className="dc-reader-loop-type">[{l.type || '?'}]</span>
                <span className="dc-reader-loop-tick">@t{l.opened_tick ?? '?'}</span>
              </div>
              <div className="dc-reader-loop-desc">{l.description}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
