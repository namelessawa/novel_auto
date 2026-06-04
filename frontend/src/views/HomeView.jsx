import React, { useEffect, useRef, useState } from 'react'
import {
  createNovel,
  fetchNovels,
  generateSectionStream,
  switchNovel,
} from '../services/api'
import { showToast } from '../utils/toast'

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

export default function HomeView({ onAfterGenerated, onAfterCreated }) {
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
      // pipe abort errors back as reject
      const ctrl = controllerRef.current
      ctrl.signal.addEventListener('abort', () => reject(new Error('aborted')))
    })

  const handleCreate = async () => {
    const title = createTitle.trim() || '未命名小说'
    setGenerating(true)
    resetStream()
    setStatusText(`正在创建《${title}》…`)

    try {
      const entry = await createNovel(title)
      if (!entry || !entry.id) throw new Error('创建失败:返回无 id')
      await switchNovel(entry.id)
      showToast(`已创建《${title}》,正在生成开篇…`, 'success')
      setStatusText('正在生成开篇章节…')
      await runStream(createOutline)
      showToast('开篇生成完成', 'success')
      setCreateTitle('')
      setCreateOutline('')
      await loadNovels()
      onAfterCreated?.(entry.id)
    } catch (err) {
      if (err.message !== 'aborted') {
        showToast('创建失败:' + err.message, 'error')
      }
    } finally {
      setGenerating(false)
      onAfterGenerated?.()
    }
  }

  const handleContinue = async () => {
    if (!continueId) {
      showToast('请选择要续写的作品', 'error')
      return
    }
    setGenerating(true)
    resetStream()
    setStatusText('正在续写下一节…')

    try {
      await switchNovel(continueId)
      await runStream(continuePrompt)
      showToast('续写完成', 'success')
      setContinuePrompt('')
      onAfterCreated?.(continueId)
    } catch (err) {
      if (err.message !== 'aborted') {
        showToast('续写失败:' + err.message, 'error')
      }
    } finally {
      setGenerating(false)
      onAfterGenerated?.()
    }
  }

  const handleStop = () => {
    controllerRef.current?.abort()
    setGenerating(false)
    setStatusText('')
    showToast('已停止生成', 'info')
  }

  return (
    <div style={{ maxWidth: 880 }}>
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
        <div style={{ marginTop: 20 }}>
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
    </div>
  )
}
