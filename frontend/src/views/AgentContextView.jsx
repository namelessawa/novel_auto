import React, { useEffect, useState } from 'react'
import { fetchAgentDetail, fetchAgents } from '../services/api'
import { showToast } from '../utils/toast'

const TIER_COLOR = {
  null: 'var(--text-muted)',
  small: 'var(--accent-emerald)',
  medium: 'var(--accent-blue)',
  strong: 'var(--accent-purple)',
  strongest: 'var(--accent-rose)',
}

function tierColor(tier) {
  if (!tier) return 'var(--text-muted)'
  const lower = tier.toLowerCase()
  if (lower.includes('strongest')) return 'var(--accent-rose)'
  if (lower.includes('strong')) return 'var(--accent-purple)'
  if (lower.includes('medium')) return 'var(--accent-blue)'
  if (lower.includes('small')) return 'var(--accent-emerald)'
  return 'var(--accent-cyan)'
}

const AGENT_ICONS = {
  orchestrator: 'fa-gauge-high',
  world_simulator: 'fa-globe',
  event_injector: 'fa-bolt',
  character_agent: 'fa-user-secret',
  action_resolver: 'fa-scale-balanced',
  narrator_agent: 'fa-feather-pointed',
  showrunner: 'fa-clapperboard',
  memory_compressor: 'fa-compress',
  consistency_guardian: 'fa-shield-halved',
  novelty_critic: 'fa-magnifying-glass-chart',
}

