import React, { useMemo } from 'react'
import { classifyLoop } from '../../utils'

// v2.47 — § 03 伏笔池 + § 04 知识图谱 mini, 一行两列.
//
// 左: top-N OpenLoop, HIGH/MEDIUM, age, origin, refs, protected
// 右: KG mini SVG — protag center + 周边节点; 真实 KG 在 KGView 全屏.
//     入参 graph 是 fetchGraph() 的返回 {nodes:[...], edges:[...]}.

const PROTAG_KIND_HINTS = ['protagonist', 'protag', 'main', '主角', 'A']

function pickProtagonist(nodes = []) {
  return (
    nodes.find(
      (n) =>
        PROTAG_KIND_HINTS.some(
          (h) =>
            String(n.tier || n.role || n.kind || '').toLowerCase().includes(h.toLowerCase()),
        ),
    ) || nodes[0] || null
  )
}

export default function LoopsKGSection({ openLoops, graph, onJumpKg }) {
  const loops = (openLoops || []).slice(0, 8)
  const nodeCount = Array.isArray(graph?.nodes) ? graph.nodes.length : 0
  const edgeCount = Array.isArray(graph?.edges) ? graph.edges.length : 0

  // —— Mini SVG: 把 fetchGraph 的前 N 个节点放在中心+周围圈 ——
  const miniNodes = useMemo(() => {
    if (!Array.isArray(graph?.nodes) || graph.nodes.length === 0) return []
    const protag = pickProtagonist(graph.nodes)
    const others = graph.nodes.filter((n) => n !== protag).slice(0, 9)
    const arr = []
    if (protag) {
      arr.push({ ...protag, _x: 240, _y: 160, _r: 11, _isProtag: true })
    }
    const ringR = 110
    others.forEach((n, i) => {
      const angle = (Math.PI * 2 * i) / Math.max(1, others.length) - Math.PI / 2
      arr.push({
        ...n,
        _x: 240 + Math.cos(angle) * ringR,
        _y: 160 + Math.sin(angle) * ringR * 0.85,
        _r: 7,
      })
    })
    return arr
  }, [graph])

  return (
    <section className="dc-ov-row-loops-kg">
      {/* —— Open loops —— */}
      <div>
        <div className="dc-sec-head">
          <span className="dc-sec-num">§ 03</span>
          <h2 className="dc-sec-title">伏笔池</h2>
          <span className="dc-sec-sub">Showrunner 维护 ≥ 3 开放</span>
          <span className="dc-sec-meta">{loops.length} OPEN</span>
        </div>

        {loops.length === 0 ? (
          <div className="dc-ov-loops-empty">
            当前作品没有活跃伏笔 — Showrunner 会在 OpenLoop 池 &lt; 3 时主动补线索。
          </div>
        ) : (
          <div className="dc-ov-loops-list">
            {loops.map((raw, i) => {
              const l = classifyLoop(raw)
              const high = l.priority === 'high'
              return (
                <div
                  key={l.origin || l.title + i}
                  className={`dc-ov-loop ${high ? 'is-high' : ''}`}
                >
                  <div className="dc-ov-loop-row">
                    <div className="dc-ov-loop-left">
                      <span className="dc-ov-loop-title">{l.title}</span>
                      <span className={`dc-ov-loop-pri ${high ? 'is-high' : ''}`}>
                        {high ? 'HIGH' : 'MEDIUM'}
                      </span>
                    </div>
                    {l.age !== null && <span className="dc-ov-loop-age">{l.age} tick</span>}
                  </div>
                  {l.body && <div className="dc-ov-loop-body">{l.body}</div>}
                  <div className="dc-ov-loop-meta">
                    {l.origin && <span>origin = {l.origin}</span>}
                    {l.refs !== null && <span>refs × {l.refs}</span>}
                    {l.protectedFlag && <span className="dc-ov-loop-meta-red">protected</span>}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* —— KG mini —— */}
      <div>
        <div className="dc-sec-head">
          <span className="dc-sec-num">§ 04</span>
          <h2
            className="dc-sec-title is-jump"
            onClick={onJumpKg}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') onJumpKg?.()
            }}
            title="跳转至 知识图谱"
          >
            知识图谱
          </h2>
          <span className="dc-sec-sub">tick 末尾纯 Python 同步</span>
          <span className="dc-sec-meta">{nodeCount} ENT · {edgeCount} REL</span>
        </div>

        <div className="dc-ov-kg-card">
          <svg viewBox="0 0 480 320" width="100%" height="320" style={{ display: 'block' }}>
            {/* edges */}
            {miniNodes.length > 1 && (
              <g>
                {miniNodes.slice(1).map((n, i) => (
                  <line
                    key={`e-${i}`}
                    className="dc-ov-kg-edge"
                    x1={240}
                    y1={160}
                    x2={n._x}
                    y2={n._y}
                  />
                ))}
              </g>
            )}
            {/* nodes */}
            <g>
              {miniNodes.map((n, i) => (
                <g key={`n-${i}`}>
                  <circle
                    className={`dc-ov-kg-node-circle ${n._isProtag ? 'is-protag' : ''}`}
                    cx={n._x}
                    cy={n._y}
                    r={n._r}
                  />
                  <text
                    className="dc-ov-kg-label"
                    x={n._x}
                    y={n._y + 22}
                    textAnchor="middle"
                  >
                    {n.label || n.name || n.id}
                  </text>
                </g>
              ))}
            </g>
          </svg>

          <div className="dc-ov-kg-legend">
            <div className="dc-ov-kg-legend-item">
              <span className="dc-ov-kg-legend-dot-protag" />
              <span>主角</span>
            </div>
            <div className="dc-ov-kg-legend-item">
              <span className="dc-ov-kg-legend-dot-char" />
              <span>角色</span>
            </div>
            <div className="dc-ov-kg-legend-item">
              <span className="dc-ov-kg-legend-dot-place" />
              <span>地点</span>
            </div>
            <div className="dc-ov-kg-legend-meta">
              <span>{nodeCount} ENT</span>
              <span>{edgeCount} REL</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
