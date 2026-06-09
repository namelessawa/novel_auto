// v2.24 — 左侧常驻任务列表。
//
// 数据流:
//   - 轮询 GET /api/tasks 每 3s 同步全局任务集 (兜底, 防 SSE 断流)
//   - 对每个 queued/running 任务额外开 SSE /api/tasks/{id}/stream;
//     SSE 推送的 snapshot 替换轮询拿到的, 提供毫秒级进度更新
//   - 任务终态后 SSE 自动关闭 (服务端 yield 完 break), 保留快照展示
//
// 不在此组件做的事:
//   - 创建任务 (POST /api/section/generate) — 由 HomeView 触发
//   - 显示节级正文 — 由 NovelView 通过 listTickSections 渲染

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  cancelTask,
  listTasks,
  watchTaskStream,
} from '../services/api'
import { showToast } from '../utils/toast'

const STATUS_CONFIG = {
  queued: { label: '排队', color: 'var(--text-muted)', icon: 'fa-hourglass' },
  running: { label: '进行中', color: 'var(--accent-cyan)', icon: 'fa-spinner fa-spin' },
  completed: { label: '已完成', color: 'var(--accent-green, #16a34a)', icon: 'fa-check' },
  failed: { label: '失败', color: 'var(--accent-rose)', icon: 'fa-times' },
  cancelled: { label: '已取消', color: 'var(--text-muted)', icon: 'fa-ban' },
}

const KIND_LABEL = {
  section_generation: '续写下一节',
  bootstrap_section: '首节生成',
  bootstrap_world: '世界种子',
}

// 已完成/失败/取消的任务在列表中保留多久 — 够用户切走再回来仍能看到结果,
// 过了就自动隐藏避免列表无限增长 (后端 /api/tasks 仍可查全量)
const TERMINAL_RETAIN_MS = 30 * 60 * 1000

// 列表自动刷新间隔 — SSE 是流式但用户主动失焦/网络抖动可能漏推, 15s 兜底拉一次
const AUTO_REFRESH_MS = 15 * 1000

export default function TaskListPanel({ onTaskComplete }) {
  const [tasks, setTasks] = useState([])
  // 每个 active 任务的 SSE controller, 任务 id → AbortController
  const streamsRef = useRef(new Map())
  const onCompleteRef = useRef(onTaskComplete)
  useEffect(() => {
    onCompleteRef.current = onTaskComplete
  }, [onTaskComplete])

  const updateOne = useCallback((snap) => {
    setTasks((prev) => {
      const idx = prev.findIndex((t) => t.id === snap.id)
      if (idx === -1) return [...prev, snap]
      const next = [...prev]
      next[idx] = snap
      return next
    })
    // 终态触发外部回调 (HomeView/NovelView 刷新节列表)
    if (
      snap.status === 'completed' ||
      snap.status === 'failed' ||
      snap.status === 'cancelled'
    ) {
      const cb = onCompleteRef.current
      if (typeof cb === 'function') cb(snap)
    }
  }, [])

  const subscribeIfNeeded = useCallback(
    (task) => {
      if (streamsRef.current.has(task.id)) return
      if (task.status !== 'queued' && task.status !== 'running') return
      const ctrl = watchTaskStream(task.id, {
        onSnapshot: updateOne,
        onDone: () => {
          streamsRef.current.delete(task.id)
        },
        onError: () => {
          // SSE 失败时静默 — 轮询路径会兜底更新
          streamsRef.current.delete(task.id)
        },
      })
      streamsRef.current.set(task.id, ctrl)
    },
    [updateOne],
  )

  // 提到 useEffect 外 — 顶部 ⟳ 按钮也要触发同一段刷新逻辑
  const cancelledRef = useRef(false)
  const [refreshing, setRefreshing] = useState(false)

  const refreshList = useCallback(async () => {
    setRefreshing(true)
    try {
      const data = await listTasks()
      if (cancelledRef.current) return
      const nowMs = Date.now()
      const filtered = (data.tasks || []).filter((t) => {
        if (t.status === 'queued' || t.status === 'running') return true
        // 终态任务超过保留窗口就隐藏 — 仍可在 /api/tasks 列表里查到
        if (!t.completed_at) return true
        const completed = Date.parse(t.completed_at)
        if (Number.isNaN(completed)) return true
        return nowMs - completed < TERMINAL_RETAIN_MS
      })
      setTasks(filtered)
      filtered.forEach(subscribeIfNeeded)
    } catch {
      /* 后端临时下线 — 保留上一次列表, 不弹 toast */
    } finally {
      if (!cancelledRef.current) setRefreshing(false)
    }
  }, [subscribeIfNeeded])

  // 列表拉取:
  //   1. 挂载时拉一次
  //   2. tab 切回前台时拉一次
  //   3. 15s 兜底自动刷新 (AUTO_REFRESH_MS) — 防 SSE 漏推 / 失败任务被 60s 窗口截走前补一帧
  //   4. 顶部 ⟳ 按钮手动拉一次
  // 进行中任务的进度变化由各 task SSE 流推送 (subscribeIfNeeded), 兜底轮询不影响实时性.
  useEffect(() => {
    cancelledRef.current = false
    refreshList()
    const onVisible = () => {
      if (document.visibilityState === 'visible') refreshList()
    }
    document.addEventListener('visibilitychange', onVisible)
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') refreshList()
    }, AUTO_REFRESH_MS)
    return () => {
      cancelledRef.current = true
      document.removeEventListener('visibilitychange', onVisible)
      clearInterval(interval)
      // 卸载时关闭所有 SSE
      streamsRef.current.forEach((c) => c.abort())
      streamsRef.current.clear()
    }
  }, [refreshList])

  const handleCancel = useCallback(async (taskId) => {
    try {
      await cancelTask(taskId)
      // 取消成功 — SSE 会推回状态变化, 不需要 toast
    } catch (e) {
      showToast(`取消失败: ${e.message || e}`, 'error')
    }
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <div
        className="sidebar-topics-header"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <span>任务{tasks.length > 0 ? ` · ${tasks.length}` : ''}</span>
        <button
          onClick={refreshList}
          disabled={refreshing}
          title="刷新任务列表"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: refreshing ? 'wait' : 'pointer',
            fontSize: 12,
            padding: '2px 6px',
            opacity: refreshing ? 0.5 : 1,
          }}
        >
          <i className={`fas fa-rotate ${refreshing ? 'fa-spin' : ''}`}></i>
        </button>
      </div>

      {tasks.length === 0 ? (
        <div
          style={{
            padding: '12px',
            fontSize: 12,
            color: 'var(--text-muted)',
            fontStyle: 'italic',
          }}
        >
          暂无后台任务
        </div>
      ) : (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            padding: '4px 8px 8px',
            maxHeight: 280,
            overflowY: 'auto',
          }}
        >
          {tasks.map((t) => (
            <TaskRow key={t.id} task={t} onCancel={handleCancel} />
          ))}
        </div>
      )}
    </div>
  )
}

