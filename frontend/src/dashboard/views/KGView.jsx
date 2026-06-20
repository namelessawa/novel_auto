import React, { useEffect, useMemo, useState } from 'react'
import { fetchEntityDetail, fetchGraph } from '../../services/api'

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

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const r = await fetchGraph()
        if (!cancelled) {
          setGraph({ nodes: r?.nodes || [], edges: r?.edges || [] })
        }
      } catch {
        if (!cancelled) setGraph({ nodes: [], edges: [] })
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

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

  // relations triples
  const relations = useMemo(() => {
    return (graph.edges || []).slice(0, 8).map((e) => {
      const s = posById.get(e.source) || graph.nodes.find((n) => n.id === e.source)
      const o = posById.get(e.target) || graph.nodes.find((n) => n.id === e.target)
      return {
        s: s?.label || s?.name || e.source,
        p: e.label || e.relation || e.type || 'rel',
        o: o?.label || o?.name || e.target,
      }
    })
  }, [graph.edges, graph.nodes, posById])

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
              {relations.map((r, i) => (
                <div key={i} className="dc-kg-rel">
                  <span className="dc-kg-rel-s">{r.s}</span>
                  <span className="dc-kg-rel-p">{r.p}</span>
                  <span className="dc-kg-rel-o">{r.o}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
