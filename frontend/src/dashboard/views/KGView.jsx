import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  createEntity,
  createRelation,
  deleteEntity,
  deleteRelation,
  fetchEntityDetail,
  fetchGraph,
} from '../../services/api'
import { showToast } from '../../utils/toast'

// v2.48 — § KG CRUD: 解析 "k=v; k2=v2" 简易语法 → attributes 对象 (复刻 GraphView).
// 设计取舍: 不引 JSON 编辑器, 4 字段表单, 用户直接打 "background=学者; loyalty=高".
function parseAttributesString(s) {
  if (!s || !s.trim()) return {}
  const out = {}
  for (const pair of s.split(/[;;]/)) {
    const idx = pair.indexOf('=')
    if (idx <= 0) continue
    const k = pair.slice(0, idx).trim()
    const v = pair.slice(idx + 1).trim()
    if (k) out[k] = v
  }
  return out
}

const ENTITY_TYPES = [
  { v: 'character', cn: '角色' },
  { v: 'location', cn: '地点' },
  { v: 'item', cn: '道具' },
  { v: 'skill', cn: '技能' },
  { v: 'faction', cn: '阵营' },
]

const RELATION_TYPES = [
  { v: 'located_at', cn: '位于' },
  { v: 'holds', cn: '持有' },
  { v: 'knows', cn: '认识' },
  { v: 'hostile', cn: '敌对' },
  { v: 'allied', cn: '同盟' },
  { v: 'loves', cn: '爱慕' },
  { v: 'parent_of', cn: '父母' },
  { v: 'member_of', cn: '所属' },
  { v: 'master_of', cn: '师徒' },
  { v: 'custom', cn: '自定义' },
]

// v2.47 — § 知识图谱. SVG canvas + 节点详情弹层 + 右侧 type stats / top entities / relations.

const NODE_TYPE_LABELS = {
  character: '角色',
  place: '地点',
  location: '地点',
  faction: '势力',
  object: '物件',
  item: '物件',
  event: '事件',
}

function classifyNodeKind(n) {
  const t = String(n.type || n.kind || n.role || '').toLowerCase()
  if (t.includes('protag') || t.includes('main') || t === 'a') return 'protag'
  if (t.includes('place') || t.includes('location')) return 'place'
  if (t.includes('faction')) return 'faction'
  if (t.includes('object') || t.includes('item')) return 'object'
  return 'char'
}

function layoutNodes(nodes) {
  if (!nodes?.length) return []
  // 简单 ring layout: degree 最高放中心, 其他绕一周.
  const sorted = [...nodes].sort((a, b) => (b.degree || 0) - (a.degree || 0))
  const center = sorted[0]
  const others = sorted.slice(1, 14)
  const positions = []
  positions.push({ ...center, x: 300, y: 220, r: 14 })
  const R = 180
  others.forEach((n, i) => {
    const angle = (Math.PI * 2 * i) / Math.max(1, others.length) - Math.PI / 2
    positions.push({
      ...n,
      x: 300 + Math.cos(angle) * R,
      y: 220 + Math.sin(angle) * R * 0.7,
      r: 10,
    })
  })
  return positions
}

