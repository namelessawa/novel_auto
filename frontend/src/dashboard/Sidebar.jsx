import React, { useEffect, useRef, useState } from 'react'

export const NAV_ITEMS = [
  { key: 'production', label: '生产中心', index: '01' },
  { key: 'outline', label: '整书大纲', index: '02' },
  { key: 'chapters', label: '章节', index: '03' },
  { key: 'styles', label: '风格工作室', index: '04' },
  { key: 'bible', label: '创作圣经', index: '05' },
  { key: 'state', label: '当前事实', index: '06' },
  { key: 'memory', label: '故事线与记忆', index: '07' },
  { key: 'provider', label: 'Provider 配置', index: '08' },
  { key: 'export', label: '导出', index: '09' },
  { key: 'lab', label: '实验室', index: '10', experimental: true },
]

export default function Sidebar({
  novels,
  activeNovelId,
  onSwitchNovel,
  onCreateNovel,
  view,
  onView,
  tasks,
  open = false,
  onClose,
}) {
  const novelCount = (novels || []).length
  const navRef = useRef(null)
  const itemRefs = useRef({})
  const [indicator, setIndicator] = useState({ top: 0, height: 0 })

  useEffect(() => {
    function measure() {
      const element = itemRefs.current[view]
      if (!element || !navRef.current) return
      const parentRect = navRef.current.getBoundingClientRect()
      const rect = element.getBoundingClientRect()
      setIndicator({ top: rect.top - parentRect.top, height: rect.height })
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [view, novelCount, (tasks || []).length])

  const runningTasks = (tasks || []).filter((task) =>
    ['running', 'pending', 'queued'].includes(task.status),
  )

  function selectView(key) {
    onView?.(key)
    onClose?.()
  }

  return (
    <aside
      className={`dc-sidebar ${open ? 'is-open' : ''}`}
      aria-label="作品工作区导航"
    >
      <div className="dc-sidebar-mobile-head">
        <span>WORKSPACE</span>
        <button type="button" onClick={onClose} aria-label="关闭导航">×</button>
      </div>

      <section className="dc-sb-section">
        <div className="dc-sb-head">
          <span className="dc-sb-kicker">我的小说</span>
          <span className="dc-sb-counter">{novelCount}</span>
        </div>
        <div className="dc-sb-novels">
          {(novels || []).map((novel) => (
            <button
              type="button"
              key={novel.id}
              className={`dc-sb-novel ${novel.id === activeNovelId ? 'is-active' : ''}`}
              onClick={() => {
                onSwitchNovel?.(novel.id)
                onClose?.()
              }}
            >
              <span className="dc-sb-novel-bar" />
              <span className="dc-sb-novel-body">
                <span className="dc-sb-novel-title">{novel.title || novel.id}</span>
                <span className="dc-sb-novel-meta">
                  {novel.id}
                  {typeof novel.current_tick === 'number' && ` · ${novel.current_tick} tick`}
                </span>
              </span>
            </button>
          ))}
          <button
            type="button"
            className="dc-sb-novel-add"
            onClick={() => {
              onCreateNovel?.()
              onClose?.()
            }}
          >
            <span className="dc-sb-novel-add-plus">+</span>
            <span>新建小说</span>
          </button>
        </div>
      </section>

      <section className="dc-sb-section dc-sb-workspace">
        <span className="dc-sb-nav-group">长篇生产工作区</span>
        <div className="dc-sb-nav" ref={navRef}>
          <div
            className="dc-sb-nav-indicator"
            style={{ top: indicator.top, height: indicator.height }}
          />
          {NAV_ITEMS.map((item) => {
            const active = view === item.key
            return (
              <button
                type="button"
                key={item.key}
                ref={(element) => {
                  itemRefs.current[item.key] = element
                }}
                className={`dc-sb-nav-item ${active ? 'is-active' : ''} ${
                  item.experimental ? 'is-experimental' : ''
                }`}
                onClick={() => selectView(item.key)}
                aria-current={active ? 'page' : undefined}
              >
                <span className="dc-sb-nav-index">{item.index}</span>
                <span className="dc-sb-nav-label">{item.label}</span>
                {item.experimental && <em>OPT-IN</em>}
              </button>
            )
          })}
        </div>
      </section>

      <section className="dc-sb-section dc-sb-tasks">
        <div className="dc-sb-head">
          <span className="dc-sb-kicker">后台任务</span>
          <span className={`dc-sb-counter ${runningTasks.length ? 'is-running' : ''}`}>
            {runningTasks.length ? `${runningTasks.length} LIVE` : '空闲'}
          </span>
        </div>
        <div className="dc-sb-task-list">
          {(tasks || []).slice(0, 3).map((task) => {
            const pct = computePct(task)
            return (
              <button
                type="button"
                key={task.task_id || task.id}
                className="dc-sb-task"
                onClick={() => selectView(
                  task.kind === 'author_section_generation' ? 'production' : 'lab',
                )}
              >
                <span className="dc-sb-task-row1">
                  <span className="dc-sb-task-name">
                    <span className="dc-sb-task-caret">›</span>
                    {prettyTaskName(task)}
                  </span>
                  <span className="dc-sb-task-pct">
                    {pct != null ? `${pct}%` : statusBadge(task)}
                  </span>
                </span>
                <span className="dc-sb-task-track">
                  <span className="dc-sb-task-fill" style={{ width: `${pct ?? 0}%` }} />
                </span>
                <span className="dc-sb-task-sub">{prettyTaskSub(task)}</span>
              </button>
            )
          })}
          {(tasks || []).length === 0 && (
            <p className="dc-sb-empty">尚无后台任务。整书生产启动后会在这里显示。</p>
          )}
        </div>
      </section>
    </aside>
  )
}

function prettyTaskName(task) {
  return task.label || task.kind || task.name || task.task_id || '后台任务'
}

function prettyTaskSub(task) {
  const stage = task.stage || task.phase || task.status || ''
  const novel = task.novel_id || ''
  return [novel, stage].filter(Boolean).join(' · ') || '—'
}

function computePct(task) {
  if (typeof task.progress === 'number') {
    return Math.max(0, Math.min(100, Math.round(task.progress * 100)))
  }
  for (const key of ['percent', 'pct']) {
    if (typeof task[key] === 'number') {
      return Math.max(0, Math.min(100, Math.round(task[key])))
    }
  }
  return null
}

function statusBadge(task) {
  if (!task.status) return '—'
  if (task.status === 'completed') return 'DONE'
  if (task.status === 'failed') return 'FAIL'
  if (task.status === 'cancelled') return 'CANC'
  return String(task.status).toUpperCase()
}
