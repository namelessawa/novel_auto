import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import DayNightToggle from './DayNightToggle'
import { useReaderPrefs } from './useReaderPrefs'
import {
  fetchCharacterStates,
  fetchTickNarratives,
  fetchTickOpenLoops,
  listTickSections,
} from '../services/api'

// v2.47 — 全文阅读 overlay. 左侧节列表 + 右侧正文.
// Phase 6-B (iter#E) — 加 continuous-scroll mode: 全部 tick 串起来作为一本
// 连续小说阅读 (vs 老的 section-by-section 浏览). 切节标题作 inline anchor,
// 左侧 sidebar 仍按 section 列出 — 点击在 continuous 模式下 scroll 到对应
// section, 在 section 模式下切换 selIdx (老行为).

export default function ReaderOverlay({ novel, onClose }) {
  const [sections, setSections] = useState([])
  const [selIdx, setSelIdx] = useState(0)
  const [body, setBody] = useState([])
  // iter#E — 连读 mode: 拉全本 narratives + inline section header 形式渲染.
  // iter#G — 偏好 + scroll 位置走 localStorage, 跨刷新保留.
  const {
    continuousMode,
    setContinuousMode,
    fontSize,
    setFontSize,
    lineHeight,
    setLineHeight,
    restoreScroll,
    saveScroll,
    FONT_SIZE_OPTIONS,
    LINE_HEIGHT_OPTIONS,
  } = useReaderPrefs(novel?.id)
  const [allNarratives, setAllNarratives] = useState([])
  const [continuousLoading, setContinuousLoading] = useState(false)
  const articleRef = useRef(null)
  const mainRef = useRef(null)
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
    if (continuousMode) return undefined  // continuous mode 走另一 effect
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
  }, [selIdx, sections, novel?.id, continuousMode])

  // iter#E — continuous mode: 拉全本 narratives. 一次性 (limit=2000) 足够 ~500
  // tick 连读, 超出 limit 会 truncate 但 UI 还能显示, 用户至少看到尾部之前.
  useEffect(() => {
    if (!novel?.id || !continuousMode) return undefined
    let cancelled = false
    async function load() {
      setContinuousLoading(true)
      try {
        const r = await fetchTickNarratives({ startTick: 0, endTick: 0, limit: 2000 })
        if (!cancelled) setAllNarratives(r?.narratives || [])
      } catch {
        if (!cancelled) setAllNarratives([])
      } finally {
        if (!cancelled) setContinuousLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [novel?.id, continuousMode])

  // iter#E — 合并 sections + narratives 成 inline-marker 时间线.
  // 输出 [{kind: 'section', section, start_tick}, {kind: 'narr', tick, text}, ...]
  // 按 tick 升序, section header 在第一个 narrative ≥ start_tick 之前插入.
  const continuousFeed = useMemo(() => {
    if (!continuousMode) return []
    const narrs = (allNarratives || [])
      .filter((n) => (n.text || '').trim())
      .sort((a, b) => a.tick - b.tick)
    const secs = (sections || []).slice().sort(
      (a, b) => (a.start_tick ?? 0) - (b.start_tick ?? 0),
    )
    const out = []
    let secIdx = 0
    for (const n of narrs) {
      while (
        secIdx < secs.length &&
        (secs[secIdx].start_tick ?? 0) <= n.tick
      ) {
        const s = secs[secIdx]
        out.push({
          kind: 'section',
          section: s.section ?? secIdx + 1,
          start_tick: s.start_tick ?? 0,
          end_tick: s.end_tick ?? 0,
          title: s.title || s.heading || `第 ${s.section ?? secIdx + 1} 节`,
        })
        secIdx++
      }
      out.push({
        kind: 'narr',
        tick: n.tick,
        text: n.text,
        world_time: n.world_time,
        viewpoint_character_id: n.viewpoint_character_id,
      })
    }
    // trailing sections (no narrative yet) — still anchor them
    while (secIdx < secs.length) {
      const s = secs[secIdx]
      out.push({
        kind: 'section',
        section: s.section ?? secIdx + 1,
        start_tick: s.start_tick ?? 0,
        end_tick: s.end_tick ?? 0,
        title: s.title || s.heading || `第 ${s.section ?? secIdx + 1} 节`,
      })
      secIdx++
    }
    return out
  }, [continuousMode, allNarratives, sections])

  const scrollToSection = useCallback(
    (section) => {
      if (!articleRef.current) return
      const anchor = articleRef.current.querySelector(
        `[data-section-anchor="${section}"]`,
      )
      if (anchor) {
        anchor.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    },
    [],
  )

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

  // iter#G — restore scroll on novel mount (after first paint).
  useEffect(() => {
    if (!mainRef.current) return undefined
    // Defer slightly so initial content render finishes before scrolling.
    const id = setTimeout(() => restoreScroll(mainRef.current), 50)
    return () => clearTimeout(id)
  }, [novel?.id, restoreScroll, continuousMode])

  // iter#G — save scroll on user scroll (debounced via rAF).
  useEffect(() => {
    const el = mainRef.current
    if (!el) return undefined
    let ticking = false
    function onScroll() {
      if (ticking) return
      ticking = true
      requestAnimationFrame(() => {
        saveScroll(el.scrollTop)
        ticking = false
      })
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [novel?.id, saveScroll, continuousMode])

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
          {/* iter#E — 阅读模式切换. 节模式 = 当前节正文; 连读模式 = 全书 inline. */}
          <button
            type="button"
            className="dc-btn-ghost"
            onClick={() => setContinuousMode((v) => !v)}
            aria-pressed={continuousMode}
            title={continuousMode ? '切回 节模式' : '切到 连读 (全本)'}
            style={{
              font: "500 11px/1 'JetBrains Mono', monospace",
              padding: '6px 10px',
              background: continuousMode ? 'var(--accent)' : 'transparent',
              color: continuousMode ? 'var(--bg)' : 'var(--text2)',
              borderColor: continuousMode ? 'var(--accent)' : 'var(--border)',
              letterSpacing: '0.06em',
            }}
          >
            {continuousMode ? '连读 ON' : '节模式'}
          </button>
          {/* iter#G — 字体 size selector (16/18/20). Compact 3-chip group. */}
          <ChipGroup
            options={FONT_SIZE_OPTIONS}
            value={fontSize}
            onChange={setFontSize}
            renderLabel={(v) => `${v}px`}
            ariaLabel="字号"
          />
          {/* iter#G — 行距 selector. 3-chip group. */}
          <ChipGroup
            options={LINE_HEIGHT_OPTIONS}
            value={lineHeight}
            onChange={setLineHeight}
            renderLabel={(v) => `×${v}`}
            ariaLabel="行距"
          />
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
              const isActive = !continuousMode && i === selIdx
              return (
                <div
                  key={`${sec}-${i}`}
                  className={`dc-reader-sec-row ${isActive ? 'is-active' : ''}`}
                  onClick={() => {
                    if (continuousMode) {
                      scrollToSection(sec)
                    } else {
                      setSelIdx(i)
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      if (continuousMode) {
                        scrollToSection(sec)
                      } else {
                        setSelIdx(i)
                      }
                    }
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

        <div className="dc-reader-main" ref={mainRef}>
          <article
            className="dc-reader-article"
            ref={articleRef}
            style={{ '--reader-font-size': `${fontSize}px`, '--reader-line-height': lineHeight }}
          >
            {!continuousMode && (
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
            )}
            {continuousMode && (
              <div className="dc-reader-article-head">
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span
                    style={{ width: 16, height: 1, background: 'var(--accent)' }}
                  />
                  <span
                    style={{
                      font: "500 11px/1 'JetBrains Mono', monospace",
                      color: 'var(--accent)',
                      letterSpacing: '0.18em',
                    }}
                  >
                    连读 · {continuousFeed.filter((x) => x.kind === 'narr').length} tick ·{' '}
                    {sections.length} 节
                  </span>
                </div>
                <h1>{novel?.title || novel?.id}</h1>
              </div>
            )}

            {/* iter#E — 节模式 (老): 当前节正文 */}
            {!continuousMode && body.length === 0 && (
              <p style={{ color: 'var(--text3)', textIndent: 0 }}>
                该节没有正文 — 推进到该 tick 区间后由 Narrator 写入.
              </p>
            )}
            {!continuousMode &&
              body.map((n) => <p key={n.tick}>{n.text}</p>)}

            {/* iter#E — 连读模式: inline section headers + tick chip per paragraph */}
            {continuousMode && continuousLoading && (
              <p style={{ color: 'var(--text3)', textIndent: 0 }}>加载全本中…</p>
            )}
            {continuousMode &&
              !continuousLoading &&
              continuousFeed.length === 0 && (
                <p style={{ color: 'var(--text3)', textIndent: 0 }}>
                  尚无任何 narrative — 推进 tick 后由 Narrator 写入.
                </p>
              )}
            {continuousMode &&
              continuousFeed.map((item, idx) => {
                if (item.kind === 'section') {
                  return (
                    <ContinuousSectionMarker
                      key={`sec-${item.section}-${idx}`}
                      section={item.section}
                      title={item.title}
                      startTick={item.start_tick}
                      endTick={item.end_tick}
                    />
                  )
                }
                return (
                  <ContinuousParagraph
                    key={`narr-${item.tick}`}
                    tick={item.tick}
                    text={item.text}
                    viewpoint={item.viewpoint_character_id}
                  />
                )
              })}
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

// iter#G — 紧凑 chip 选择器, font / line-height 共用.
function ChipGroup({ options, value, onChange, renderLabel, ariaLabel }) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      style={{
        display: 'inline-flex',
        gap: 2,
        padding: 2,
        border: '1px solid var(--border)',
        borderRadius: 3,
      }}
    >
      {options.map((opt) => {
        const active = opt === value
        return (
          <button
            key={opt}
            type="button"
            onClick={() => onChange(opt)}
            aria-pressed={active}
            title={`${ariaLabel} ${renderLabel(opt)}`}
            style={{
              font: "500 10px/1 'JetBrains Mono', monospace",
              padding: '4px 7px',
              background: active ? 'var(--accent)' : 'transparent',
              color: active ? 'var(--bg)' : 'var(--text3)',
              border: 'none',
              borderRadius: 2,
              cursor: 'pointer',
              minWidth: 36,
            }}
          >
            {renderLabel(opt)}
          </button>
        )
      })}
    </div>
  )
}

// iter#E — 连读模式下的 inline section header. data-section-anchor 用于 sidebar
// click → scrollIntoView 定位.
function ContinuousSectionMarker({ section, title, startTick, endTick }) {
  return (
    <div
      data-section-anchor={section}
      style={{
        margin: '32px 0 6px',
        paddingTop: 24,
        borderTop: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div
        style={{
          font: "500 11px/1 'JetBrains Mono', monospace",
          color: 'var(--accent)',
          letterSpacing: '0.18em',
        }}
      >
        § {String(section).padStart(2, '0')} · tick {startTick}–{endTick || '…'}
      </div>
      <h2
        style={{
          font: "600 26px/1.3 'Noto Serif SC', serif",
          color: 'var(--text)',
          margin: 0,
          letterSpacing: '-0.005em',
        }}
      >
        {title}
      </h2>
    </div>
  )
}

// iter#E — 连读模式下的段落 + tick chip. chip 默认半透明, hover 时高亮.
// iter#F — 增加 viewpoint chip (角色名 short form) 替代/补充 tick chip.
function ContinuousParagraph({ tick, text, viewpoint }) {
  return (
    <div
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'row',
        gap: 12,
        alignItems: 'flex-start',
      }}
    >
      <div
        style={{
          flex: 'none',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-end',
          gap: 2,
          minWidth: 56,
          marginTop: 12,
          userSelect: 'none',
        }}
      >
        <span
          title={`tick ${tick}`}
          style={{
            font: "500 10px/1.2 'JetBrains Mono', monospace",
            color: 'var(--text3)',
            opacity: 0.6,
            letterSpacing: '0.04em',
          }}
        >
          t{tick}
        </span>
        {viewpoint && (
          <span
            title={`视点角色: ${viewpoint}`}
            style={{
              font: "500 9px/1.2 'JetBrains Mono', monospace",
              color: 'var(--accent)',
              opacity: 0.8,
              letterSpacing: '0.04em',
              padding: '1px 5px',
              border: '1px solid var(--accent)',
              borderRadius: 2,
              textTransform: 'lowercase',
              maxWidth: 56,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {shortenViewpoint(viewpoint)}
          </span>
        )}
      </div>
      <p style={{ margin: 0, flex: 1 }}>{text}</p>
    </div>
  )
}

// "char_su_mo" → "苏默" 不可行 (我们没字典); 取 "char_" 之后部分, 限 6 字符.
function shortenViewpoint(vpid) {
  if (!vpid) return ''
  const stripped = vpid.startsWith('char_') ? vpid.slice(5) : vpid
  return stripped.length > 8 ? stripped.slice(0, 8) : stripped
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