export default function AgentContextView() {
  const [agents, setAgents] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    load()
  }, [])

  const load = async () => {
    setLoading(true)
    try {
      const data = await fetchAgents()
      const list = data.agents || []
      setAgents(list)
      if (list.length > 0 && !selectedId) {
        selectAgent(list[0].id)
      }
    } catch (err) {
      showToast('加载 agent 注册表失败:' + err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const selectAgent = async (id) => {
    setSelectedId(id)
    setDetailLoading(true)
    setDetail(null)
    try {
      const d = await fetchAgentDetail(id)
      setDetail(d)
    } catch (err) {
      showToast('加载 agent 详情失败:' + err.message, 'error')
    } finally {
      setDetailLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="card">
        <div className="generating-indicator">
          <span className="loading-spinner"></span>
          <span>读取 agent 注册表中…</span>
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', gap: 16, height: '100%', minHeight: 0 }}>
      {/* 左侧:agent 列表 */}
      <div
        style={{
          width: 280,
          minWidth: 280,
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
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span>Agent 列表</span>
          <span style={{ textTransform: 'none' }}>{agents.length}</span>
        </div>
        <div style={{ padding: 8, overflowY: 'auto', flex: 1 }}>
          {agents.map((a) => {
            const icon = AGENT_ICONS[a.id] || 'fa-microchip'
            const isActive = selectedId === a.id
            return (
              <button
                key={a.id}
                className={`nav-item ${isActive ? 'active' : ''}`}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'stretch',
                  gap: 4,
                  padding: '10px 12px',
                  textAlign: 'left',
                  marginBottom: 4,
                }}
                onClick={() => selectAgent(a.id)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <i
                    className={`fas ${icon}`}
                    style={{
                      color: tierColor(a.llm_tier),
                      width: 16,
                      textAlign: 'center',
                    }}
                  ></i>
                  <span style={{ flex: 1, fontWeight: 600, fontSize: 13 }}>
                    {a.cn_name}
                  </span>
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: 'var(--text-muted)',
                    display: 'flex',
                    gap: 6,
                    paddingLeft: 24,
                  }}
                >
                  <span>{a.cadence}</span>
                  {a.llm_tier && (
                    <>
                      <span>·</span>
                      <span style={{ color: tierColor(a.llm_tier) }}>
                        {a.llm_tier}
                      </span>
                    </>
                  )}
                  {!a.has_prompt && (
                    <>
                      <span>·</span>
                      <span>无 prompt</span>
                    </>
                  )}
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* 右侧:agent 详情 */}
      <div style={{ flex: 1, minWidth: 0, overflowY: 'auto' }}>
        {detailLoading && (
          <div className="card">
            <div className="generating-indicator">
              <span className="loading-spinner"></span>
              <span>读取上下文中…</span>
            </div>
          </div>
        )}
        {!detailLoading && detail && <AgentDetail detail={detail} />}
        {!detailLoading && !detail && (
          <div className="empty-state">
            <i className="fas fa-arrow-left"></i>
            <p>从左侧选择一个 agent 查看完整上下文</p>
          </div>
        )}
      </div>
    </div>
  )
}

function AgentDetail({ detail }) {
  const tColor = tierColor(detail.llm_tier)
  return (
    <div>
      {/* 顶部元信息 */}
      <div className="card">
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 12,
            marginBottom: 16,
          }}
        >
          <i
            className={`fas ${AGENT_ICONS[detail.id] || 'fa-microchip'}`}
            style={{
              color: tColor,
              fontSize: 28,
              marginTop: 4,
              width: 32,
              textAlign: 'center',
            }}
          ></i>
          <div style={{ flex: 1 }}>
            <h2
              style={{
                margin: 0,
                fontSize: 20,
                fontWeight: 700,
              }}
            >
              {detail.cn_name}
            </h2>
            <div
              style={{
                marginTop: 4,
                fontSize: 12,
                color: 'var(--text-muted)',
                fontFamily: 'JetBrains Mono, Cascadia Code, monospace',
              }}
            >
              {detail.module_path || detail.id}
            </div>
          </div>
        </div>

        <div
          style={{
            display: 'flex',
            gap: 8,
            flexWrap: 'wrap',
            marginBottom: 12,
          }}
        >
          <span className="badge badge-purple">{detail.cadence}</span>
          <span
            className="badge"
            style={{
              background: `${tColor}26`,
              color: tColor,
            }}
          >
            <i className="fas fa-microchip" style={{ marginRight: 4 }}></i>
            {detail.llm_tier || '无 LLM(纯逻辑)'}
          </span>
          {detail.last_invoked ? (
            <span
              className="badge"
              style={{
                background: 'rgba(16, 185, 129, 0.15)',
                color: 'var(--accent-emerald)',
              }}
            >
              <i className="fas fa-clock" style={{ marginRight: 4 }}></i>
              最近调用: tick {detail.last_invoked.tick}
            </span>
          ) : (
            <span
              className="badge"
              style={{
                background: 'rgba(148, 163, 184, 0.15)',
                color: 'var(--text-muted)',
              }}
            >
              <i className="fas fa-clock" style={{ marginRight: 4 }}></i>
              尚未调用
            </span>
          )}
        </div>

        <div
          style={{
            fontSize: 14,
            lineHeight: 1.7,
            color: 'var(--text-secondary)',
          }}
        >
          {detail.role}
        </div>
      </div>

      {/* 输入 */}
      <div className="card">
        <div className="card-title">
          <i className="fas fa-arrow-down-to-line"></i> 输入上下文
          <span className="badge badge-purple" style={{ marginLeft: 8 }}>
            {detail.inputs?.length || 0} 项
          </span>
        </div>
        {(detail.inputs || []).map((src, i) => (
          <div
            key={i}
            className="entity-item"
            style={{
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
              background: 'rgba(139, 92, 246, 0.06)',
            }}
          >
            <span
              style={{
                color: 'var(--accent-purple)',
                fontWeight: 600,
                fontSize: 12,
                minWidth: 24,
              }}
            >
              {String(i + 1).padStart(2, '0')}
            </span>
            <span style={{ flex: 1 }}>{src}</span>
          </div>
        ))}
      </div>

      {/* 输出 */}
      <div className="card">
        <div className="card-title">
          <i className="fas fa-arrow-up-from-bracket"></i> 产出
          <span className="badge badge-emerald" style={{ marginLeft: 8 }}>
            {detail.outputs?.length || 0} 项
          </span>
        </div>
        {(detail.outputs || []).map((out, i) => (
          <div
            key={i}
            className="entity-item"
            style={{
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
              background: 'rgba(16, 185, 129, 0.06)',
              borderLeft: '2px solid var(--accent-emerald)',
            }}
          >
            <span
              style={{
                color: 'var(--accent-emerald)',
                fontWeight: 600,
                fontSize: 12,
                minWidth: 24,
              }}
            >
              {String(i + 1).padStart(2, '0')}
            </span>
            <span style={{ flex: 1 }}>{out}</span>
          </div>
        ))}
      </div>

      {/* 最近调用 */}
      {detail.last_invoked && (
        <div className="card">
          <div className="card-title">
            <i className="fas fa-clock-rotate-left"></i> 最近调用
          </div>
          <div className="grid-2" style={{ marginBottom: 8 }}>
            <div className="entity-item">
              <span className="entity-name" style={{ color: 'var(--accent-cyan)' }}>
                Tick
              </span>{' '}
              #{detail.last_invoked.tick}
            </div>
            <div className="entity-item">
              <span className="entity-name" style={{ color: 'var(--accent-cyan)' }}>
                世界时间
              </span>{' '}
              {detail.last_invoked.world_time}
            </div>
          </div>
          {detail.last_invoked.summary && (
            <div className="event-item">
              <div className="event-chapter">状态变化摘要</div>
              {detail.last_invoked.summary}
            </div>
          )}
          {detail.last_invoked.narrator_produced && (
            <div
              className="badge badge-purple"
              style={{ marginTop: 8, display: 'inline-block' }}
            >
              <i className="fas fa-feather" style={{ marginRight: 4 }}></i>
              该 tick Narrator 产出叙述
            </div>
          )}
        </div>
      )}

      {/* 实时上下文(已喂进 agent 的数据) */}
      <LiveContextBlock ctx={detail.live_context} />

      {/* System Prompt */}
      {detail.prompt ? (
        <>
          <div className="card">
            <div className="card-title">
              <i className="fas fa-scroll"></i> System Prompt
              <span
                className="badge badge-purple"
                style={{ marginLeft: 8 }}
              >
                {detail.prompt.primary?.length || 0} 字符
              </span>
            </div>
            <PromptBlock text={detail.prompt.primary} />
          </div>

          {detail.prompt.extras &&
            Object.entries(detail.prompt.extras).map(([name, text]) => (
              <div className="card" key={name}>
                <div className="card-title">
                  <i className="fas fa-scroll"></i> 附加 Prompt:{' '}
                  <code style={{ color: 'var(--accent-amber)', marginLeft: 4 }}>
                    {name}
                  </code>
                  <span
                    className="badge badge-purple"
                    style={{ marginLeft: 8 }}
                  >
                    {text.length} 字符
                  </span>
                </div>
                <PromptBlock text={text} />
              </div>
            ))}
        </>
      ) : (
        <div className="card">
          <div className="card-title">
            <i className="fas fa-scroll"></i> System Prompt
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            该 agent 无 LLM 调用,无 prompt(纯 Python 逻辑)
          </div>
        </div>
      )}
    </div>
  )
}

function LiveContextBlock({ ctx }) {
  if (!ctx) return null
  if (!ctx.available) {
    return (
      <div className="card">
        <div className="card-title">
          <i className="fas fa-database"></i> 实时上下文
        </div>
        <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          {ctx.reason || '不可用'}
        </div>
      </div>
    )
  }
  // 拆出 meta 字段,其余作为 JSON 渲染
  const { available, tick_when_sampled, ...rest } = ctx
  const sections = Object.entries(rest)
  return (
    <div className="card">
      <div className="card-title">
        <i className="fas fa-database"></i> 实时上下文(下一次 tick 该 agent 会读到的数据)
        <span className="badge badge-emerald" style={{ marginLeft: 8 }}>
          采样自 tick #{tick_when_sampled ?? '?'}
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {sections.map(([key, value]) => (
          <ContextField key={key} name={key} value={value} />
        ))}
      </div>
    </div>
  )
}

function ContextField({ name, value }) {
  const [collapsed, setCollapsed] = useState(() => {
    // 默认折叠大数组/大对象,但小标量/短数组展开
    if (value == null) return false
    if (Array.isArray(value)) return value.length > 5
    if (typeof value === 'object') return Object.keys(value).length > 5
    return false
  })

  const summary = renderSummary(value)
  const isCollapsible =
    value !== null &&
    typeof value === 'object'

  return (
    <div
      style={{
        background: 'rgba(0, 0, 0, 0.25)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 12px',
          background: 'rgba(255,255,255,0.02)',
          cursor: isCollapsible ? 'pointer' : 'default',
          userSelect: 'none',
          fontSize: 13,
        }}
        onClick={() => isCollapsible && setCollapsed((c) => !c)}
      >
        <code style={{ color: 'var(--accent-amber)', fontWeight: 600 }}>
          {name}
        </code>
        <span style={{ flex: 1, color: 'var(--text-muted)', fontSize: 12 }}>
          {summary}
        </span>
        {isCollapsible && (
          <i
            className={`fas fa-chevron-${collapsed ? 'right' : 'down'}`}
            style={{ fontSize: 11, color: 'var(--text-muted)' }}
          ></i>
        )}
      </div>
      {!collapsed && (
        <div style={{ padding: '8px 12px', fontSize: 12 }}>
          {renderValue(value)}
        </div>
      )}
    </div>
  )
}

function renderSummary(value) {
  if (value === null || value === undefined) return 'null'
  if (typeof value === 'string') {
    return value.length > 40 ? `"${value.slice(0, 40)}…"` : `"${value}"`
  }
  if (typeof value === 'number' || typeof value === 'boolean')
    return String(value)
  if (Array.isArray(value)) return `array (${value.length} 项)`
  if (typeof value === 'object') return `object (${Object.keys(value).length} 键)`
  return String(value)
}

function renderValue(value) {
  if (value === null || value === undefined) {
    return <span style={{ color: 'var(--text-muted)' }}>null</span>
  }
  if (typeof value === 'string') {
    return (
      <pre
        style={{
          margin: 0,
          whiteSpace: 'pre-wrap',
          color: 'var(--accent-emerald)',
          fontFamily:
            'JetBrains Mono, Cascadia Code, Fira Code, Consolas, monospace',
          fontSize: 12,
        }}
      >
        {value}
      </pre>
    )
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return (
      <span style={{ color: 'var(--accent-cyan)', fontFamily: 'monospace' }}>
        {String(value)}
      </span>
    )
  }
  // array or object → JSON pretty
  return (
    <pre
      style={{
        margin: 0,
        whiteSpace: 'pre-wrap',
        maxHeight: 320,
        overflowY: 'auto',
        fontSize: 12,
        lineHeight: 1.5,
        color: 'var(--text-secondary)',
        fontFamily:
          'JetBrains Mono, Cascadia Code, Fira Code, Consolas, monospace',
      }}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function PromptBlock({ text }) {
  const [collapsed, setCollapsed] = useState(false)
  if (!text)
    return (
      <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
        (空 prompt)
      </div>
    )
  return (
    <>
      <button
        className="btn btn-secondary btn-sm"
        onClick={() => setCollapsed((c) => !c)}
        style={{ marginBottom: 8 }}
      >
        <i className={`fas fa-chevron-${collapsed ? 'right' : 'down'}`}></i>{' '}
        {collapsed ? '展开' : '折叠'}
      </button>
      {!collapsed && (
        <pre
          className="output-console"
          style={{
            maxHeight: 480,
            whiteSpace: 'pre-wrap',
            fontSize: 13,
            color: 'var(--text-primary)',
          }}
        >
          {text}
        </pre>
      )}
    </>
  )
}
