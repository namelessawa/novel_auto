import React, { useEffect, useLayoutEffect, useRef, useState } from 'react'

// v2.47 — Dashboard 左侧栏: 我的小说 + 视图 nav (滑动 indicator) + 后台任务.

export const NAV_ITEMS = [
  { key: 'overview', label: '总览' },
  { key: 'tick',     label: 'Tick 控制' },
  { key: 'agent',    label: 'Agent 上下文' },
  { key: 'chapter',  label: '章节与多模态' },
  { key: 'kg',       label: '知识图谱' },
  { key: 'config',   label: '配置' },
]

export default function Sidebar({
  novels,
  activeNovelId,
  onSwitchNovel,
  onCreateNovel,
  view,
  onView,
  tasks,
}) {
  // 我的小说 list
  const novelCount = (novels || []).length

  // 视图 nav 滑动 indicator
  const navRef = useRef(null)
  const itemRefs = useRef({})
  const [indicator, setIndicator] = useState({ top: 0, height: 0 })

  useLayoutEffect(() => {
    const el = itemRefs.current[view]
    if (el && navRef.current) {
      const parentRect = navRef.current.getBoundingClientRect()
      const rect = el.getBoundingClientRect()
      setIndicator({ top: rect.top - parentRect.top, height: rect.height })
    }
  }, [view, novelCount, (tasks || []).length])

  // window resize 重算
  useEffect(() => {
    function onResize() {
      const el = itemRefs.current[view]
      if (el && navRef.current) {
        const parentRect = navRef.current.getBoundingClientRect()
        const rect = el.getBoundingClientRect()
        setIndicator({ top: rect.top - parentRect.top, height: rect.height })
      }
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [view])

  const runningTasks = (tasks || []).filter(
    (t) => t.status && (t.status === 'running' || t.status === 'pending'),
  )

  return (
    <aside className="dc-sidebar">
      {/* —— 我的小说 —— */}
      <div className="dc-sb-section">
        <div className="dc-sb-head">
          <span className="dc-sb-kicker">我的小说</span>
          <span className="dc-sb-counter">{novelCount}</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {(novels || []).map((n) => (
            <div
              key={n.id}
              className={`dc-sb-novel ${n.id === activeNovelId ? 'is-active' : ''}`}
              onClick={() => onSwitchNovel?.(n.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') onSwitchNovel?.(n.id)
              }}
            >
              <span className="dc-sb-novel-bar" />
              <div className="dc-sb-novel-body">
                <span className="dc-sb-novel-title">{n.title || n.id}</span>
                <span className="dc-sb-novel-meta">
                  {n.id}
                  {typeof n.current_tick === 'number' && ` · ${n.current_tick} tick`}
                </span>
              </div>
            </div>
          ))}
          <button type="button" className="dc-sb-novel-add" onClick={onCreateNovel}>
            <span className="dc-sb-novel-add-plus">+</span>
            <span>新建小说</span>
          </button>
        </div>
      </div>

      {/* —— 视图 —— */}
      <div className="dc-sb-section">
        <span className="dc-sb-kicker" style={{ padding: '0 8px' }}>
          视图
        </span>
        <div className="dc-sb-nav" ref={navRef}>
          <div
            className="dc-sb-nav-indicator"
            style={{ top: indicator.top, height: indicator.height }}
          />
          {NAV_ITEMS.map((item) => {
            const active = view === item.key
            return (
              <button
                key={item.key}
                type="button"
                ref={(el) => {
                  itemRefs.current[item.key] = el
                }}
                className={`dc-sb-nav-item ${active ? 'is-active' : ''}`}
                onClick={() => onView?.(item.key)}
                aria-current={active ? 'page' : undefined}
              >
                <span className="dc-sb-nav-label">{item.label}</span>
                {item.hot && (
                  <span className={`dc-sb-nav-hot ${active ? 'is-accent' : ''}`}>
                    {item.hot}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* —— 后台任务 —— */}
      <div className="dc-sb-section">
        <div className="dc-sb-head">
          <span className="dc-sb-kicker">后台任务</span>
          {runningTasks.length > 0 ? (
            <span className="dc-sb-counter is-running">
              {runningTasks.length} RUNNING
            </span>
          ) : (
            <span className="dc-sb-counter">空闲</span>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {(tasks || []).slice(0, 3).map((t) => {
            const pct = computePct(t)
            return (
              <div key={t.task_id || t.id} className="dc-sb-task" onClick={() => onView?.('tick')}>
                <div className="dc-sb-task-row1">
                  <span className="dc-sb-task-name">
                    <span className="dc-sb-task-caret">›</span>
                    {prettyTaskName(t)}
                  </span>
                  <span className="dc-sb-task-pct">{pct != null ? `${pct}%` : statusBadge(t)}</span>
                </div>
                <div className="dc-sb-task-track">
                  <div
                    className="dc-sb-task-fill"
                    style={{ width: `${pct ?? 0}%` }}
                  />
                </div>
                <div className="dc-sb-task-sub">{prettyTaskSub(t)}</div>
              </div>
            )
          })}
          {(tasks || []).length === 0 && (
            <div
              style={{
                font: "400 11px/1.6 'Inter', sans-serif",
                color: 'var(--text3)',
                padding: '0 4px',
              }}
            >
              尚无任务 — 续写一节会出现在这里
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}

function prettyTaskName(t) {
  return t.label || t.kind || t.name || t.task_id || '后台任务'
}

function prettyTaskSub(t) {
  const stage = t.stage || t.phase || t.status || ''
  const novel = t.novel_id || ''
  if (stage && novel) return `${novel} · ${stage}`
  return stage || novel || '—'
}

function computePct(t) {
  if (typeof t.progress === 'number') return Math.max(0, Math.min(100, Math.round(t.progress * 100)))
  if (typeof t.percent === 'number') return Math.max(0, Math.min(100, Math.round(t.percent)))
  if (typeof t.pct === 'number') return Math.max(0, Math.min(100, Math.round(t.pct)))
  return null
}

function statusBadge(t) {
  if (!t.status) return '—'
  if (t.status === 'completed') return 'DONE'
  if (t.status === 'failed') return 'FAIL'
  if (t.status === 'cancelled') return 'CANC'
  return t.status.toUpperCase()
}
