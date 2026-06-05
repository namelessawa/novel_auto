import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  createNovel,
  createSectionTask,
  fetchNovels,
  fetchTickStatus,
  generateSectionStream,
  switchNovel,
} from '../services/api'
import { showToast } from '../utils/toast'
import TickControlPanel from '../components/TickControlPanel'

// 节级管线 6 个 stage 顺序固定; failed 单列。
const STAGE_LABELS = {
  context_assembly: '组装上下文',
  planning: '意图规划',
  retrieval: '信息检索',
  validation: '逻辑审查',
  generation: '正文生成',
  state_sync: '状态同步',
  complete: '完成',
  failed: '失败',
}

const PIPELINE_ORDER = [
  'context_assembly',
  'planning',
  'retrieval',
  'validation',
  'generation',
  'state_sync',
  'complete',
]

export default function HomeView({ activeNovel, onAfterGenerated, onAfterCreated }) {
  const [novels, setNovels] = useState([])
  const [createTitle, setCreateTitle] = useState('')
  const [createOutline, setCreateOutline] = useState('')
  const [continueId, setContinueId] = useState('')
  const [continuePrompt, setContinuePrompt] = useState('')

  const [generating, setGenerating] = useState(false)
  const [statusText, setStatusText] = useState('')
  const [streamText, setStreamText] = useState('')
  const [stages, setStages] = useState([])
  const [logs, setLogs] = useState([])
  const [mode, setMode] = useState('create')

  // v2.23 — Tick runtime 状态用于 "当前小说生成进度" 展示
  const [tickStatus, setTickStatus] = useState(null)

  const controllerRef = useRef(null)
  const textRef = useRef(null)

  useEffect(() => {
    loadNovels()
  }, [])

  useEffect(() => {
    if (textRef.current) {
      textRef.current.scrollTop = textRef.current.scrollHeight
    }
  }, [streamText])

  const loadTick = useCallback(async () => {
    try {
      const s = await fetchTickStatus()
      setTickStatus(s)
    } catch {
      setTickStatus(null)
    }
  }, [])

  useEffect(() => {
    loadTick()
    const t = setInterval(loadTick, 3000)
    return () => clearInterval(t)
  }, [loadTick])

  // v2.23 — App.jsx 切换活跃小说后, 续写下拉默认就跟着切, 减少误操作。
  useEffect(() => {
    if (activeNovel?.id) {
      setContinueId(activeNovel.id)
    }
  }, [activeNovel?.id])

  const loadNovels = async () => {
    try {
      const data = await fetchNovels()
      setNovels(data.novels || [])
    } catch (err) {
      console.error('load novels failed:', err)
    }
  }

  const resetStream = () => {
    setStreamText('')
    setStages([])
    setLogs([])
  }

  const runStream = (outline) =>
    new Promise((resolve, reject) => {
      controllerRef.current = generateSectionStream(
        outline,
        (event) => {
          setStages((prev) => {
            const cleaned = prev.filter((s) => s.stage !== event.stage)
            const status = event.stage === 'complete' ? 'done' : 'active'
            return [...cleaned, { stage: event.stage, status }]
          })
          setLogs((prev) => [
            ...prev,
            {
              time: new Date().toLocaleTimeString(),
              level: event.stage === 'failed' ? 'error' : 'info',
              message: `[${STAGE_LABELS[event.stage] || event.stage}] ${event.message || ''}`,
            },
          ])
        },
        (text) => setStreamText((prev) => prev + text),
        () => resolve(),
        (err) => reject(err),
      )
      const ctrl = controllerRef.current
      ctrl.signal.addEventListener('abort', () => reject(new Error('aborted')))
    })

  // v2.24 — 创建小说 / 续写下一节都走任务队列, 不再就地 SSE 流。
  // 进度由左侧「任务」面板展示 (TaskListPanel 自己订阅 SSE), HomeView
  // 只负责创建任务 + 切换活跃小说 + toast 反馈。
  const handleCreate = async () => {
    const title = createTitle.trim() || '未命名小说'
    setMode('create')
    setStatusText(`正在创建《${title}》…`)

    try {
      // createNovel 默认 auto_bootstrap=true, 后端自动入队 bootstrap_section
      const entry = await createNovel(title)
      if (!entry || !entry.id) throw new Error('创建失败:返回无 id')
      await switchNovel(entry.id)
      if (entry.bootstrap_task_id) {
        showToast(
          `已创建《${title}》,首节生成已加入任务队列,可在左下「任务」面板查看进度`,
          'success',
        )
      } else {
        showToast(`已创建《${title}》(未自动生成首节)`, 'info')
      }
      setCreateTitle('')
      setCreateOutline('')
      await loadNovels()
      onAfterCreated?.(entry.id)
    } catch (err) {
      showToast('创建失败:' + err.message, 'error')
    } finally {
      setStatusText('')
      onAfterGenerated?.()
    }
  }

  const handleContinue = async () => {
    if (!continueId) {
      showToast('请选择要续写的作品', 'error')
      return
    }
    setMode('continue')
    setStatusText('正在创建续写任务…')

    try {
      await switchNovel(continueId)
      const snap = await createSectionTask(continueId)
      showToast(
        `已为 第${snap.chapter || '?'}章 第${snap.section_no || '?'}节 创建续写任务,可在左下「任务」面板查看进度`,
        'success',
      )
      setContinuePrompt('')
      onAfterCreated?.(continueId)
    } catch (err) {
      // 409 = 同 novel 已有续写任务
      const msg = err.message || String(err)
      if (msg.includes('已有') || msg.includes('409')) {
        showToast('该作品已有续写任务在跑,等它完成再来', 'info')
      } else {
        showToast('续写失败:' + msg, 'error')
      }
    } finally {
      setStatusText('')
      onAfterGenerated?.()
    }
  }

  const handleStop = () => {
    controllerRef.current?.abort()
    setGenerating(false)
    setStatusText('')
    showToast('已停止生成', 'info')
  }

  // v2.23 — 阶段进度: 已完成的 stage 数 / 7
  const stageDoneCount = stages.filter((s) => s.status === 'done').length
  const currentActiveStage = stages.find((s) => s.status === 'active')?.stage
  const progressPct = generating
    ? Math.min(100, Math.round((stageDoneCount / PIPELINE_ORDER.length) * 100))
    : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 1200 }}>
      {/* v2.23 — 当前作品总览 + 进度 */}
      <ActiveNovelOverview
        novel={activeNovel}
        tickStatus={tickStatus}
        generating={generating}
        mode={mode}
        progressPct={progressPct}
        statusText={statusText}
        currentStage={currentActiveStage}
      />

      <div className="grid-2">
        {/* 创建新小说 */}
        <div className="card">
          <div className="card-title">
            <i className="fas fa-plus-circle"></i> 创建新小说
          </div>
          <div style={{ marginBottom: 12 }}>
            <label className="input-label">小说标题</label>
            <input
              type="text"
              className="input-field"
              placeholder="留空将自动生成"
              value={createTitle}
              onChange={(e) => setCreateTitle(e.target.value)}
              disabled={generating}
            />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label className="input-label">主题 / 大纲 (可选)</label>
            <textarea
              className="input-field"
              placeholder="例如:末世修仙、宋代仿古边境与中央的张力 …"
              value={createOutline}
              onChange={(e) => setCreateOutline(e.target.value)}
              disabled={generating}
              style={{ minHeight: 64 }}
            />
          </div>
          <button
            className="btn btn-primary btn-full"
            onClick={handleCreate}
            disabled={generating}
          >
            <i className="fas fa-magic"></i> 开始创作
          </button>
        </div>

        {/* 续写小说 */}
        <div className="card">
          <div className="card-title">
            <i className="fas fa-feather-alt"></i> 续写小说
          </div>
          <div style={{ marginBottom: 12 }}>
            <label className="input-label">选择作品</label>
            <select
              className="input-field"
              value={continueId}
              onChange={(e) => setContinueId(e.target.value)}
              disabled={generating}
            >
              <option value="">选择已有作品…</option>
              {novels.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.title || n.id}
                </option>
              ))}
            </select>
          </div>
          <div className="prompt-drawer">
            <div className="prompt-drawer-title">
              <i className="fas fa-lightbulb"></i> 作者提示词 (可选)
            </div>
            <textarea
              className="input-field"
              placeholder="例如:让主角在这一节获得新能力,并与反派激烈对决 …"
              value={continuePrompt}
              onChange={(e) => setContinuePrompt(e.target.value)}
              disabled={generating}
              style={{ minHeight: 64 }}
            />
            <p className="input-hint">留空则由 AI 自由发挥</p>
          </div>
          <button
            className="btn btn-success btn-full"
            onClick={handleContinue}
            disabled={generating || !continueId}
            style={{ marginTop: 12 }}
          >
            <i className="fas fa-play"></i> 续写下一节
          </button>
        </div>
      </div>

      {(generating || streamText || logs.length > 0) && (
        <div>
          {generating && (
            <div className="generating-indicator">
              <span className="loading-spinner"></span>
              <span>{statusText || '正在生成中…'}</span>
              <button
                className="btn btn-danger btn-sm"
                onClick={handleStop}
                style={{ marginLeft: 'auto' }}
              >
                <i className="fas fa-stop"></i> 停止
              </button>
            </div>
          )}

          {stages.length > 0 && (
            <div className="card" style={{ marginTop: 12 }}>
              <div className="card-title">
                <i className="fas fa-stream"></i> Pipeline 进度
              </div>
              <div className="pipeline-status">
                {Object.keys(STAGE_LABELS).map((key) => {
                  const found = stages.find((s) => s.stage === key)
                  let cls = 'stage-badge'
                  if (found?.status === 'active') cls += ' active'
                  if (found?.status === 'done') cls += ' done'
                  if (key === 'failed' && found) cls += ' error'
                  return (
                    <span key={key} className={cls}>
                      {STAGE_LABELS[key]}
                    </span>
                  )
                })}
              </div>
            </div>
          )}

          {streamText && (
            <div className="card" style={{ marginTop: 12 }}>
              <div className="card-title">
                <i className="fas fa-align-left"></i> 实时正文
                <span
                  className="badge badge-purple"
                  style={{ marginLeft: 8 }}
                >
                  {streamText.length} 字
                </span>
              </div>
              <div className="generated-text" ref={textRef}>
                {streamText}
              </div>
            </div>
          )}

          {logs.length > 0 && (
            <div className="card" style={{ marginTop: 12 }}>
              <div className="card-title">
                <i className="fas fa-terminal"></i> 运行日志
              </div>
              <div className="log-panel">
                {logs.map((log, i) => (
                  <div key={i} className={`log-entry ${log.level}`}>
                    <span style={{ color: 'var(--text-muted)' }}>{log.time}</span>{' '}
                    {log.message}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* v2.23 — Tick 控制台完整迁入。原 工具栏 "Tick 控制台" Tab 已删, 此处是唯一入口。 */}
      <div className="card" style={{ padding: 0 }}>
        <div
          className="card-title"
          style={{
            padding: '20px 24px 0',
            marginBottom: 0,
          }}
        >
          <i className="fas fa-gauge-high"></i> Tick 调度控制台
          <span
            style={{
              marginLeft: 8,
              fontSize: 12,
              color: 'var(--text-muted)',
              fontWeight: 400,
            }}
          >
            手动推进 / 注入事件 / 维护伏笔
          </span>
        </div>
        <div style={{ padding: '16px 24px 24px' }}>
          <TickControlPanel onAction={onAfterGenerated} />
        </div>
      </div>
    </div>
  )
}

function ActiveNovelOverview({
  novel,
  tickStatus,
  generating,
  mode,
  progressPct,
  statusText,
  currentStage,
}) {
  if (!novel) {
    return (
      <div className="card">
        <div className="card-title">
          <i className="fas fa-book"></i> 当前作品
        </div>
        <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          尚未选择作品。在下方"创建新小说"开始,或在左侧"我的作品"切换。
        </div>
      </div>
    )
  }

  const currentTick = tickStatus?.current_tick ?? '—'
  const isPaused = tickStatus?.is_paused
  const openLoops = tickStatus?.open_loop_count ?? '—'
  const charCount = tickStatus?.character_count ?? '—'

  // 当前阶段中文
  const stageLabel = currentStage ? STAGE_LABELS[currentStage] || currentStage : ''

  return (
    <div className="card">
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ flex: 1, minWidth: 240 }}>
          <div
            style={{
              fontSize: 12,
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
              letterSpacing: 1,
              marginBottom: 4,
            }}
          >
            当前作品
          </div>
          <h2
            style={{
              margin: 0,
              fontSize: 20,
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <i
              className="fas fa-book-open"
              style={{ color: 'var(--accent-purple)' }}
            ></i>
            {novel.title || novel.id}
          </h2>
          <div
            style={{
              marginTop: 8,
              display: 'flex',
              gap: 8,
              flexWrap: 'wrap',
            }}
          >
            <span className="badge badge-purple">tick #{currentTick}</span>
            <span
              className="badge"
              style={{
                background: isPaused
                  ? 'rgba(245,158,11,0.15)'
                  : 'rgba(16,185,129,0.15)',
                color: isPaused ? 'var(--accent-amber)' : 'var(--accent-emerald)',
              }}
            >
              {isPaused ? '已暂停' : '运行中'}
            </span>
            <span className="badge badge-emerald">活跃伏笔 {openLoops}</span>
            <span className="badge badge-purple">角色 {charCount}</span>
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 280 }}>
          <div
            style={{
              fontSize: 12,
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
              letterSpacing: 1,
              marginBottom: 4,
            }}
          >
            {mode === 'continue' ? '续写进度' : '生成进度'}
          </div>
          <div
            style={{
              fontSize: 13,
              color: 'var(--text-secondary)',
              marginBottom: 6,
              minHeight: 18,
            }}
          >
            {generating
              ? `${statusText || '生成中…'}${stageLabel ? ` · 当前阶段: ${stageLabel}` : ''}`
              : '空闲 — 在下方开始创作或续写'}
          </div>
          <div
            style={{
              background: 'rgba(255,255,255,0.05)',
              borderRadius: 8,
              height: 10,
              overflow: 'hidden',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div
              style={{
                width: `${progressPct}%`,
                height: '100%',
                background: generating
                  ? 'linear-gradient(90deg, var(--accent-purple), var(--accent-cyan))'
                  : 'transparent',
                transition: 'width 0.3s ease',
              }}
            />
          </div>
          <div
            style={{
              marginTop: 4,
              fontSize: 11,
              color: 'var(--text-muted)',
              textAlign: 'right',
            }}
          >
            {generating ? `${progressPct}% · 6 阶段管线` : '—'}
          </div>
        </div>
      </div>
    </div>
  )
}
