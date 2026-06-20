import React, { useEffect, useMemo, useState } from 'react'
import { fetchAgentDetail, fetchAgents } from '../../services/api'

// v2.47 — § Agent 上下文.
// 左: agent roster 10 行 (running dot + cn 名 + cadence + 估算 token).
// 右: 选中 agent 的"上下文窗口装配" 7 段分布 + 总 budget + system prompt 预览.
//
// 上下文窗口分布字段后端 fetchAgentDetail 给的 live_context 是 dict,
// 这里把 key → bucket 简化为 6-7 段 (固定 schema).

const CTX_SCHEMA = [
  { key: 'world_state',          label: '世界状态', sub: 'WorldState snapshot',         color: '#c8392a' },
  { key: 'character_states',     label: '角色状态', sub: 'CharacterState × N',          color: '#525252' },
  { key: 'recent_events',        label: '近事件',   sub: 'last N tick 事件流',          color: '#8A8A8A' },
  { key: 'open_loops_top',       label: '伏笔',     sub: 'top-10 open loop',            color: '#B8B8B6' },
  { key: 'style_anchors',        label: '风格锚点', sub: 'style_anchors_top_5',         color: '#D4D4D2' },
  { key: 'novelty_warnings',     label: '新颖性反馈', sub: 'novelty_warnings',          color: '#EFEDE8' },
  { key: 'system_prompt',        label: 'system prompt', sub: 'NARRATOR_SYSTEM_PROMPT', color: '#3a3a3a' },
]

function estimateTokens(obj) {
  if (obj == null) return 0
  if (typeof obj === 'string') return Math.ceil(obj.length / 4)
  try {
    return Math.ceil(JSON.stringify(obj).length / 4)
  } catch {
    return 0
  }
}

function mapCtxBuckets(detail) {
  const live = detail?.live_context || {}
  const prompt = detail?.prompt?.primary || ''
  return CTX_SCHEMA.map((s) => {
    let raw
    switch (s.key) {
      case 'world_state':     raw = live.world_state ?? null; break
      case 'character_states': raw = live.character_states || live.characters_preview; break
      case 'recent_events':    raw = live.recent_events_3_ticks || live.events_last_tick || live.tick_history_20; break
      case 'open_loops_top':   raw = live.open_loops_top_10 || live.open_loops_with_age; break
      case 'style_anchors':    raw = live.style_anchors_top_5; break
      case 'novelty_warnings': raw = live.novelty_warnings; break
      case 'system_prompt':    raw = prompt; break
      default: raw = null
    }
    return { ...s, tok: estimateTokens(raw) }
  })
}

export default function AgentView() {
  const [agents, setAgents] = useState([])
  const [active, setActive] = useState('narrator_agent')
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const r = await fetchAgents()
        if (!cancelled) setAgents(r?.agents || [])
      } catch {
        if (!cancelled) setAgents([])
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const r = await fetchAgentDetail(active)
        if (!cancelled) setDetail(r)
      } catch {
        if (!cancelled) setDetail(null)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [active])

  const buckets = useMemo(() => mapCtxBuckets(detail), [detail])
  const total = buckets.reduce((s, b) => s + b.tok, 0)
  const budget = 16000
  const totalPct = Math.min(100, Math.round((total / budget) * 100))

  return (
    <div className="dc-view-switch dc-ag-root">
      <div className="dc-sec-head">
        <span className="dc-sec-num">§ Agent</span>
        <h2 className="dc-sec-title">Agent 上下文</h2>
        <span className="dc-sec-sub">10 agent · 上下文窗口装配</span>
        <span className="dc-sec-meta">{agents.length} REGISTERED</span>
      </div>

      <div className="dc-ag-row">
        {/* roster */}
        <div className="dc-ag-col">
          <span className="dc-ag-col-kicker">AGENT 名册 · {agents.length}</span>
          <div className="dc-ag-list">
            {agents.map((a) => {
              const id = a.id || a.name
              const isActive = id === active
              return (
                <div
                  key={id}
                  className={`dc-ag-list-row ${isActive ? 'is-active' : ''}`}
                  onClick={() => setActive(id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') setActive(id)
                  }}
                >
                  <span className={`dc-ag-list-dot ${isActive ? '' : 'is-idle'}`} />
                  <div className="dc-ag-list-body">
                    <span className="dc-ag-list-name">{a.cn_name || a.name || id}</span>
                    <span className="dc-ag-list-sub">
                      {a.cadence || '—'}
                      {a.llm_tier ? ` · ${a.llm_tier}` : ''}
                    </span>
                  </div>
                  <span className={`dc-ag-list-tok ${isActive ? 'is-active' : ''}`}>
                    {a.has_prompt ? 'PROMPT' : ''}
                  </span>
                </div>
              )
            })}
            {agents.length === 0 && (
              <div style={{ font: "400 12px/1.5 'Inter', sans-serif", color: 'var(--text3)' }}>
                后端 /api/agents 未返回 — 检查登录态
              </div>
            )}
          </div>
        </div>

        {/* ctx window */}
        <div className="dc-ag-col">
          <span className="dc-ag-col-kicker">
            {detail?.id || active} · 上下文窗口装配
          </span>
          <div className="dc-ag-ctx">
            <div className="dc-ag-ctx-head">
              <div className="dc-ag-ctx-head-l">
                <span className="dc-ag-ctx-name">{detail?.id || active}</span>
                <span className="dc-ag-ctx-badge">
                  {detail?.live_context?.available ? 'LIVE' : 'STATIC'}
                </span>
              </div>
              <span className="dc-ag-ctx-aux">{detail?.role || '—'}</span>
            </div>

            {/* segmented composition bar */}
            <div className="dc-ag-ctx-segbar">
              {buckets.map((b) => {
                const w = total > 0 ? (b.tok / total) * 100 : 0
                return (
                  <span
                    key={b.key}
                    className="dc-ag-ctx-seg"
                    style={{ width: `${w}%`, background: b.color }}
                    title={`${b.label} · ${b.tok}`}
                  />
                )
              })}
            </div>

            {/* breakdown */}
            <div className="dc-ag-ctx-rows">
              {buckets.map((b) => (
                <div key={b.key} className="dc-ag-ctx-rowx">
                  <span className="dc-ag-ctx-swatch" style={{ background: b.color }} />
                  <div className="dc-ag-ctx-rowx-body">
                    <span className="dc-ag-ctx-rowx-name">{b.label}</span>
                    <span className="dc-ag-ctx-rowx-sub">{b.sub}</span>
                  </div>
                  <span className="dc-ag-ctx-rowx-tok">{b.tok.toLocaleString()}</span>
                </div>
              ))}
            </div>

            <div className="dc-ag-ctx-total">
              <span className="dc-ag-ctx-total-lbl">CONTEXT TOTAL</span>
              <span className="dc-ag-ctx-total-right">
                <span className="dc-ag-ctx-total-num">{total.toLocaleString()}</span>
                <span className="dc-ag-ctx-total-aux">/ {budget.toLocaleString()} budget · {totalPct}%</span>
              </span>
            </div>

            {detail?.prompt?.primary ? (
              <pre className="dc-ag-prompt">{detail.prompt.primary}</pre>
            ) : (
              <div className="dc-ag-prompt-empty">
                该 agent 无 system prompt (纯调度 / 纯 Python).
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