export default function KGView() {
  const [graph, setGraph] = useState({ nodes: [], edges: [] })
  const [detail, setDetail] = useState(null)
  const [selectedId, setSelectedId] = useState(null)

  // v2.48 — § CRUD 状态
  const [entityForm, setEntityForm] = useState({
    id: '', name: '', entity_type: 'character', attributes: '',
  })
  const [relationForm, setRelationForm] = useState({
    source_id: '', target_id: '', relation_type: 'knows', label: '',
  })
  const [busy, setBusy] = useState(false)

  const loadGraph = useCallback(async () => {
    try {
      const r = await fetchGraph()
      setGraph({ nodes: r?.nodes || [], edges: r?.edges || [] })
    } catch {
      setGraph({ nodes: [], edges: [] })
    }
  }, [])

  useEffect(() => {
    loadGraph()
  }, [loadGraph])

  async function handleAddEntity(e) {
    e.preventDefault()
    if (!entityForm.id || !entityForm.name) {
      showToast('实体需要 id 和名称', 'error')
      return
    }
    setBusy(true)
    try {
      await createEntity({
        id: entityForm.id,
        name: entityForm.name,
        entity_type: entityForm.entity_type,
        attributes: parseAttributesString(entityForm.attributes),
      })
      setEntityForm({ id: '', name: '', entity_type: 'character', attributes: '' })
      await loadGraph()
      showToast('实体已添加', 'success')
    } catch (err) {
      showToast('添加失败: ' + (err?.message || '未知错误'), 'error')
    } finally {
      setBusy(false)
    }
  }

  async function handleAddRelation(e) {
    e.preventDefault()
    if (!relationForm.source_id || !relationForm.target_id) {
      showToast('关系需要源和目标 id', 'error')
      return
    }
    setBusy(true)
    try {
      await createRelation(relationForm)
      setRelationForm({ source_id: '', target_id: '', relation_type: 'knows', label: '' })
      await loadGraph()
      showToast('关系已添加', 'success')
    } catch (err) {
      showToast('添加关系失败: ' + (err?.message || '未知错误'), 'error')
    } finally {
      setBusy(false)
    }
  }

  async function handleDeleteEntity(entityId, entityName) {
    if (!entityId) return
    if (!window.confirm(`确认删除实体 "${entityName || entityId}"? 关联关系也会被一并删除, 无法恢复。`)) {
      return
    }
    setBusy(true)
    try {
      await deleteEntity(entityId)
      setDetail(null)
      setSelectedId(null)
      await loadGraph()
      showToast('实体已删除', 'success')
    } catch (err) {
      showToast('删除失败: ' + (err?.message || '未知错误'), 'error')
    } finally {
      setBusy(false)
    }
  }

  async function handleDeleteRelation(sourceId, targetId) {
    if (!sourceId || !targetId) return
    if (!window.confirm(`确认删除关系 ${sourceId} → ${targetId}?`)) return
    setBusy(true)
    try {
      await deleteRelation(sourceId, targetId)
      await loadGraph()
      showToast('关系已删除', 'success')
    } catch (err) {
      showToast('删除失败: ' + (err?.message || '未知错误'), 'error')
    } finally {
      setBusy(false)
    }
  }

  const positioned = useMemo(() => layoutNodes(graph.nodes), [graph.nodes])
  const posById = useMemo(() => new Map(positioned.map((p) => [p.id, p])), [positioned])

  // type stats
  const stats = useMemo(() => {
    const t = { character: 0, place: 0, faction: 0, object: 0 }
    graph.nodes.forEach((n) => {
      const k = classifyNodeKind(n)
      if (k === 'protag' || k === 'char') t.character++
      else if (k === 'place') t.place++
      else if (k === 'faction') t.faction++
      else if (k === 'object') t.object++
    })
    return t
  }, [graph.nodes])

  // top by degree
  const topEntities = useMemo(() => {
    return [...graph.nodes]
      .map((n) => ({
        ...n,
        _kind: classifyNodeKind(n),
      }))
      .sort((a, b) => (b.degree || 0) - (a.degree || 0))
      .slice(0, 7)
  }, [graph.nodes])

  async function selectNode(node) {
    setSelectedId(node.id)
    try {
      const r = await fetchEntityDetail(node.id)
      setDetail({ ...r, _kind: classifyNodeKind(node) })
    } catch {
      setDetail({ ...node, _kind: classifyNodeKind(node) })
    }
  }

  return (
    <div className="dc-view-switch dc-kg-root">
      <div className="dc-sec-head">
        <span className="dc-sec-num">§ KG</span>
        <h2 className="dc-sec-title">知识图谱</h2>
        <span className="dc-sec-sub">tick 末尾纯 Python 同步</span>
        <span className="dc-sec-meta">
          {graph.nodes.length} ENT · {graph.edges.length} REL
        </span>
      </div>

      <div className="dc-kg-row">
        {/* canvas */}
        <div className="dc-kg-canvas">
          <svg viewBox="0 0 600 440" style={{ width: '100%', height: 'auto', display: 'block' }}>
            <g stroke="var(--border2)" strokeWidth="1" fill="none">
              {(graph.edges || []).map((e, i) => {
                const a = posById.get(e.source)
                const b = posById.get(e.target)
                if (!a || !b) return null
                return <line key={`e-${i}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
              })}
            </g>
            {positioned.map((n, i) => {
              const k = classifyNodeKind(n)
              const isSel = selectedId === n.id
              const fill =
                k === 'protag' ? 'var(--accent)' : k === 'place' ? 'none' : 'var(--ink)'
              const stroke = k === 'place' || k === 'faction' ? 'var(--text)' : 'none'
              return (
                <g
                  key={`n-${i}`}
                  onClick={() => selectNode(n)}
                  style={{ cursor: 'pointer' }}
                >
                  {k === 'place' ? (
                    <rect
                      x={n.x - n.r}
                      y={n.y - n.r}
                      width={n.r * 2}
                      height={n.r * 2}
                      fill={fill}
                      stroke={stroke}
                      strokeWidth="1.5"
                    />
                  ) : k === 'faction' ? (
                    <path
                      d={`M ${n.x} ${n.y - n.r} L ${n.x + n.r} ${n.y} L ${n.x} ${n.y + n.r} L ${n.x - n.r} ${n.y} Z`}
                      fill="none"
                      stroke={isSel ? 'var(--accent)' : 'var(--text)'}
                      strokeWidth="1.5"
                    />
                  ) : (
                    <circle cx={n.x} cy={n.y} r={n.r} fill={isSel ? 'var(--accent)' : fill} />
                  )}
                  <text
                    x={n.x}
                    y={n.y + n.r + 14}
                    textAnchor="middle"
                    fontFamily="Noto Serif SC, serif"
                    fontSize="11"
                    fontWeight="500"
                    fill="var(--text)"
                  >
                    {n.label || n.name || n.id}
                  </text>
                </g>
              )
            })}

            {/* legend */}
            <g fontFamily="JetBrains Mono, monospace" fontSize="9" fill="var(--text3)">
              <rect x="24" y="404" width="9" height="9" fill="var(--text)" />
              <text x="40" y="412">角色</text>
              <rect x="92" y="404" width="9" height="9" fill="none" stroke="var(--text)" strokeWidth="1.3" />
              <text x="108" y="412">地点</text>
              <path d="M 168 408 L 173 403 L 178 408 L 173 413 Z" fill="none" stroke="var(--accent)" strokeWidth="1.3" />
              <text x="186" y="412">势力</text>
              <circle cx="240" cy="408" r="4" fill="var(--text3)" />
              <text x="250" y="412">物件</text>
            </g>
          </svg>

          {detail && (
            <div className="dc-kg-detail">
              <div className="dc-kg-detail-head">
                <span className="dc-kg-detail-kicker">
                  {(detail._kind || '').toUpperCase()}
                </span>
                <button
                  type="button"
                  className="dc-kg-detail-close"
                  onClick={() => {
                    setDetail(null)
                    setSelectedId(null)
                  }}
                >
                  <svg width="11" height="11" viewBox="0 0 15 15" fill="none">
                    <path
                      d="M3 3 L12 12 M12 3 L3 12"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
              </div>
              <div className="dc-kg-detail-title-row">
                <span className="dc-kg-detail-title">
                  {detail.label || detail.name || detail.id}
                </span>
                <span className="dc-kg-detail-kind">
                  {NODE_TYPE_LABELS[detail.type] || detail.type || ''}
                </span>
              </div>
              <div className="dc-kg-detail-stats">
                <div className="dc-kg-detail-stat">
                  <span className="dc-kg-detail-stat-lbl">DEGREE</span>
                  <span className="dc-kg-detail-stat-num">{detail.degree ?? '—'}</span>
                </div>
                <div className="dc-kg-detail-stat">
                  <span className="dc-kg-detail-stat-lbl">RELATIONS</span>
                  <span className="dc-kg-detail-stat-num">
                    {(detail.relations || detail.edges || []).length || '—'}
                  </span>
                </div>
              </div>
              {detail.description && (
                <p className="dc-kg-detail-desc">{detail.description}</p>
              )}
              {/* v2.48 — § 删除实体 */}
              <button
                type="button"
                className="dc-kg-detail-delete"
                onClick={() =>
                  handleDeleteEntity(detail.id, detail.label || detail.name)
                }
                disabled={busy}
              >
                删除实体
              </button>
            </div>
          )}
        </div>

        {/* side */}
        <div className="dc-kg-side">
          {/* type stats */}
          <div className="dc-kg-stats">
            <div className="dc-kg-stat">
              <span className="dc-kg-stat-lbl">角色 · CHAR</span>
              <span className="dc-kg-stat-num">{stats.character}</span>
            </div>
            <div className="dc-kg-stat">
              <span className="dc-kg-stat-lbl">地点 · PLACE</span>
              <span className="dc-kg-stat-num">{stats.place}</span>
            </div>
            <div className="dc-kg-stat">
              <span className="dc-kg-stat-lbl">势力 · FACTION</span>
              <span className="dc-kg-stat-num">{stats.faction}</span>
            </div>
            <div className="dc-kg-stat">
              <span className="dc-kg-stat-lbl">物件 · OBJECT</span>
              <span className="dc-kg-stat-num">{stats.object}</span>
            </div>
          </div>

          {/* top entities */}
          <div>
            <span className="dc-kg-side-kicker">高频实体 · BY DEGREE</span>
            <div className="dc-kg-ents" style={{ marginTop: 12 }}>
              {topEntities.map((e) => (
                <div key={e.id} className="dc-kg-ent" onClick={() => selectNode(e)}>
                  <span
                    className={`dc-kg-ent-dot ${e._kind === 'protag' ? 'is-protag' : ''} ${e._kind === 'place' ? 'is-place' : ''}`}
                  />
                  <span className="dc-kg-ent-name">{e.label || e.name || e.id}</span>
                  <span className="dc-kg-ent-type">
                    {NODE_TYPE_LABELS[e.type] || e.type || '—'}
                  </span>
                  <span className="dc-kg-ent-deg">deg {e.degree ?? '—'}</span>
                </div>
              ))}
              {topEntities.length === 0 && (
                <div style={{ padding: 16, font: "400 12px/1.5 'Inter', sans-serif", color: 'var(--text3)' }}>
                  KG 尚未建立 — tick 推进后由 KG Sync 同步.
                </div>
              )}
            </div>
          </div>

          {/* relations */}
          <div>
            <span className="dc-kg-side-kicker">关系三元组 · RELATIONS</span>
            <div className="dc-kg-rels" style={{ marginTop: 12 }}>
              {(graph.edges || []).slice(0, 8).map((e, i) => {
                const s = posById.get(e.source) || graph.nodes.find((n) => n.id === e.source)
                const o = posById.get(e.target) || graph.nodes.find((n) => n.id === e.target)
                return (
                  <div key={i} className="dc-kg-rel">
                    <span className="dc-kg-rel-s">{s?.label || s?.name || e.source}</span>
                    <span className="dc-kg-rel-p">{e.label || e.relation || e.type || 'rel'}</span>
                    <span className="dc-kg-rel-o">{o?.label || o?.name || e.target}</span>
                    <button
                      type="button"
                      className="dc-kg-rel-delete"
                      onClick={() => handleDeleteRelation(e.source, e.target)}
                      disabled={busy}
                      title="删除这条关系"
                    >
                      ×
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      {/* v2.48 — § CRUD: 添加实体 + 添加关系 表单 */}
      <div className="dc-kg-crud">
        <form className="dc-kg-crud-card" onSubmit={handleAddEntity}>
          <span className="dc-kg-side-kicker">添加实体</span>
          <div className="dc-kg-crud-row">
            <input
              className="dc-input"
              type="text"
              placeholder="id (如 protagonist)"
              value={entityForm.id}
              onChange={(e) => setEntityForm({ ...entityForm, id: e.target.value })}
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            />
            <input
              className="dc-input"
              type="text"
              placeholder="名称"
              value={entityForm.name}
              onChange={(e) => setEntityForm({ ...entityForm, name: e.target.value })}
            />
          </div>
          <div className="dc-kg-crud-row">
            <select
              className="dc-input"
              value={entityForm.entity_type}
              onChange={(e) => setEntityForm({ ...entityForm, entity_type: e.target.value })}
            >
              {ENTITY_TYPES.map((t) => (
                <option key={t.v} value={t.v}>{t.cn} · {t.v}</option>
              ))}
            </select>
            <button type="submit" className="dc-btn" disabled={busy}>+ 添加</button>
          </div>
          <input
            className="dc-input"
            type="text"
            placeholder="属性 (可选): background=学者; loyalty=高"
            value={entityForm.attributes}
            onChange={(e) => setEntityForm({ ...entityForm, attributes: e.target.value })}
          />
        </form>

        <form className="dc-kg-crud-card" onSubmit={handleAddRelation}>
          <span className="dc-kg-side-kicker">添加关系</span>
          <div className="dc-kg-crud-row">
            <input
              className="dc-input"
              type="text"
              placeholder="源 id"
              value={relationForm.source_id}
              onChange={(e) => setRelationForm({ ...relationForm, source_id: e.target.value })}
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            />
            <input
              className="dc-input"
              type="text"
              placeholder="目标 id"
              value={relationForm.target_id}
              onChange={(e) => setRelationForm({ ...relationForm, target_id: e.target.value })}
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            />
          </div>
          <div className="dc-kg-crud-row">
            <select
              className="dc-input"
              value={relationForm.relation_type}
              onChange={(e) => setRelationForm({ ...relationForm, relation_type: e.target.value })}
            >
              {RELATION_TYPES.map((t) => (
                <option key={t.v} value={t.v}>{t.cn} · {t.v}</option>
              ))}
            </select>
            <button type="submit" className="dc-btn" disabled={busy}>+ 添加</button>
          </div>
          <input
            className="dc-input"
            type="text"
            placeholder="关系描述 (可选)"
            value={relationForm.label}
            onChange={(e) => setRelationForm({ ...relationForm, label: e.target.value })}
          />
        </form>
      </div>
    </div>
  )
}
