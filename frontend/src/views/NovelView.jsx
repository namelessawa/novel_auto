import React, { useEffect, useMemo, useState } from 'react'
import {
  fetchGraph,
  fetchMemory,
  fetchOutline,
  fetchSections,
  listTickSections,
} from '../services/api'
import { showToast } from '../utils/toast'

export default function NovelView({ novel, onAfterGenerated, onNavigate }) {
  const [sections, setSections] = useState([])
  const [memory, setMemory] = useState(null)
  const [outline, setOutline] = useState(null)
  const [graph, setGraph] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)

  const [generating, setGenerating] = useState(false)

  useEffect(() => {
    setSelected(null)
    loadAll()
  }, [novel?.id])

  const loadAll = async () => {
    setLoading(true)
    try {
      // v2.24 — 同时拉 tick 驱动节 (主) 与 legacy 节 (测试栏产物). 按 (chapter, section)
      // 升序合并, 同 key 时 tick 驱动优先, legacy 退让 — 保证 v2.24 主路径渲染稳定,
      // 同时让旧数据不丢。
      const [tickResp, legacyResp, mem, out, gph] = await Promise.all([
        listTickSections().catch(() => ({ sections: [] })),
        fetchSections().catch(() => ({ sections: [] })),
        fetchMemory().catch(() => null),
        fetchOutline().catch(() => null),
        fetchGraph().catch(() => null),
      ])
      const tickList = tickResp.sections || []
      const legacyList = legacyResp.sections || []
      const merged = mergeSections(tickList, legacyList)
      setSections(merged)
      setMemory(mem)
      setOutline(out)
      setGraph(gph)
      if (merged.length > 0) setSelected(merged.length - 1)
    } catch (err) {
      console.error('load novel detail failed:', err)
    }
    setLoading(false)
  }

  // tick 驱动节优先, legacy 退让; 按 (chapter, section) 升序排
  function mergeSections(tickList, legacyList) {
    const map = new Map()
    legacyList.forEach((s) => {
      const k = `${s.chapter}-${s.section}`
      map.set(k, { ...s, source: 'legacy' })
    })
    tickList.forEach((s) => {
      const k = `${s.chapter}-${s.section}`
      map.set(k, { ...s, source: 'tick' })
    })
    return Array.from(map.values()).sort(
      (a, b) =>
        (a.chapter - b.chapter) * 1000 + (a.section - b.section),
    )
  }

  // v2.23 — 续写按钮不再就地弹模态生成, 而是直接跳到创作控制台 (home),
  // 由控制台的"续写小说"卡片承担生成。这样进度条 / Tick 状态 / 阶段明细
  // 全部在一个面板, 用户不会在阅读视图里看到半截的实时正文。
  const startContinue = () => {
    if (typeof onNavigate === 'function') {
      onNavigate('home')
    } else {
      showToast('请前往创作控制台续写', 'info')
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
              <ReadingContent
                section={sections[selected]}
                index={selected}
                total={sections.length}
                onNav={(next) => setSelected(next)}
              />
            </div>
            <div className="reading-sidebar">
              {/* v2.23 — 标题区可点击跳转到对应工具视图。jumpHint 让用户知道点击会跳走;
                  graph/memory 在工具栏挂载, 由 App.jsx 的 onNavigate 直接切 view。 */}
              <MemoryPanel
                title="角色关系"
                icon="fa-users"
                color="var(--accent-cyan)"
                onJump={() => onNavigate?.('graph')}
                jumpHint="打开知识图谱"
              >
                <RelationshipBlock graph={graph} />
              </MemoryPanel>

              <MemoryPanel
                title="人物与实体"
                icon="fa-user-tag"
                color="var(--accent-amber)"
                onJump={() => onNavigate?.('graph')}
                jumpHint="打开知识图谱"
              >
                <EntitiesBlock graph={graph} />
              </MemoryPanel>

              <MemoryPanel
                title="工作记忆"
                icon="fa-layer-group"
                color="var(--accent-emerald)"
                onJump={() => onNavigate?.('memory')}
                jumpHint="打开记忆系统"
              >
                <WorkingMemoryBlock memory={memory} />
              </MemoryPanel>

              <MemoryPanel
                title="故事摘要"
                icon="fa-align-left"
                color="var(--accent-purple)"
                defaultCollapsed
                onJump={() => onNavigate?.('memory')}
                jumpHint="打开记忆系统"
              >
                <OutlineBlock outline={outline} />
              </MemoryPanel>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function ReadingContent({ section, index = 0, total = 0, onNav }) {
  if (!section) {
    return (
      <div className="empty-state">
        <i className="fas fa-book-reader"></i>
        <p>章节内容加载中…</p>
      </div>
    )
  }
  const title = section.title || `第${section.chapter}章 第${section.section}节`
  // 按空行/换行切段 — 让 CSS 的首行缩进与段距排版生效
  const paragraphs = String(section.content || '')
    .split(/\n+/)
    .map((p) => p.trim())
    .filter(Boolean)
  const hasPrev = index > 0
  const hasNext = index < total - 1
  return (
    <div className="reading-content">
      <h1>{title}</h1>
      <div className="reading-meta">
        第{section.chapter}章 · 第{section.section}节 ·{' '}
        {(section.word_count || 0).toLocaleString()} 字
        {section.source === 'legacy' ? ' · 节级管线' : ''}
      </div>
      {paragraphs.length > 0 ? (
        paragraphs.map((p, i) => <p key={i}>{p}</p>)
      ) : (
        <p style={{ color: 'var(--text-low)' }}>(本节暂无内容)</p>
      )}
      {typeof onNav === 'function' && total > 1 && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginTop: 44,
            paddingTop: 18,
            borderTop: '1px solid var(--line-1)',
            fontFamily: 'var(--font-ui)',
          }}
        >
          <button
            className="btn btn-secondary btn-sm"
            disabled={!hasPrev}
            onClick={() => hasPrev && onNav(index - 1)}
          >
            <i className="fas fa-arrow-left"></i> 上一节
          </button>
          <span
            style={{
              alignSelf: 'center',
              fontSize: 12,
              color: 'var(--text-low)',
            }}
          >
            {index + 1} / {total}
          </span>
          <button
            className="btn btn-secondary btn-sm"
            disabled={!hasNext}
            onClick={() => hasNext && onNav(index + 1)}
          >
            下一节 <i className="fas fa-arrow-right"></i>
          </button>
        </div>
      )}
    </div>
  )
}

