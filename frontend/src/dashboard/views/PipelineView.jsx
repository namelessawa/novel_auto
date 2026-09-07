import React, { useCallback, useEffect, useState } from 'react'
import {
  fetchPipelineSynopses,
  fetchPipelineSchema,
  fetchPipelineForeshadows,
  fetchPipelineForeshadowState,
  fetchPipelineCurrentStatus,
  fetchPipelineStatus,
  updatePipelineSynopsis,
  updatePipelineSchema,
  confirmPipelineChapter,
  generatePipelineChapter,
  fetchPipelineChromaStatus,
} from '../../services/api'
import AsyncState from '../components/AsyncState'
import { showToast } from '../../utils/toast'

const PHASE_LABELS = {
  awaiting_user_confirmation: '等待确认',
  confirmed: '已确认',
  preparing_context: '准备上下文',
  writing: '正文生成',
  extracting_foreshadows: '伏笔提取',
  extracting_information: '信息提取',
  integrating_memory: '记忆整合',
  committing: '提交章节',
  chapter_completed: '已完成',
  failed: '失败',
}

const FORESHADOW_MODES = [
  { value: 'random', label: '自动随机' },
  { value: 'fixed', label: '固定数量' },
]

export default function PipelineView({ novelId }) {
  const [synopses, setSynopses] = useState([])
  const [schema, setSchema] = useState(null)
  const [foreshadows, setForeshadows] = useState([])
  const [foreshadowState, setForeshadowState] = useState(null)
  const [currentChapter, setCurrentChapter] = useState(1)
  const [pipelineStatus, setPipelineStatus] = useState(null)
  const [chromaStatus, setChromaStatus] = useState(null)

  const [editingSynopsis, setEditingSynopsis] = useState(null)
  const [editingSchema, setEditingSchema] = useState(null)

  const [foreshadowMode, setForeshadowMode] = useState('random')
  const [foreshadowCount, setForeshadowCount] = useState(0)
  const [confirming, setConfirming] = useState(false)

  const loadData = useCallback(async () => {
    if (!novelId) return
    try {
      const [syn, sch, fs, fsState, status] = await Promise.all([
        fetchPipelineSynopses(novelId),
        fetchPipelineSchema(novelId),
        fetchPipelineForeshadows(novelId),
        fetchPipelineForeshadowState(novelId),
        fetchPipelineCurrentStatus(novelId),
      ])
      setSynopses(syn || [])
      setSchema(sch)
      setForeshadows(fs || [])
      setForeshadowState(fsState)
      setCurrentChapter(status?.current_chapter || 1)

      // Load current chapter status
      if (status?.current_chapter) {
        const chStatus = await fetchPipelineStatus(novelId, status.current_chapter)
        setPipelineStatus(chStatus)
      }

      // Load Chroma status
      try {
        const chroma = await fetchPipelineChromaStatus(novelId)
        setChromaStatus(chroma)
      } catch {
        // Chroma may not be available
      }
    } catch (err) {
      showToast(`加载失败: ${err.message}`, 'error')
    }
  }, [novelId])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleConfirmAndGenerate = async () => {
    if (!novelId) return
    setConfirming(true)
    try {
      await confirmPipelineChapter(novelId, currentChapter, {
        foreshadowMode,
        foreshadowCount: foreshadowMode === 'fixed' ? foreshadowCount : 0,
      })
      showToast(`第 ${currentChapter} 章已确认`, 'success')

      // Start generation
      await generatePipelineChapter(novelId, currentChapter)
      showToast('生成任务已启动', 'success')
      loadData()
    } catch (err) {
      showToast(`确认失败: ${err.message}`, 'error')
    } finally {
      setConfirming(false)
    }
  }

  const handleSynopsisSave = async (chapter, title, synopsis) => {
    try {
      await updatePipelineSynopsis(novelId, chapter, { title, synopsis })
      showToast(`第 ${chapter} 章梗概已保存`, 'success')
      setEditingSynopsis(null)
      loadData()
    } catch (err) {
      showToast(`保存失败: ${err.message}`, 'error')
    }
  }

  const handleSchemaSave = async (fields) => {
    try {
      await updatePipelineSchema(novelId, fields)
      showToast('信息 Schema 已更新', 'success')
      setEditingSchema(null)
      loadData()
    } catch (err) {
      showToast(`保存失败: ${err.message}`, 'error')
    }
  }

  const phase = pipelineStatus?.phase || 'awaiting_user_confirmation'

  return (
    <div className="pipeline-view" style={{ padding: '20px' }}>
      <h2 style={{ marginBottom: '20px' }}>有状态生成管线</h2>

      {/* Current Chapter Status */}
      <section className="panel" style={{ marginBottom: '24px' }}>
        <h3>当前章节</h3>
        <div className="status-bar" style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
          <span style={{ fontSize: '18px', fontWeight: 'bold' }}>
            第 {currentChapter} 章
          </span>
          <span className="badge" style={{
            padding: '4px 12px',
            borderRadius: '12px',
            background: phase === 'chapter_completed' ? '#4caf50' : phase === 'failed' ? '#f44336' : '#2196f3',
            color: 'white',
          }}>
            {PHASE_LABELS[phase] || phase}
          </span>
        </div>

        {/* Pipeline Progress */}
        <div className="pipeline-stages" style={{ marginTop: '12px' }}>
          {Object.entries(PHASE_LABELS).map(([key, label]) => (
            <div
              key={key}
              style={{
                display: 'inline-block',
                padding: '4px 8px',
                margin: '2px',
                borderRadius: '4px',
                fontSize: '12px',
                background: phase === key ? '#2196f3' : '#e0e0e0',
                color: phase === key ? 'white' : '#666',
              }}
            >
              {label}
            </div>
          ))}
        </div>
      </section>

      {/* Confirmation Panel */}
      {phase === 'awaiting_user_confirmation' && (
        <section className="panel" style={{ marginBottom: '24px', padding: '16px', border: '1px solid #ddd' }}>
          <h3>确认并生成第 {currentChapter} 章</h3>

          <div style={{ marginBottom: '12px' }}>
            <label>伏笔收录数量：</label>
            <select
              value={foreshadowMode}
              onChange={(e) => setForeshadowMode(e.target.value)}
              style={{ marginLeft: '8px', padding: '4px' }}
            >
              {FORESHADOW_MODES.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
            {foreshadowMode === 'fixed' && (
              <select
                value={foreshadowCount}
                onChange={(e) => setForeshadowCount(parseInt(e.target.value))}
                style={{ marginLeft: '8px', padding: '4px' }}
              >
                <option value={0}>0</option>
                <option value={1}>1</option>
                <option value={2}>2</option>
              </select>
            )}
          </div>

          <button
            onClick={handleConfirmAndGenerate}
            disabled={confirming}
            style={{
              padding: '8px 24px',
              background: '#4caf50',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: confirming ? 'wait' : 'pointer',
            }}
          >
            {confirming ? '确认中...' : '确认并生成本章'}
          </button>
        </section>
      )}

      {/* Synopsis Editor */}
      <section className="panel" style={{ marginBottom: '24px' }}>
        <h3>章节梗概</h3>
        {synopses.length === 0 ? (
          <p style={{ color: '#666' }}>暂无梗概。创建小说后系统会自动生成第 1、2 章梗概。</p>
        ) : (
          synopses.map((s) => (
            <div key={s.chapter} style={{ marginBottom: '12px', padding: '12px', border: '1px solid #eee' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <strong>第 {s.chapter} 章：{s.title}</strong>
                <button onClick={() => setEditingSynopsis(s.chapter)}>编辑</button>
              </div>
              {editingSynopsis === s.chapter ? (
                <SynopsisEditor
                  synopsis={s}
                  onSave={handleSynopsisSave}
                  onCancel={() => setEditingSynopsis(null)}
                />
              ) : (
                <p style={{ margin: '8px 0', color: '#333' }}>{s.synopsis}</p>
              )}
            </div>
          ))
        )}
      </section>

      {/* Information Schema */}
      <section className="panel" style={{ marginBottom: '24px' }}>
        <h3>信息收集字段</h3>
        {editingSchema !== null ? (
          <SchemaEditor
            fields={editingSchema}
            onSave={handleSchemaSave}
            onCancel={() => setEditingSchema(null)}
          />
        ) : schema ? (
          <div>
            <p style={{ color: '#666', marginBottom: '8px' }}>
              Schema 版本 {schema.revision} ({schema.source === 'auto_generated' ? 'AI 生成' : '用户定义'})
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {schema.fields?.map((f) => (
                <span key={f.key} style={{ padding: '4px 12px', background: '#e3f2fd', borderRadius: '4px' }}>
                  {f.name}
                </span>
              ))}
            </div>
            <button onClick={() => setEditingSchema(schema.fields || [])} style={{ marginTop: '8px' }}>
              编辑字段
            </button>
          </div>
        ) : (
          <p style={{ color: '#666' }}>暂无 Schema。将在首次生成时自动创建。</p>
        )}
      </section>

      {/* Foreshadow Status */}
      <section className="panel" style={{ marginBottom: '24px' }}>
        <h3>伏笔状态</h3>
        {foreshadowState && (
          <div style={{ marginBottom: '12px', color: '#666' }}>
            连续选中：{foreshadowState.consecutive_selection_count} 次
            {foreshadowState.discard_unlocked && ' | 丢弃机制已解锁'}
          </div>
        )}
        {foreshadows.length === 0 ? (
          <p style={{ color: '#666' }}>暂无伏笔</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #ddd' }}>
                <th style={{ textAlign: 'left', padding: '8px' }}>来源章节</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>摘要</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>状态</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>概率</th>
              </tr>
            </thead>
            <tbody>
              {foreshadows.map((f) => (
                <tr key={f.id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: '8px' }}>第 {f.source_chapter} 章</td>
                  <td style={{ padding: '8px', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {f.summary}
                  </td>
                  <td style={{ padding: '8px' }}>
                    <span style={{
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontSize: '12px',
                      background: f.status === 'active' ? '#4caf50' : f.status === 'discarded' ? '#f44336' : '#ff9800',
                      color: 'white',
                    }}>
                      {f.status === 'active' ? '活跃' : f.status === 'discarded' ? '已丢弃' : '已选中'}
                    </span>
                  </td>
                  <td style={{ padding: '8px' }}>
                    {f.selected_once ? '-' : `${(f.probability * 100).toFixed(0)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* ChromaDB Status */}
      {chromaStatus && (
        <section className="panel" style={{ marginBottom: '24px' }}>
          <h3>记忆存储</h3>
          <p style={{ color: '#666' }}>
            ChromaDB 文档数量：{chromaStatus.document_count}
          </p>
        </section>
      )}
    </div>
  )
}

function SynopsisEditor({ synopsis, onSave, onCancel }) {
  const [title, setTitle] = useState(synopsis.title)
  const [content, setContent] = useState(synopsis.synopsis)

  return (
    <div style={{ marginTop: '8px' }}>
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="章节标题"
        style={{ width: '100%', padding: '8px', marginBottom: '8px' }}
      />
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={4}
        style={{ width: '100%', padding: '8px', marginBottom: '8px' }}
      />
      <button onClick={() => onSave(synopsis.chapter, title, content)}>保存</button>
      <button onClick={onCancel} style={{ marginLeft: '8px' }}>取消</button>
    </div>
  )
}

function SchemaEditor({ fields, onSave, onCancel }) {
  const [editFields, setEditFields] = useState(
    fields.map((f) => ({ ...f }))
  )

  const addField = () => {
    setEditFields([...editFields, { key: `field_${editFields.length}`, name: '', description: '' }])
  }

  const removeField = (index) => {
    setEditFields(editFields.filter((_, i) => i !== index))
  }

  const updateField = (index, key, value) => {
    const updated = [...editFields]
    updated[index] = { ...updated[index], [key]: value }
    setEditFields(updated)
  }

  return (
    <div>
      {editFields.map((f, i) => (
        <div key={i} style={{ marginBottom: '8px', padding: '8px', border: '1px solid #eee' }}>
          <input
            type="text"
            value={f.name}
            onChange={(e) => updateField(i, 'name', e.target.value)}
            placeholder="字段名称"
            style={{ width: '150px', marginRight: '8px' }}
          />
          <input
            type="text"
            value={f.description}
            onChange={(e) => updateField(i, 'description', e.target.value)}
            placeholder="描述"
            style={{ width: '300px' }}
          />
          <button onClick={() => removeField(i)} style={{ marginLeft: '8px', color: '#f44336' }}>
            删除
          </button>
        </div>
      ))}
      <button onClick={addField} style={{ marginBottom: '12px' }}>添加字段</button>
      <div>
        <button onClick={() => onSave(editFields)}>保存</button>
        <button onClick={onCancel} style={{ marginLeft: '8px' }}>取消</button>
      </div>
    </div>
  )
}
