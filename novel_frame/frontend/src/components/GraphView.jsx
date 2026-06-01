import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { fetchGraph, createEntity, createRelation } from '../services/api'

const TYPE_COLORS = {
  character: '#6366f1',
  location: '#22c55e',
  item: '#f59e0b',
  skill: '#ef4444',
  faction: '#8b5cf6',
}

const TYPE_LABELS = {
  character: '角色',
  location: '地点',
  item: '道具',
  skill: '技能',
  faction: '阵营',
}

const GRAPH_HEIGHT = 560

// Lazy-load ForceGraph2D
const LazyForceGraph2D = React.lazy(() => import('react-force-graph-2d'))

export default function GraphView({ refreshKey, isVisible }) {
  const [graphData, setGraphData] = useState({ entities: [], relations: [] })
  const [loading, setLoading] = useState(true)
  const [selectedNode, setSelectedNode] = useState(null)
  const [hoverNode, setHoverNode] = useState(null)
  const [containerWidth, setContainerWidth] = useState(0)
  const graphRef = useRef(null)
  const containerRef = useRef(null)

  // Entity form
  const [entityForm, setEntityForm] = useState({
    id: '', name: '', entity_type: 'character',
  })
  // Relation form
  const [relationForm, setRelationForm] = useState({
    source_id: '', target_id: '', relation_type: 'knows', label: '',
  })

  const loadGraph = useCallback(async () => {
    try {
      const data = await fetchGraph()
      setGraphData(data)
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    loadGraph()
  }, [loadGraph, refreshKey])

  // Measure container width when tab becomes visible
  useEffect(() => {
    if (!isVisible) return
    const measure = () => {
      if (containerRef.current) {
        const w = containerRef.current.clientWidth
        if (w > 0) setContainerWidth(w)
      }
    }
    const timer = setTimeout(measure, 100)
    window.addEventListener('resize', measure)
    return () => {
      clearTimeout(timer)
      window.removeEventListener('resize', measure)
    }
  }, [isVisible])

  // Build graph data for ForceGraph2D — filter orphan links
  const forceGraphData = useMemo(() => {
    const nodes = graphData.entities.map((e) => ({
      id: e.id,
      name: e.name,
      type: e.type,
      attributes: e.attributes || {},
    }))
    const nodeIds = new Set(nodes.map((n) => n.id))
    const links = graphData.relations
      .filter((r) => nodeIds.has(r.source) && nodeIds.has(r.target))
      .map((r) => ({
        source: r.source,
        target: r.target,
        label: r.label || r.relation_type,
        relation_type: r.relation_type,
      }))
    return { nodes, links }
  }, [graphData])

  // Build neighbor sets for highlight logic
  const neighborSet = useMemo(() => {
    const ns = new Map()
    forceGraphData.links.forEach((link) => {
      const sid = typeof link.source === 'object' ? link.source.id : link.source
      const tid = typeof link.target === 'object' ? link.target.id : link.target
      if (!ns.has(sid)) ns.set(sid, new Set())
      if (!ns.has(tid)) ns.set(tid, new Set())
      ns.get(sid).add(tid)
      ns.get(tid).add(sid)
    })
    return ns
  }, [forceGraphData.links])

  const isNeighbor = useCallback((nodeId) => {
    if (!selectedNode) return false
    return neighborSet.get(selectedNode.id)?.has(nodeId) || false
  }, [selectedNode, neighborSet])

  const isLinkedToSelected = useCallback((link) => {
    if (!selectedNode) return false
    const sid = typeof link.source === 'object' ? link.source.id : link.source
    const tid = typeof link.target === 'object' ? link.target.id : link.target
    return sid === selectedNode.id || tid === selectedNode.id
  }, [selectedNode])

  // Fit view on data change
  useEffect(() => {
    if (isVisible && graphRef.current && forceGraphData.nodes.length > 0 && containerWidth > 0) {
      const timer = setTimeout(() => {
        try { graphRef.current.zoomToFit(400, 60) } catch (e) { /* ignore */ }
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [forceGraphData.nodes.length, isVisible, containerWidth])

  // Custom node rendering
  const paintNode = useCallback((node, ctx, globalScale) => {
    if (typeof node.x !== 'number' || typeof node.y !== 'number') return

    const isSelected = selectedNode?.id === node.id
    const isNbr = isNeighbor(node.id)
    const isHovered = hoverNode?.id === node.id
    const hasSelection = !!selectedNode
    const color = TYPE_COLORS[node.type] || '#6366f1'

    let radius, alpha, labelAlpha

    if (!hasSelection) {
      radius = 8
      alpha = 1
      labelAlpha = 1
    } else if (isSelected) {
      radius = 14
      alpha = 1
      labelAlpha = 1
    } else if (isNbr) {
      radius = 8
      alpha = 0.7
      labelAlpha = 0.7
    } else {
      radius = 5
      alpha = 0.12
      labelAlpha = 0.1
    }

    if (isHovered && !isSelected) {
      radius = Math.max(radius, 10)
      alpha = Math.max(alpha, 0.9)
      labelAlpha = Math.max(labelAlpha, 0.9)
    }

    ctx.save()
    ctx.globalAlpha = alpha

    // Glow for selected node
    if (isSelected) {
      ctx.shadowColor = color
      ctx.shadowBlur = 25
      ctx.beginPath()
      ctx.arc(node.x, node.y, radius + 4, 0, 2 * Math.PI)
      ctx.fillStyle = color
      ctx.globalAlpha = 0.15
      ctx.fill()
      ctx.globalAlpha = 1
      ctx.shadowBlur = 0
    }

    // Outer ring
    ctx.beginPath()
    ctx.arc(node.x, node.y, radius + 1.5, 0, 2 * Math.PI)
    ctx.fillStyle = isSelected ? '#ffffff' : 'rgba(255,255,255,0.08)'
    ctx.globalAlpha = isSelected ? 0.3 : alpha * 0.5
    ctx.fill()

    // Node body
    ctx.globalAlpha = alpha
    ctx.beginPath()
    ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
    ctx.fillStyle = color
    ctx.fill()

    // Inner highlight (glossy)
    const grad = ctx.createRadialGradient(
      node.x - radius * 0.3, node.y - radius * 0.3, 0,
      node.x, node.y, radius
    )
    grad.addColorStop(0, 'rgba(255,255,255,0.25)')
    grad.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = grad
    ctx.fill()

    // Label
    const fontSize = isSelected ? 14 / globalScale : 12 / globalScale
    ctx.font = `${isSelected ? 'bold ' : ''}${fontSize}px sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.globalAlpha = labelAlpha

    // Text shadow for readability
    ctx.shadowColor = 'rgba(0,0,0,0.8)'
    ctx.shadowBlur = 3
    ctx.fillStyle = isSelected ? '#ffffff' : '#c4c4cc'
    ctx.fillText(node.name, node.x, node.y + radius + 3)
    ctx.shadowBlur = 0

    ctx.restore()
  }, [selectedNode, hoverNode, isNeighbor])

  // Link styling
  const linkColor = useCallback((link) => {
    if (!selectedNode) return 'rgba(99, 102, 241, 0.25)'
    return isLinkedToSelected(link)
      ? 'rgba(99, 102, 241, 0.7)'
      : 'rgba(99, 102, 241, 0.06)'
  }, [selectedNode, isLinkedToSelected])

  const linkWidth = useCallback((link) => {
    if (!selectedNode) return 1
    return isLinkedToSelected(link) ? 2.5 : 0.3
  }, [selectedNode, isLinkedToSelected])

  const handleNodeClick = useCallback((node) => {
    setSelectedNode((prev) => prev?.id === node.id ? null : node)
  }, [])

  const handleBackgroundClick = useCallback(() => {
    setSelectedNode(null)
  }, [])

  // Get selected entity details
  const selectedEntity = useMemo(() => {
    if (!selectedNode) return null
    const entity = graphData.entities.find((e) => e.id === selectedNode.id)
    if (!entity) return null
    const relations = graphData.relations.filter(
      (r) => r.source === entity.id || r.target === entity.id
    )
    return { ...entity, relations }
  }, [selectedNode, graphData])

  const handleAddEntity = async (e) => {
    e.preventDefault()
    if (!entityForm.id || !entityForm.name) return
    await createEntity(entityForm)
    setEntityForm({ id: '', name: '', entity_type: 'character' })
    loadGraph()
  }

  const handleAddRelation = async (e) => {
    e.preventDefault()
    if (!relationForm.source_id || !relationForm.target_id) return
    await createRelation(relationForm)
    setRelationForm({ source_id: '', target_id: '', relation_type: 'knows', label: '' })
    loadGraph()
  }

  const showGraph = isVisible && containerWidth > 0 && forceGraphData.nodes.length > 0

  return (
    <div>
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px 8px' }}>
          <div className="card-title" style={{ marginBottom: 0 }}>
            知识图谱
            <span style={{ fontWeight: 400, fontSize: 12, marginLeft: 8, color: 'var(--text-muted)' }}>
              {graphData.entities.length} 实体 &middot; {graphData.relations.length} 关系
            </span>
          </div>
        </div>

        <div ref={containerRef} className="graph-canvas-wrap">
          {graphData.entities.length === 0 ? (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              height: '100%', color: 'var(--text-muted)',
            }}>
              暂无实体。可通过下方表单手动添加，或开始生成后自动创建。
            </div>
          ) : showGraph ? (
            <React.Suspense fallback={<div style={{ color: 'var(--text-muted)', textAlign: 'center', paddingTop: 40 }}>加载图谱组件…</div>}>
            <LazyForceGraph2D
              ref={graphRef}
              graphData={forceGraphData}
              width={containerWidth}
              height={GRAPH_HEIGHT}
              backgroundColor="#0f1117"
              nodeCanvasObject={paintNode}
              nodePointerAreaPaint={(node, color, ctx) => {
                if (typeof node.x !== 'number') return
                ctx.beginPath()
                ctx.arc(node.x, node.y, 12, 0, 2 * Math.PI)
                ctx.fillStyle = color
                ctx.fill()
              }}
              linkColor={linkColor}
              linkWidth={linkWidth}
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={1}
              onNodeClick={handleNodeClick}
              onBackgroundClick={handleBackgroundClick}
              onNodeHover={setHoverNode}
              cooldownTicks={80}
              d3AlphaDecay={0.02}
              d3VelocityDecay={0.3}
            />
            </React.Suspense>
          ) : null}
        </div>

        {/* Legend */}
        <div style={{
          padding: '10px 20px 14px',
          display: 'flex', gap: 16, fontSize: 12,
          borderTop: '1px solid var(--border)',
        }}>
          {Object.entries(TYPE_COLORS).map(([type, color]) => (
            <span key={type} style={{
              display: 'flex', alignItems: 'center', gap: 5,
              color: 'var(--text-secondary)',
            }}>
              <span style={{
                width: 8, height: 8, borderRadius: '50%',
                background: color, display: 'inline-block',
                boxShadow: `0 0 6px ${color}44`,
              }} />
              {TYPE_LABELS[type] || type}
            </span>
          ))}
        </div>
      </div>

      {/* Entity Detail Panel */}
      {selectedEntity && (
        <div className="card entity-detail-panel">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
            <span style={{
              width: 14, height: 14, borderRadius: '50%',
              background: TYPE_COLORS[selectedEntity.type] || '#6366f1',
              display: 'inline-block',
              boxShadow: `0 0 8px ${TYPE_COLORS[selectedEntity.type] || '#6366f1'}66`,
            }} />
            <span style={{ fontSize: 16, fontWeight: 600 }}>{selectedEntity.name}</span>
            <span style={{
              fontSize: 11, color: 'var(--text-muted)',
              padding: '2px 8px', background: 'var(--bg-hover)',
              borderRadius: 4,
            }}>
              {TYPE_LABELS[selectedEntity.type] || selectedEntity.type}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace' }}>
              {selectedEntity.id}
            </span>
          </div>

          {/* Attributes */}
          {Object.keys(selectedEntity.attributes || {}).length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                属性
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {Object.entries(selectedEntity.attributes).map(([key, val]) => (
                  <span key={key} className="entity-attr-tag">
                    <span style={{ color: 'var(--text-muted)' }}>{key}:</span>{' '}
                    {Array.isArray(val) ? val.join(', ') : String(val)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Relations */}
          {selectedEntity.relations.length > 0 && (
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                关系 ({selectedEntity.relations.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {selectedEntity.relations.map((r, i) => {
                  const isSource = r.source === selectedEntity.id
                  const otherEntity = graphData.entities.find(
                    (e) => e.id === (isSource ? r.target : r.source)
                  )
                  return (
                    <div key={i} className="entity-relation-row">
                      <span style={{ color: TYPE_COLORS[selectedEntity.type], fontSize: 13 }}>
                        {selectedEntity.name}
                      </span>
                      <span style={{
                        color: 'var(--accent)', fontSize: 11,
                        padding: '1px 6px', background: 'rgba(99,102,241,0.1)',
                        borderRadius: 3,
                      }}>
                        {r.label || r.relation_type}
                      </span>
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>→</span>
                      <span style={{
                        color: TYPE_COLORS[otherEntity?.type] || 'var(--text-secondary)',
                        fontSize: 13,
                      }}>
                        {otherEntity?.name || (isSource ? r.target : r.source)}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Add entity / relation forms */}
      <div style={{ display: 'flex', gap: 16 }}>
        <div className="card" style={{ flex: 1 }}>
          <div className="card-title">添加实体</div>
          <form onSubmit={handleAddEntity}>
            <div className="form-row">
              <input
                type="text" placeholder="ID（如 protagonist）"
                value={entityForm.id}
                onChange={(e) => setEntityForm({ ...entityForm, id: e.target.value })}
              />
              <input
                type="text" placeholder="名称"
                value={entityForm.name}
                onChange={(e) => setEntityForm({ ...entityForm, name: e.target.value })}
              />
            </div>
            <div className="form-row">
              <select
                value={entityForm.entity_type}
                onChange={(e) => setEntityForm({ ...entityForm, entity_type: e.target.value })}
              >
                <option value="character">角色</option>
                <option value="location">地点</option>
                <option value="item">道具</option>
                <option value="skill">技能</option>
                <option value="faction">阵营</option>
              </select>
              <button type="submit" className="btn btn-primary">添加</button>
            </div>
          </form>
        </div>

        <div className="card" style={{ flex: 1 }}>
          <div className="card-title">添加关系</div>
          <form onSubmit={handleAddRelation}>
            <div className="form-row">
              <input
                type="text" placeholder="源实体 ID"
                value={relationForm.source_id}
                onChange={(e) => setRelationForm({ ...relationForm, source_id: e.target.value })}
              />
              <input
                type="text" placeholder="目标实体 ID"
                value={relationForm.target_id}
                onChange={(e) => setRelationForm({ ...relationForm, target_id: e.target.value })}
              />
            </div>
            <div className="form-row">
              <select
                value={relationForm.relation_type}
                onChange={(e) => setRelationForm({ ...relationForm, relation_type: e.target.value })}
              >
                <option value="located_at">位于</option>
                <option value="holds">持有</option>
                <option value="knows">认识</option>
                <option value="hostile">敌对</option>
                <option value="allied">同盟</option>
                <option value="loves">爱慕</option>
                <option value="parent_of">父母</option>
                <option value="member_of">所属</option>
                <option value="master_of">师徒</option>
                <option value="custom">自定义</option>
              </select>
              <input
                type="text" placeholder="关系描述"
                value={relationForm.label}
                onChange={(e) => setRelationForm({ ...relationForm, label: e.target.value })}
              />
              <button type="submit" className="btn btn-primary">添加</button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
