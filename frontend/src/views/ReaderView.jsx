import React, { useEffect, useMemo, useState } from 'react'
import {
  fetchTickNarratives,
  fetchTickOpenLoops,
  fetchCharacterStates,
} from '../services/api'

/**
 * Phase 6-B — long-range reader view.
 *
 * Lists every per-tick narrative the orchestrator produced for the active
 * novel, in tick order. Skips ticks with empty narratives (stale-skip /
 * narration value below threshold) since they don't have visible content.
 *
 * Layout:
 * - Left: tick index (clickable list of ticks that have content)
 * - Middle: continuous reader pane showing selected window
 * - Right: side panels — open loops + character arc snapshot
 * - Top controls: refresh + jump-to-tick range
 *
 * What this is NOT:
 * - Not the arc *timeline* view (current snapshot only — historical arc
 *   trail needs snapshot replay, deferred).
 * - Not the multimedia reader (multimodal_routes already exposes per-section
 *   bundles; reader-with-media is a separate flow).
 */
export default function ReaderView({ novel }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [data, setData] = useState({ narratives: [], current_tick: 0, count: 0 })
  const [startTick, setStartTick] = useState(0)
  const [endTick, setEndTick] = useState(0)
  const [selectedTick, setSelectedTick] = useState(null)
  // Phase 6-B right sidebar — current open loops + character arc snapshot.
  const [loopsData, setLoopsData] = useState({ loops: [], count: 0, closed_total: 0 })
  const [arcStates, setArcStates] = useState([])
  const [sideLoading, setSideLoading] = useState(false)

  const loadNarratives = async (overrides = {}) => {
    setLoading(true)
    setError('')
    try {
      const r = await fetchTickNarratives({
        startTick: overrides.startTick ?? startTick,
        endTick: overrides.endTick ?? endTick,
        limit: 500,
      })
      setData(r)
      // Auto-select last tick on first load
      if (r.narratives.length > 0 && selectedTick == null) {
        setSelectedTick(r.narratives[r.narratives.length - 1].tick)
      }
    } catch (e) {
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  const loadSidePanels = async () => {
    setSideLoading(true)
    try {
      const [loops, chars] = await Promise.all([
        fetchTickOpenLoops(50),
        fetchCharacterStates(),
      ])
      setLoopsData({
        loops: loops?.loops ?? [],
        count: loops?.count ?? 0,
        closed_total: loops?.closed_total ?? 0,
      })
      setArcStates(chars?.states ?? [])
    } catch (err) {
      // 侧栏失败不阻塞阅读, 但留观测线索方便定位 (区分"空数据" vs "加载失败")
      console.warn('ReaderView loadSidePanels failed:', err)
      setLoopsData({ loops: [], count: 0, closed_total: 0 })
      setArcStates([])
    } finally {
      setSideLoading(false)
    }
  }

  useEffect(() => {
    loadNarratives()
    loadSidePanels()
    // re-fetch when novel id changes
  }, [novel?.id])

  const selected = useMemo(
    () => data.narratives.find((n) => n.tick === selectedTick) || null,
    [data.narratives, selectedTick],
  )

  const totalChars = useMemo(
    () => data.narratives.reduce((acc, n) => acc + (n.char_count || 0), 0),
    [data.narratives],
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
      <div className="card" style={{ padding: 12 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <strong style={{ fontSize: 16 }}>
            <i className="fas fa-book-open" style={{ marginRight: 6 }}></i>
            连续阅读
          </strong>
          <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
            tick {data.narratives[0]?.tick ?? '-'} – {data.current_tick} ·
            {` ${data.narratives.length} 段, 共 ${totalChars.toLocaleString()} 字`}
            {data.truncated && (
              <span style={{ color: 'var(--accent-rose, #f43f5e)', marginLeft: 8 }}>
                (达到 500 段上限,可调起始 tick 翻页)
              </span>
            )}
          </span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <label className="input-label" style={{ fontSize: 12 }}>起 tick</label>
            <input
              className="input-field"
              type="number"
              min={0}
              value={startTick}
              onChange={(e) => setStartTick(Math.max(0, parseInt(e.target.value || '0', 10)))}
              style={{ width: 80 }}
              disabled={loading}
            />
            <label className="input-label" style={{ fontSize: 12 }}>止 tick</label>
            <input
              className="input-field"
              type="number"
              min={0}
              value={endTick}
              onChange={(e) => setEndTick(Math.max(0, parseInt(e.target.value || '0', 10)))}
              placeholder="0=至今"
              style={{ width: 80 }}
              disabled={loading}
            />
            <button
              type="button"
              className="btn"
              onClick={() => {
                loadNarratives()
                loadSidePanels()
              }}
              disabled={loading}
            >
              {loading ? (
                <><i className="fas fa-spinner fa-spin" style={{ marginRight: 4 }}></i>加载中</>
              ) : (
                <><i className="fas fa-sync" style={{ marginRight: 4 }}></i>刷新</>
              )}
            </button>
          </div>
        </div>
        {error && (
          <div
            role="alert"
            aria-live="assertive"
            style={{ color: 'var(--accent-rose, #f43f5e)', fontSize: 13, marginTop: 8 }}
          >
            {error}
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr 300px', gap: 12, flex: 1, minHeight: 0 }}>
        <div className="card" style={{ padding: 8, overflowY: 'auto' }}>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
            Tick 索引 ({data.narratives.length})
          </div>
          {data.narratives.length === 0 && !loading && (
            <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              (无 narrative — 当前 novel 还没生成内容)
            </div>
          )}
          {data.narratives.map((n) => (
            <button
              key={n.tick}
              type="button"
              onClick={() => setSelectedTick(n.tick)}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                background: n.tick === selectedTick
                  ? 'var(--accent-purple, #8b5cf6)' : 'transparent',
                color: n.tick === selectedTick ? '#fff' : 'inherit',
                border: 'none',
                padding: '4px 8px',
                borderRadius: 4,
                cursor: 'pointer',
                fontSize: 12,
                marginBottom: 2,
              }}
            >
              tick {n.tick} · {n.char_count} 字
            </button>
          ))}
        </div>
        <div className="card" style={{ padding: 16, overflowY: 'auto' }}>
          {selected ? (
            <>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
                tick {selected.tick} · {selected.char_count} 字
              </div>
              <pre
                style={{
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  fontFamily: 'inherit',
                  fontSize: 15,
                  lineHeight: 1.7,
                  margin: 0,
                }}
              >
                {selected.text}
              </pre>
            </>
          ) : (
            <div style={{ color: 'var(--text-muted)', padding: 20, textAlign: 'center' }}>
              {loading ? '加载中…' : '选一个 tick 开始阅读'}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0 }}>
          <ArcSnapshotPanel arcs={arcStates} loading={sideLoading} />
          <OpenLoopsPanel
            loops={loopsData.loops}
            count={loopsData.count}
            closedTotal={loopsData.closed_total}
            loading={sideLoading}
          />
        </div>
      </div>
    </div>
  )
}

function ArcSnapshotPanel({ arcs, loading }) {
  return (
    <div className="card" style={{ padding: 10, overflowY: 'auto', flex: 1, minHeight: 0 }}>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
        <i className="fas fa-route" style={{ marginRight: 4 }}></i>
        角色弧线 (current snapshot · {arcs.length})
      </div>
      {loading && arcs.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>加载中…</div>
      )}
      {!loading && arcs.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>(无角色)</div>
      )}
      {arcs.map((c) => {
        const progress = Math.max(0, Math.min(1, Number(c.arc_progress) || 0))
        return (
          <div
            key={c.character_id || c.name}
            style={{
              marginBottom: 8,
              paddingBottom: 8,
              borderBottom: '1px solid var(--border-soft, rgba(255,255,255,0.06))',
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 600 }}>
              {c.name}
              {c.arc_stage && (
                <span
                  style={{
                    marginLeft: 6,
                    fontSize: 11,
                    fontWeight: 400,
                    padding: '1px 6px',
                    borderRadius: 4,
                    background: 'var(--accent-purple-soft, rgba(139,92,246,0.18))',
                    color: 'var(--accent-purple, #8b5cf6)',
                  }}
                >
                  {c.arc_stage}
                </span>
              )}
            </div>
            {c.arc_goal && (
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                目标:{c.arc_goal}
              </div>
            )}
            <div
              style={{
                marginTop: 4,
                height: 4,
                background: 'var(--border-soft, rgba(255,255,255,0.08))',
                borderRadius: 2,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  width: `${Math.round(progress * 100)}%`,
                  height: '100%',
                  background: 'var(--accent-purple, #8b5cf6)',
                }}
              />
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
              {Math.round(progress * 100)}%
              {c.arc_stage_entered_tick != null && (
                <span style={{ marginLeft: 6 }}>
                  · 进入 stage @ tick {c.arc_stage_entered_tick}
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function OpenLoopsPanel({ loops, count, closedTotal, loading }) {
  const urgencyColor = (u) => {
    if (u >= 8) return 'var(--accent-rose, #f43f5e)'
    if (u >= 5) return 'var(--accent-amber, #f59e0b)'
    return 'var(--text-muted)'
  }
  return (
    <div className="card" style={{ padding: 10, overflowY: 'auto', flex: 1, minHeight: 0 }}>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
        <i className="fas fa-link" style={{ marginRight: 4 }}></i>
        伏笔 · 开 {count} / 累计已关 {closedTotal}
      </div>
      {loading && loops.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>加载中…</div>
      )}
      {!loading && loops.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>(无 open loop)</div>
      )}
      {loops.map((l) => (
        <div
          key={l.id}
          style={{
            marginBottom: 6,
            paddingBottom: 6,
            borderBottom: '1px solid var(--border-soft, rgba(255,255,255,0.06))',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
            <span
              style={{
                fontWeight: 600,
                color: urgencyColor(l.urgency || 0),
                minWidth: 24,
              }}
            >
              u{l.urgency ?? 0}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              [{l.type || '?'}]
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              @{l.opened_tick}
            </span>
          </div>
          <div style={{ fontSize: 12, marginTop: 2, lineHeight: 1.4 }}>
            {l.description}
          </div>
        </div>
      ))}
    </div>
  )
}
