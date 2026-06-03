import React, { useEffect, useMemo, useState } from 'react'
import {
  fetchGraph,
  fetchMemory,
  fetchOutline,
  fetchSections,
  generateSectionStream,
} from '../services/api'
import { showToast } from '../utils/toast'

export default function NovelView({ novel, onAfterGenerated }) {
  const [sections, setSections] = useState([])
  const [memory, setMemory] = useState(null)
  const [outline, setOutline] = useState(null)
  const [graph, setGraph] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)

  const [promptOpen, setPromptOpen] = useState(false)
  const [continuePrompt, setContinuePrompt] = useState('')
  const [generating, setGenerating] = useState(false)

  useEffect(() => {
    setSelected(null)
    loadAll()
  }, [novel?.id])

  const loadAll = async () => {
    setLoading(true)
    try {
      const [sec, mem, out, gph] = await Promise.all([
        fetchSections(),
        fetchMemory().catch(() => null),
        fetchOutline().catch(() => null),
        fetchGraph().catch(() => null),
      ])
      const list = sec.sections || []
      setSections(list)
      setMemory(mem)
      setOutline(out)
      setGraph(gph)
      if (list.length > 0) setSelected(list.length - 1)
    } catch (err) {
      console.error('load novel detail failed:', err)
    }
    setLoading(false)
  }

  const startContinue = () => {
    setContinuePrompt('')
    setPromptOpen(true)
  }

  const submitContinue = async () => {
    setPromptOpen(false)
    setGenerating(true)
    try {
      await new Promise((resolve, reject) => {
        const ctrl = generateSectionStream(
          continuePrompt,
          () => {},
          () => {},
          () => resolve(),
        )
        ctrl.signal.addEventListener('abort', () => reject(new Error('aborted')))
      })
      showToast('续写完成', 'success')
      await loadAll()
      onAfterGenerated?.()
    } catch (err) {
      if (err.message !== 'aborted') {
        showToast('续写失败:' + err.message, 'error')
      }
    } finally {
      setGenerating(false)
    }
  }

  const totalWords = useMemo(
    () => sections.reduce((sum, s) => sum + (s.word_count || 0), 0),
    [sections],
  )

  if (!novel) {
    return (
      <div className="empty-state">
        <i className="fas fa-book"></i>
        <p>从左侧「我的作品」选择一部作品</p>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <h2
          style={{
            margin: 0,
            fontSize: 18,
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
        <span className="badge badge-purple">{sections.length} 节</span>
        <span className="badge badge-emerald">
          {totalWords.toLocaleString()} 字
        </span>
        <button
          className="btn btn-success btn-sm"
          onClick={startContinue}
          disabled={generating}
          style={{ marginLeft: 'auto' }}
        >
          <i className="fas fa-plus"></i>{' '}
          {generating ? '生成中…' : '续写下一节'}
        </button>
      </div>

      <div style={{ display: 'flex', flex: 1, gap: 16, minHeight: 0 }}>
        {/* 左侧:章节列表 */}
        <div
          style={{
            width: 260,
            minWidth: 260,
            display: 'flex',
            flexDirection: 'column',
            background: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 12,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '14px 16px 10px',
              fontSize: 12,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: 1,
              color: 'var(--text-muted)',
              borderBottom: '1px solid var(--border-subtle)',
            }}
          >
            章节列表
          </div>
          <div
            className="chapter-list"
            style={{ padding: 8, overflowY: 'auto', flex: 1 }}
          >
            {loading && (
              <div
                style={{
                  padding: 16,
                  color: 'var(--text-muted)',
                  fontSize: 13,
                }}
              >
                加载中…
              </div>
            )}
            {!loading && sections.length === 0 && (
              <div
                style={{
                  padding: 16,
                  color: 'var(--text-muted)',
                  fontSize: 13,
                }}
              >
                暂无章节
              </div>
            )}
            {sections.map((s, i) => (
              <div
                key={i}
                className={`chapter-item ${selected === i ? 'active' : ''}`}
                onClick={() => setSelected(i)}
              >
                <div className="chapter-num">{i + 1}</div>
                <div className="chapter-info">
                  <div className="chapter-title">
                    {s.title || `第${s.chapter}章 第${s.section}节`}
                  </div>
                  <div className="chapter-preview">
                    {(s.summary || s.content || '').slice(0, 80)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 右侧:阅读 + 记忆面板 */}
        {selected === null ? (
          <div
            className="empty-state"
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <i className="fas fa-book-reader"></i>
            <p
              style={{
                fontSize: 16,
                fontWeight: 500,
                color: 'var(--text-secondary)',
              }}
            >
              选择一个章节开始阅读
            </p>
            <p>点击左侧章节列表查看内容</p>
          </div>
        ) : (
          <div className="reading-container" style={{ flex: 1 }}>
            <div className="reading-main">
              <ReadingContent section={sections[selected]} />
            </div>
            <div className="reading-sidebar">
              <MemoryPanel
                title="角色关系"
                icon="fa-users"
                color="var(--accent-cyan)"
              >
                <RelationshipBlock graph={graph} />
              </MemoryPanel>

              <MemoryPanel
                title="人物与实体"
                icon="fa-user-tag"
                color="var(--accent-amber)"
              >
                <EntitiesBlock graph={graph} />
              </MemoryPanel>

              <MemoryPanel
                title="工作记忆"
                icon="fa-layer-group"
                color="var(--accent-emerald)"
              >
                <WorkingMemoryBlock memory={memory} />
              </MemoryPanel>

              <MemoryPanel
                title="故事摘要"
                icon="fa-align-left"
                color="var(--accent-purple)"
                defaultCollapsed
              >
                <OutlineBlock outline={outline} />
              </MemoryPanel>
            </div>
          </div>
        )}
      </div>

      {promptOpen && (
        <div className="modal-overlay" onClick={() => setPromptOpen(false)}>
          <div
            className="modal-content"
            style={{ width: 500 }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="modal-title" style={{ fontSize: 18 }}>
              续写下一节
            </h2>
            <p className="modal-desc" style={{ marginBottom: 16 }}>
              为 <strong>{novel.title || novel.id}</strong> 生成新的章节
            </p>
            <div style={{ marginBottom: 16 }}>
              <label className="input-label">作者提示词 (可选)</label>
              <textarea
                className="input-field"
                placeholder="留空则由 AI 自由发挥…"
                value={continuePrompt}
                onChange={(e) => setContinuePrompt(e.target.value)}
                style={{ minHeight: 100 }}
              />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className="btn btn-secondary"
                style={{ flex: 1 }}
                onClick={() => setPromptOpen(false)}
              >
                取消
              </button>
              <button
                className="btn btn-success"
                style={{ flex: 1 }}
                onClick={submitContinue}
              >
                <i className="fas fa-play"></i> 开始续写
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ReadingContent({ section }) {
  if (!section) return null
  const title = section.title || `第${section.chapter}章 第${section.section}节`
  return (
    <>
      <div className="reading-content">
        <h1>{title}</h1>
        {section.content}
      </div>
    </>
  )
}

function MemoryPanel({ title, icon, color, defaultCollapsed = false, children }) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)
  return (
    <div className="memory-panel">
      <div className="memory-panel-header" onClick={() => setCollapsed((c) => !c)}>
        <i className={`fas ${icon}`} style={{ color }}></i>
        {title}
        <i className={`fas fa-chevron-down toggle ${collapsed ? 'collapsed' : ''}`}></i>
      </div>
      <div className={`memory-panel-body ${collapsed ? 'collapsed' : ''}`}>
        {children}
      </div>
    </div>
  )
}

function RelationshipBlock({ graph }) {
  const relations = graph?.relations || []
  if (relations.length === 0) {
    return (
      <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
        暂无关系数据
      </div>
    )
  }
  // group by source name
  const byName = {}
  const nameById = {}
  ;(graph?.entities || []).forEach((e) => {
    nameById[e.id] = e.name
  })
  relations.forEach((r) => {
    const src = nameById[r.source_id] || r.source_id
    const dst = nameById[r.target_id] || r.target_id
    if (!byName[src]) byName[src] = []
    byName[src].push({ to: dst, type: r.relation_type, label: r.label })
  })
  return (
    <>
      {Object.entries(byName).map(([name, rels]) => (
        <div key={name} className="rel-group">
          <div className="rel-name">{name}</div>
          {rels.map((r, i) => (
            <span key={i} className="rel-item">
              {r.to} ({r.label || r.type})
            </span>
          ))}
        </div>
      ))}
    </>
  )
}

function EntitiesBlock({ graph }) {
  const entities = graph?.entities || []
  if (entities.length === 0) {
    return (
      <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
        暂无实体数据
      </div>
    )
  }
  const byType = {}
  entities.forEach((e) => {
    const t = e.type || 'unknown'
    if (!byType[t]) byType[t] = []
    byType[t].push(e)
  })
  const TYPE_COLOR = {
    character: 'var(--accent-amber)',
    location: 'var(--accent-cyan)',
    item: 'var(--accent-emerald)',
    organization: 'var(--accent-purple)',
  }
  const TYPE_LABEL = {
    character: '人物',
    location: '地点',
    item: '物品',
    organization: '组织',
    event: '事件',
    concept: '概念',
  }
  return (
    <>
      {Object.entries(byType).map(([type, list]) => (
        <div key={type} style={{ marginBottom: 10 }}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: TYPE_COLOR[type] || 'var(--text-secondary)',
              marginBottom: 6,
            }}
          >
            {TYPE_LABEL[type] || type}
          </div>
          {list.map((e) => (
            <div key={e.id} className="entity-item">
              <span
                className="entity-name"
                style={{ color: TYPE_COLOR[type] || 'var(--accent-amber)' }}
              >
                {e.name}
              </span>
            </div>
          ))}
        </div>
      ))}
    </>
  )
}

function WorkingMemoryBlock({ memory }) {
  if (!memory) {
    return (
      <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
        暂无工作记忆数据
      </div>
    )
  }
  const slots = memory.sections || []
  const env = memory.scene?.environment || ''
  const chars = memory.scene?.active_characters || []
  return (
    <>
      {slots.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--accent-emerald)',
              marginBottom: 6,
            }}
          >
            短期缓存 ({slots.length})
          </div>
          {slots.map((s, i) => (
            <div key={i} className="entity-item">
              第{s.chapter}章 第{s.section}节 · {s.word_count} 字
            </div>
          ))}
        </div>
      )}
      {env && (
        <div style={{ marginBottom: 10 }}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--accent-cyan)',
              marginBottom: 6,
            }}
          >
            环境
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            {env}
          </div>
        </div>
      )}
      {chars.length > 0 && (
        <div>
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--accent-amber)',
              marginBottom: 6,
            }}
          >
            在场角色
          </div>
          {chars.map((c, i) => (
            <span key={i} className="rel-item">
              {c.name} · {c.emotion}
            </span>
          ))}
        </div>
      )}
      {!slots.length && !env && !chars.length && (
        <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          暂无工作记忆数据
        </div>
      )}
    </>
  )
}

function OutlineBlock({ outline }) {
  if (!outline?.root_summary && !outline?.outline) {
    return (
      <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
        暂无摘要
      </div>
    )
  }
  return (
    <>
      {outline.root_summary && (
        <div style={{ marginBottom: 10 }}>
          <strong style={{ color: 'var(--accent-purple)' }}>全书总纲:</strong>
          <div style={{ marginTop: 4, fontSize: 13 }}>{outline.root_summary}</div>
        </div>
      )}
      {outline.outline && (
        <div className="tree-view" style={{ maxHeight: 200, overflowY: 'auto' }}>
          {outline.outline}
        </div>
      )}
    </>
  )
}
