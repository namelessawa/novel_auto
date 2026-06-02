import React, { useState, useEffect } from 'react'
import {
  advanceChapter,
  rollback,
  resetPipeline,
  takeSnapshot,
  fetchSnapshots,
  fetchStats,
  fetchLLMConfig,
  updateLLMConfig,
  fetchNovels,
  createNovel,
  switchNovel,
  updateNovelTitle,
  deleteNovel,
} from '../services/api'

export default function ControlPanel({ onAction, refreshKey }) {
  const [stats, setStats] = useState(null)
  const [snapshots, setSnapshots] = useState([])
  const [rollbackChapter, setRollbackChapter] = useState('')
  const [message, setMessage] = useState('')

  // LLM config state
  const [llmConfig, setLlmConfig] = useState(null)
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [baseUrlInput, setBaseUrlInput] = useState('')
  const [modelInput, setModelInput] = useState('')
  const [configSaving, setConfigSaving] = useState(false)

  // Novel management state
  const [novels, setNovels] = useState([])
  const [activeNovelId, setActiveNovelId] = useState(null)
  const [editingTitleId, setEditingTitleId] = useState(null)
  const [editingTitleValue, setEditingTitleValue] = useState('')
  const [novelSwitching, setNovelSwitching] = useState(false)

  useEffect(() => {
    loadData()
    loadLLMConfig()
    loadNovels()
  }, [refreshKey])

  const loadData = async () => {
    try {
      const [s, snap] = await Promise.all([fetchStats(), fetchSnapshots()])
      setStats(s)
      setSnapshots(snap.snapshots || [])
    } catch (err) {
      console.error(err)
    }
  }

  const loadLLMConfig = async () => {
    try {
      const cfg = await fetchLLMConfig()
      setLlmConfig(cfg)
      setBaseUrlInput(cfg.base_url || '')
      setModelInput(cfg.model || '')
      setApiKeyInput('')
    } catch (err) {
      console.error('Failed to load LLM config:', err)
    }
  }

  const loadNovels = async () => {
    try {
      const data = await fetchNovels()
      setNovels(data.novels || [])
      setActiveNovelId(data.active_id)
    } catch (err) {
      console.error('Failed to load novels:', err)
    }
  }

  const handleSaveConfig = async () => {
    setConfigSaving(true)
    try {
      const updates = {}
      if (apiKeyInput) updates.api_key = apiKeyInput
      if (baseUrlInput !== (llmConfig?.base_url || '')) updates.base_url = baseUrlInput
      if (modelInput !== (llmConfig?.model || '')) updates.model = modelInput
      if (Object.keys(updates).length === 0) {
        showMessage('没有需要更新的配置')
        setConfigSaving(false)
        return
      }
      const result = await updateLLMConfig(updates)
      setLlmConfig(result)
      setApiKeyInput('')
      showMessage('LLM 配置已更新（Pipeline 已重置以应用新配置）')
    } catch (err) {
      showMessage('配置更新失败: ' + (err.message || '未知错误'))
    } finally {
      setConfigSaving(false)
    }
  }

  const showMessage = (msg) => {
    setMessage(msg)
    setTimeout(() => setMessage(''), 3000)
  }

  const handleAdvanceChapter = async () => {
    await advanceChapter()
    showMessage('已进入下一章')
    loadData()
    onAction?.()
  }

  const handleSnapshot = async () => {
    const result = await takeSnapshot()
    showMessage(`快照已保存: ${result.snapshot_id}`)
    loadData()
  }

  const handleRollback = async () => {
    if (!rollbackChapter) return
    try {
      const result = await rollback(parseInt(rollbackChapter))
      showMessage(result.message)
      setRollbackChapter('')
      loadData()
      onAction?.()
    } catch (err) {
      showMessage('回滚失败: ' + (err.message || '未知错误'))
    }
  }

  const handleReset = async () => {
    if (!window.confirm('确定要重置整个Pipeline吗？所有生成内容将丢失。')) return
    await resetPipeline()
    showMessage('Pipeline 已重置')
    loadData()
    onAction?.()
  }

  // -- Novel handlers --

  const handleCreateNovel = async () => {
    try {
      const novel = await createNovel()
      await loadNovels()
      // Switch to the new novel
      await handleSwitchNovel(novel.id)
      showMessage(`新小说已创建: ${novel.title}`)
    } catch (err) {
      showMessage('创建失败: ' + (err.message || '未知错误'))
    }
  }

  const handleSwitchNovel = async (novelId) => {
    if (novelId === activeNovelId || novelSwitching) return
    setNovelSwitching(true)
    try {
      await switchNovel(novelId)
      setActiveNovelId(novelId)
      showMessage('已切换小说')
      await loadData()
      onAction?.()
    } catch (err) {
      showMessage('切换失败: ' + (err.message || '未知错误'))
    } finally {
      setNovelSwitching(false)
    }
  }

  const handleStartEditTitle = (novel) => {
    setEditingTitleId(novel.id)
    setEditingTitleValue(novel.title)
  }

  const handleSaveTitle = async () => {
    if (!editingTitleId || !editingTitleValue.trim()) return
    try {
      await updateNovelTitle(editingTitleId, editingTitleValue.trim())
      setEditingTitleId(null)
      await loadNovels()
      showMessage('标题已更新')
    } catch (err) {
      showMessage('更新失败: ' + (err.message || '未知错误'))
    }
  }

  const handleDeleteNovel = async (novelId) => {
    if (novelId === activeNovelId) {
      showMessage('不能删除当前活跃的小说')
      return
    }
    if (!window.confirm('确定要删除这部小说吗？所有数据将被永久删除。')) return
    try {
      await deleteNovel(novelId)
      await loadNovels()
      showMessage('小说已删除')
    } catch (err) {
      showMessage('删除失败: ' + (err.message || '未知错误'))
    }
  }

  return (
    <div>
      {message && (
        <div className="card" style={{
          background: 'var(--accent)',
          color: 'white',
          textAlign: 'center',
          padding: 12,
        }}>
          {message}
        </div>
      )}

      {/* Novel Switcher */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div className="card-title" style={{ margin: 0 }}>小说项目</div>
          <button className="btn btn-primary" onClick={handleCreateNovel} style={{ fontSize: 13 }}>
            + 新建小说
          </button>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {novels.map((novel) => (
            <div
              key={novel.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 12px',
                borderRadius: 6,
                border: novel.id === activeNovelId
                  ? '2px solid var(--accent)'
                  : '1px solid var(--border)',
                background: novel.id === activeNovelId
                  ? 'rgba(99, 102, 241, 0.08)'
                  : 'var(--bg-primary)',
                cursor: novel.id === activeNovelId ? 'default' : 'pointer',
                opacity: novelSwitching ? 0.6 : 1,
                transition: 'all 0.15s ease',
              }}
              onClick={() => handleSwitchNovel(novel.id)}
            >
              <div style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: novel.id === activeNovelId ? 'var(--accent)' : 'transparent',
                border: novel.id === activeNovelId ? 'none' : '1px solid var(--text-muted)',
                flexShrink: 0,
              }} />

              {editingTitleId === novel.id ? (
                <input
                  type="text"
                  value={editingTitleValue}
                  onChange={(e) => setEditingTitleValue(e.target.value)}
                  onBlur={handleSaveTitle}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSaveTitle()
                    if (e.key === 'Escape') setEditingTitleId(null)
                  }}
                  autoFocus
                  onClick={(e) => e.stopPropagation()}
                  style={{
                    flex: 1,
                    padding: '2px 6px',
                    fontSize: 14,
                    border: '1px solid var(--accent)',
                    borderRadius: 4,
                    background: 'var(--bg-secondary)',
                    color: 'var(--text-primary)',
                  }}
                />
              ) : (
                <span
                  style={{
                    flex: 1,
                    fontSize: 14,
                    fontWeight: novel.id === activeNovelId ? 600 : 400,
                    color: novel.id === activeNovelId ? 'var(--text-primary)' : 'var(--text-secondary)',
                  }}
                  onDoubleClick={(e) => {
                    e.stopPropagation()
                    handleStartEditTitle(novel)
                  }}
                  title="双击编辑标题"
                >
                  {novel.title}
                </span>
              )}

              <span style={{
                fontSize: 11,
                color: 'var(--text-muted)',
                flexShrink: 0,
              }}>
                {novel.created_at?.slice(0, 10)}
              </span>

              {novel.id !== activeNovelId && (
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    handleDeleteNovel(novel.id)
                  }}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--error)',
                    cursor: 'pointer',
                    fontSize: 14,
                    padding: '0 4px',
                    flexShrink: 0,
                    opacity: 0.6,
                  }}
                  title="删除小说"
                >
                  ×
                </button>
              )}
            </div>
          ))}
          {novels.length === 0 && (
            <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
              暂无小说项目。
            </p>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="card">
        <div className="card-title">系统状态</div>
        {stats ? (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
            gap: 12,
          }}>
            {[
              ['当前章节', `第${stats.current_chapter}章 第${stats.current_section}节`],
              ['总节数', stats.total_sections],
              ['总字数', stats.total_words?.toLocaleString()],
              ['实体数量', stats.entity_count],
              ['向量条目', stats.vector_count],
              ['摘要叶节点', stats.summary_leaf_count],
            ].map(([label, value]) => (
              <div key={label} style={{
                padding: 12,
                background: 'var(--bg-primary)',
                borderRadius: 6,
                border: '1px solid var(--border)',
              }}>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>
                  {label}
                </div>
                <div style={{ fontSize: 18, fontWeight: 600 }}>{value}</div>
              </div>
            ))}
          </div>
        ) : (
          <p style={{ color: 'var(--text-muted)' }}>加载中…</p>
        )}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 16 }}>
        <div className="card" style={{ flex: 1 }}>
          <div className="card-title">章节管理</div>
          <div className="btn-group" style={{ marginBottom: 12 }}>
            <button className="btn btn-primary" onClick={handleAdvanceChapter}>
              进入下一章
            </button>
            <button className="btn btn-secondary" onClick={handleSnapshot}>
              保存快照
            </button>
          </div>

          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8 }}>
              状态回滚
            </div>
            <div className="form-row">
              <input
                type="text"
                placeholder="回滚到第几章"
                value={rollbackChapter}
                onChange={(e) => setRollbackChapter(e.target.value)}
              />
              <button className="btn btn-secondary" onClick={handleRollback}>
                回滚
              </button>
            </div>
          </div>
        </div>

        <div className="card" style={{ flex: 1 }}>
          <div className="card-title">快照历史</div>
          {snapshots.length > 0 ? (
            <div style={{ maxHeight: 200, overflowY: 'auto' }}>
              {snapshots.map((s, i) => (
                <div
                  key={i}
                  style={{
                    padding: '6px 0',
                    borderBottom: '1px solid var(--border)',
                    fontSize: 13,
                    color: 'var(--text-secondary)',
                    fontFamily: 'monospace',
                  }}
                >
                  {s}
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
              无快照记录。
            </p>
          )}
        </div>
      </div>

      {/* LLM Config */}
      <div className="card">
        <div className="card-title">API 配置</div>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>
          留空则使用 config.json 中的默认配置。
          {llmConfig?.has_api_key && (
            <span style={{ marginLeft: 8, color: 'var(--accent)' }}>
              当前 Key: {llmConfig.api_key_masked}
            </span>
          )}
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
              API Key
            </label>
            <input
              type="password"
              placeholder="输入新的 API Key（留空保持不变）"
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
              style={{ width: '100%' }}
            />
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Base URL
              </label>
              <input
                type="text"
                placeholder="https://api.deepseek.com"
                value={baseUrlInput}
                onChange={(e) => setBaseUrlInput(e.target.value)}
                style={{ width: '100%' }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Model
              </label>
              <input
                type="text"
                placeholder="deepseek-chat"
                value={modelInput}
                onChange={(e) => setModelInput(e.target.value)}
                style={{ width: '100%' }}
              />
            </div>
          </div>
          <button
            className="btn btn-primary"
            onClick={handleSaveConfig}
            disabled={configSaving}
            style={{ alignSelf: 'flex-start' }}
          >
            {configSaving ? '保存中…' : '保存配置'}
          </button>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="card" style={{ borderColor: 'var(--error)' }}>
        <div className="card-title" style={{ color: 'var(--error)' }}>
          危险操作
        </div>
        <button className="btn btn-danger" onClick={handleReset}>
          重置 Pipeline
        </button>
        <span style={{ marginLeft: 12, fontSize: 13, color: 'var(--text-muted)' }}>
          清空所有已生成内容、知识图谱和记忆状态
        </span>
      </div>
    </div>
  )
}
