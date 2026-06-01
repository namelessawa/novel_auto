import React, { useState, useRef, useEffect } from 'react'
import { generateSectionStream } from '../services/api'

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

export default function GeneratePanel({ onGenerated }) {
  const [outline, setOutline] = useState('')
  const [generating, setGenerating] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [stages, setStages] = useState([])
  const [logs, setLogs] = useState([])
  const textRef = useRef(null)
  const controllerRef = useRef(null)

  useEffect(() => {
    if (textRef.current) {
      textRef.current.scrollTop = textRef.current.scrollHeight
    }
  }, [streamText])

  const handleGenerate = () => {
    setGenerating(true)
    setStreamText('')
    setStages([])
    setLogs([])

    controllerRef.current = generateSectionStream(
      outline,
      (event) => {
        setStages((prev) => {
          const updated = prev.filter((s) => s.stage !== event.stage)
          return [...updated, { stage: event.stage, status: 'active' }]
        })
        setLogs((prev) => [
          ...prev,
          {
            time: new Date().toLocaleTimeString(),
            level: event.stage === 'failed' ? 'error' : 'info',
            message: `[${STAGE_LABELS[event.stage] || event.stage}] ${event.message}`,
          },
        ])
        if (event.stage === 'complete') {
          setStages((prev) =>
            prev.map((s) => ({ ...s, status: 'done' }))
          )
        }
      },
      (text) => {
        setStreamText((prev) => prev + text)
      },
      () => {
        setGenerating(false)
        onGenerated?.()
      }
    )
  }

  const handleStop = () => {
    controllerRef.current?.abort()
    setGenerating(false)
  }

  return (
    <div>
      <div className="card">
        <div className="card-title">全局大纲 / 写作指令</div>
        <textarea
          rows={4}
          placeholder="输入小说大纲或世界观设定… 留空则由系统自动续写"
          value={outline}
          onChange={(e) => setOutline(e.target.value)}
          disabled={generating}
        />
        <div style={{ marginTop: 12 }} className="btn-group">
          <button
            className="btn btn-primary"
            onClick={handleGenerate}
            disabled={generating}
          >
            {generating ? '生成中…' : '生成下一节'}
          </button>
          {generating && (
            <button className="btn btn-danger" onClick={handleStop}>
              停止
            </button>
          )}
        </div>
      </div>

      {stages.length > 0 && (
        <div className="card">
          <div className="card-title">Pipeline 状态</div>
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
        <div className="card">
          <div className="card-title">生成正文</div>
          <div className="generated-text" ref={textRef}>
            {streamText}
          </div>
          <div style={{ marginTop: 8, fontSize: 13, color: 'var(--text-muted)' }}>
            字数: {streamText.length}
          </div>
        </div>
      )}

      {logs.length > 0 && (
        <div className="card">
          <div className="card-title">运行日志</div>
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
  )
}
