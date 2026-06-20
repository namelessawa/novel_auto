import React, { useMemo } from 'react'

// v2.47 — § 02 智能体 grid (11 + 1 placeholder).
// 拿后端 fetchAgents() 返回的列表; 不足 11 时用 FALLBACK 补齐.

const FALLBACK = [
  { id: 'orchestrator', n: '00', name: 'Orchestrator', cn: '编排', freq: '每 tick', tier: '纯调度', desc: '协调 7 阶段流程, 末尾 KG 同步 + 原子持久化' },
  { id: 'world_simulator', n: '01', name: 'WorldSimulator', cn: '世界模拟', freq: '每 tick', tier: 'small LLM', desc: '推进时间 / 天气 / 社会演化, 稳态字段反清空保护' },
  { id: 'event_injector', n: '02', name: 'EventInjector', cn: '事件注入', freq: '3-5 tick', tier: 'medium', desc: '内生 / 外生 / 戏剧事件 + state_patches 权威补丁' },
  { id: 'character_agent', n: '03', name: 'CharacterAgent', cn: '角色代理 × N', freq: '每 tick', tier: 'A=strong B=medium', desc: '基于 known_facts 决策, cooldown + model_tier_override' },
  { id: 'action_resolver', n: '04', name: 'ActionResolver', cn: '行动裁决', freq: '每 tick', tier: '纯逻辑', desc: '解析独占行动冲突, 落 state 转移字段' },
  { id: 'narrator_agent', n: '05', name: 'Narrator', cn: '叙述者 · 品味瓶颈', freq: '每 tick', tier: 'strongest → medium', desc: '选材 + 写作, 可主动沉默, 反 reasoning 泄漏, 标题锚定', narrator: true },
  { id: 'showrunner', n: '06', name: 'Showrunner', cn: '制片', freq: '每 5 tick', tier: 'medium', desc: '节奏曲线 + 冷线索 + 弧线监控, sideline 推荐' },
  { id: 'memory_compressor', n: '07', name: 'MemoryCompressor', cn: '记忆压缩', freq: '每 50 tick', tier: 'small', desc: 'L0 → L1 → L2 → L3 分层压缩, 远古事件传说化失真' },
  { id: 'consistency_guardian', n: '08', name: 'ConsistencyGuardian', cn: '一致性守卫', freq: '每 30 tick', tier: 'continuity_v2', desc: '5 类矛盾扫描 + 幻觉率统计, 超阈值写降级' },
  { id: 'novelty_critic', n: '09', name: 'NoveltyCritic', cn: '新颖性评论', freq: '每 20 tick', tier: 'small', desc: '重复模式检测, 反馈 Narrator 调整风格' },
  { id: 'section_closer', n: '10', name: 'SectionCloser', cn: '切节判定', freq: 'tick 后', tier: 'medium', desc: '判定切节; words ≥ upper 不调 LLM 直接切' },
]

const PLACEHOLDER = {
  empty: true,
  n: '+',
  name: 'KG Sync',
  cn: 'tick 末尾纯 Python 同步',
  freq: '每 tick',
  tier: '无 LLM',
  desc: 'CharacterProfile / WorldState → Entity + Relation',
}

function mergeAgents(serverAgents) {
  if (!Array.isArray(serverAgents) || serverAgents.length === 0) return FALLBACK.slice()
  // 按 id 把后端返回字段合到 FALLBACK 默认上 — 后端只给元数据 (cn_name / cadence / llm_tier),
  // 描述还是用 FALLBACK 的, 不丢可读性.
  const map = new Map(serverAgents.map((a) => [a.id || a.name, a]))
  return FALLBACK.map((fb) => {
    const a = map.get(fb.id) || map.get(fb.name) || null
    if (!a) return fb
    return {
      ...fb,
      name: a.name || a.cn_name || fb.name,
      cn: a.cn || fb.cn,
      freq: a.cadence || fb.freq,
      tier: a.llm_tier || fb.tier,
      desc: a.role || a.description || fb.desc,
    }
  })
}

// 简化: cadence 含"每 tick"或包含特定关键字 → running.
function isRunning(a, currentTick) {
  if (!a) return false
  if (a.empty) return false
  if (typeof currentTick !== 'number') return /每\s*tick/.test(a.freq || '')
  // 解析 "每 N tick"
  const m = /每\s*(\d+)\s*tick/.exec(a.freq || '')
  if (!m) return /每\s*tick/.test(a.freq || '')
  const n = Number(m[1])
  return n > 0 && currentTick % n === 0
}

export default function AgentsSection({ agents: serverAgents, currentTick, onJumpAgent }) {
  const merged = useMemo(() => mergeAgents(serverAgents), [serverAgents])
  const cells = useMemo(() => [...merged.slice(0, 11), PLACEHOLDER], [merged])
  const activeCount = merged.filter((a) => isRunning(a, currentTick)).length

  return (
    <section className="dc-ov-section">
      <div className="dc-sec-head">
        <span className="dc-sec-num">§ 02</span>
        <h2
          className="dc-sec-title is-jump"
          onClick={onJumpAgent}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') onJumpAgent?.()
          }}
          title="跳转至 Agent 上下文"
        >
          智能体
        </h2>
        <span className="dc-sec-sub">10 LLM agent + 1 调度器, 7 阶段 tick 循环</span>
        <span className="dc-sec-meta">{activeCount} ACTIVE</span>
      </div>

      <div className="dc-ov-agents-grid">
        {cells.map((a, i) => {
          if (!a) return <div key={`empty-${i}`} className="dc-ov-agent is-empty" aria-hidden="true" />
          const running = isRunning(a, currentTick)
          const status = a.empty
            ? 'PURE PY'
            : running
            ? a.id === 'character_agent'
              ? 'RUNNING × N'
              : a.id === 'narrator_agent'
              ? 'WRITING'
              : 'RUNNING'
            : (a.freq || '').toUpperCase()
          return (
            <div
              key={a.n + a.name}
              className={`dc-ov-agent${a.narrator ? ' is-narrator' : ''}${a.empty ? ' is-empty' : ''}`}
              onClick={a.empty ? undefined : onJumpAgent}
              role={a.empty ? undefined : 'button'}
              tabIndex={a.empty ? undefined : 0}
              onKeyDown={
                a.empty
                  ? undefined
                  : (e) => {
                      if (e.key === 'Enter' || e.key === ' ') onJumpAgent?.()
                    }
              }
              title={a.empty ? undefined : '跳转至 Agent 上下文'}
            >
              <div className="dc-ov-agent-head">
                <span className="dc-ov-agent-num">{a.n}</span>
                <span className="dc-ov-agent-status">
                  {!a.empty && <span className={`dc-ov-agent-dot ${running ? '' : 'is-idle'}`} />}
                  <span className={`dc-ov-agent-status-text ${running || a.empty ? '' : 'is-idle'}`}>
                    {status}
                  </span>
                </span>
              </div>
              <div>
                <div className="dc-ov-agent-name">{a.name}</div>
                <div className="dc-ov-agent-cn">{a.cn}</div>
              </div>
              <div className="dc-ov-agent-tags">
                <span>{a.freq}</span>
                <span className="dc-ov-agent-tags-sep">·</span>
                <span>{a.tier}</span>
              </div>
              <div className="dc-ov-agent-desc">{a.desc}</div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