function MemoryPanel({
  title,
  icon,
  color,
  defaultCollapsed = false,
  onJump,
  jumpHint,
  children,
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)
  // v2.23 — 标题区主体点击仍是折叠/展开; 右侧"跳转"图标 stopPropagation 进入工具视图。
  return (
    <div className="memory-panel">
      <div className="memory-panel-header" onClick={() => setCollapsed((c) => !c)}>
        <i className={`fas ${icon}`} style={{ color }}></i>
        <span style={{ flex: 1 }}>{title}</span>
        {typeof onJump === 'function' && (
          <i
            className="fas fa-arrow-up-right-from-square"
            title={jumpHint || '打开详情'}
            style={{
              fontSize: 11,
              opacity: 0.55,
              cursor: 'pointer',
              marginRight: 6,
            }}
            onClick={(e) => {
              e.stopPropagation()
              onJump()
            }}
          />
        )}
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
  // v2.22 — /api/graph 的 to_dict 返回 {source, target, relation_type, label};
  // 此前误用 source_id/target_id 让所有关系都归到 undefined, 侧栏几乎全空。
  relations.forEach((r) => {
    const srcId = r.source ?? r.source_id
    const tgtId = r.target ?? r.target_id
    const src = nameById[srcId] || srcId
    const dst = nameById[tgtId] || tgtId
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