function TaskRow({ task, onCancel }) {
  const status = STATUS_CONFIG[task.status] || STATUS_CONFIG.queued
  const kindLabel = KIND_LABEL[task.kind] || task.kind
  const progress = task.progress || {}
  // v2.25 — bootstrap_world 没有"字数"概念 (target_words=0), 用 tick_count/max_ticks
  // 当作 4 阶段进度. section_generation / bootstrap_section 仍按字数走.
  const isBootstrapWorld = task.kind === 'bootstrap_world'
  const wordTarget = progress.target_words || 3000
  const wordPct = isBootstrapWorld
    ? Math.min(100, Math.round(((progress.tick_count || 0) / (progress.max_ticks || 4)) * 100))
    : Math.min(100, Math.round(((progress.current_words || 0) / wordTarget) * 100))
  const isActive = task.status === 'queued' || task.status === 'running'

  return (
    <div
      style={{
        padding: '8px 10px',
        background: 'var(--bg-card)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 8,
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        fontSize: 12,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <i
          className={`fas ${status.icon}`}
          style={{ color: status.color, fontSize: 11, width: 12 }}
        ></i>
        <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
          {kindLabel}
        </span>
        {task.chapter && task.section_no && (
          <span style={{ color: 'var(--text-muted)' }}>
            · 第{task.chapter}章 第{task.section_no}节
          </span>
        )}
        {isActive && (
          <button
            onClick={() => onCancel(task.id)}
            title="取消"
            style={{
              marginLeft: 'auto',
              background: 'transparent',
              border: 'none',
              color: 'var(--accent-rose)',
              cursor: 'pointer',
              fontSize: 11,
            }}
          >
            <i className="fas fa-times"></i>
          </button>
        )}
      </div>

      <div
        style={{
          color: 'var(--text-muted)',
          fontSize: 11,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
        title={task.novel_title || task.novel_id}
      >
        《{task.novel_title || task.novel_id}》
      </div>

      {isActive && (
        <>
          <div
            style={{
              height: 4,
              background: 'var(--border-subtle)',
              borderRadius: 2,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${wordPct}%`,
                height: '100%',
                background: status.color,
                transition: 'width 0.3s ease',
              }}
            />
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              color: 'var(--text-muted)',
              fontSize: 11,
            }}
          >
            {isBootstrapWorld ? (
              <span>
                阶段 {progress.tick_count || 0}/{progress.max_ticks || 4}
              </span>
            ) : (
              <>
                <span>
                  {progress.current_words || 0}/{wordTarget} 字
                </span>
                <span>
                  tick {progress.tick_count || 0}/{progress.max_ticks || 30}
                </span>
              </>
            )}
          </div>
        </>
      )}

      {task.status === 'completed' && (
        <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>
          {task.result_title && `《${task.result_title}》· `}
          {task.result_word_count || progress.current_words || 0} 字
        </div>
      )}

      {task.status === 'failed' && (
        <div
          style={{
            color: 'var(--accent-rose)',
            fontSize: 11,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
          title={task.error}
        >
          {task.error || '未知错误'}
        </div>
      )}

      {progress.last_message && isActive && (
        <div
          style={{
            color: 'var(--text-muted)',
            fontSize: 11,
            fontStyle: 'italic',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={progress.last_message}
        >
          {progress.last_message}
        </div>
      )}
    </div>
  )
}
