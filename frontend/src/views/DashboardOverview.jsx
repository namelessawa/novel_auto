import React, { useEffect, useMemo, useState } from 'react'
import './DashboardOverview.css'
import {
  fetchAgents,
  fetchTickNarratives,
  fetchTickOpenLoops,
} from '../services/api'

// v2.46 — 直译自 claude.ai/design 项目「小说自动化前端页面」中
// Novel Auto Dashboard.dc.html「总览」段。三段:
//   § 01  Hero — ACTIVE NOVEL kicker + h1 + 4 stats + Narrator excerpt + world snapshot
//   § 02  智能体 grid — 10 agent + 1 KG sync placeholder
//   § 03  伏笔池 — top-N open loops
//
// 与设计稿的差异 (有意保留, 都是为了"接真后端"):
//   - 4 stats 用 fetchStats + fetchTickStatus, 没有的字段显示 "—"
//   - World snapshot 只填后端确实暴露的字段 (time/weather/location), 余 placeholder
//   - 6 卡的 "实时指标" + 60 tick mini bar + KG mini SVG 都暂未接 — 后端无聚合数据
//   - 11 cell agent grid 改用 fetchAgents 返回的真实列表 (不足 11 → 占位补齐)
//   - Narrator excerpt 调 fetchTickNarratives(limit=1, endTick=0), 价值/幻觉是后端
//     尚未暴露的 per-tick 度量 — 占位 "—" 不假造

const FALLBACK_AGENTS = [
  { num: '00', name: 'Orchestrator', cn: '编排', freq: '每 tick', tier: '纯调度', desc: '协调 7 阶段流程, 末尾 KG 同步 + 原子持久化', running: true },
  { num: '01', name: 'WorldSimulator', cn: '世界模拟', freq: '每 tick', tier: 'small LLM', desc: '推进时间 / 天气 / 社会演化, 稳态字段反清空保护', running: true },
  { num: '02', name: 'EventInjector', cn: '事件注入', freq: '3-5 tick', tier: 'medium', desc: '内生 / 外生 / 戏剧事件 + state_patches 权威补丁', running: false },
  { num: '03', name: 'CharacterAgent', cn: '角色代理 × N', freq: '每 tick', tier: 'A=strong B=medium', desc: '基于 known_facts 决策, cooldown + model_tier_override', running: true },
  { num: '04', name: 'ActionResolver', cn: '行动裁决', freq: '每 tick', tier: '纯逻辑', desc: '解析独占行动冲突, 落 state 转移字段', running: true },
  { num: '05', name: 'Narrator', cn: '叙述者 · 品味瓶颈', freq: '每 tick', tier: 'strongest → medium', desc: '选材 + 写作, 可主动沉默, 反 reasoning 泄漏, 标题锚定', running: true, narrator: true },
  { num: '06', name: 'Showrunner', cn: '制片', freq: '每 5 tick', tier: 'medium', desc: '节奏曲线 + 冷线索 + 弧线监控, sideline 推荐', running: false },
  { num: '07', name: 'MemoryCompressor', cn: '记忆压缩', freq: '每 50 tick', tier: 'small', desc: 'L0 → L1 → L2 → L3 分层压缩, 远古事件传说化失真', running: false },
  { num: '08', name: 'ConsistencyGuardian', cn: '一致性守卫', freq: '每 30 tick', tier: 'continuity_v2', desc: '5 类矛盾扫描 + 幻觉率统计, 超阈值写降级', running: false },
  { num: '09', name: 'NoveltyCritic', cn: '新颖性评论', freq: '每 20 tick', tier: 'small', desc: '重复模式检测, 反馈 Narrator 调整风格', running: false },
  { num: '10', name: 'SectionCloser', cn: '切节判定', freq: 'tick 后', tier: 'medium', desc: '判定切节; words ≥ upper 不调 LLM 直接切', running: false },
]

const PLACEHOLDER_AGENT = {
  num: '+',
  name: 'KG Sync',
  cn: 'tick 末尾纯 Python 同步',
  freq: '每 tick',
  tier: '无 LLM',
  desc: 'CharacterProfile / WorldState → Entity + Relation',
  empty: true,
}

function statusFromFreq(running, num) {
  if (num === '03') return 'RUNNING × 6'
  if (running) return 'RUNNING'
  return null
}

function classifyLoop(loop) {
  // 兼容后端 OpenLoop schema 的几种命名:
  //   * Showrunner 出的 loop: { id, summary, importance, age_ticks, priority? }
  //   * 旧 schema: { loop_id, description, tick_age }
  // importance ≥ 7 / priority === 'high' 视作 HIGH.
  const title =
    loop.title ||
    loop.summary ||
    loop.description ||
    loop.text ||
    loop.label ||
    '未命名伏笔'
  const body =
    loop.detail ||
    loop.body ||
    loop.note ||
    loop.context ||
    loop.summary_long ||
    ''
  const importance =
    typeof loop.importance === 'number' ? loop.importance : null
  const priority = String(
    loop.priority || (importance !== null && importance >= 7 ? 'high' : 'medium'),
  ).toLowerCase()
  const age = loop.age_ticks ?? loop.tick_age ?? loop.age ?? null
  const origin = loop.origin || loop.source || null
  const refs = loop.refs ?? loop.ref_count ?? loop.refs_count ?? null
  const protectedFlag = loop.protected || loop.is_protected || false
  return { title, body, priority, age, origin, refs, protectedFlag }
}

function formatTickRange(currentTick) {
  if (typeof currentTick !== 'number') return '—'
  return currentTick.toLocaleString()
}

function formatNum(n) {
  if (typeof n !== 'number') return '—'
  return n.toLocaleString()
}

function formatRuntime(ms) {
  if (typeof ms !== 'number' || ms <= 0) return '—'
  const sec = Math.floor(ms / 1000)
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  if (d > 0) return `${d}d ${h}h`
  const m = Math.floor((sec % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

export default function DashboardOverview({
  novel,
  tickStatus,
  stats,
  generating,
  statusText,
  progressPct,
  onJumpReader,
  onJumpAgents,
  onJumpKg,
}) {
  const [narrative, setNarrative] = useState(null)
  const [openLoops, setOpenLoops] = useState([])
  const [agents, setAgents] = useState(FALLBACK_AGENTS)

  // 拉最近一条 narrator 输出 + top-K 伏笔 + agent 注册表
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const r = await fetchTickNarratives({ limit: 3 })
        if (cancelled) return
        const last = (r?.narratives || []).slice(-1)[0] || null
        setNarrative(last)
      } catch {
        if (!cancelled) setNarrative(null)
      }
      try {
        const r = await fetchTickOpenLoops(8)
        if (cancelled) return
        const arr = Array.isArray(r) ? r : r?.open_loops || r?.loops || []
        setOpenLoops(arr.slice(0, 5))
      } catch {
        if (!cancelled) setOpenLoops([])
      }
      try {
        const r = await fetchAgents()
        if (cancelled) return
        // 仅当 API 真的回了一组 agent 才覆盖, 否则保留视觉完整的 fallback
        if (Array.isArray(r?.agents) && r.agents.length > 0) {
          const mapped = r.agents.map((a, i) => {
            const fb = FALLBACK_AGENTS[i] || {}
            return {
              num: a.num || a.id || fb.num || String(i).padStart(2, '0'),
              name: a.name || fb.name || a.id || `Agent ${i}`,
              cn: a.cn || a.cn_name || fb.cn || '',
              freq: a.frequency || a.freq || fb.freq || '',
              tier: a.tier || a.model_tier || fb.tier || '',
              desc: a.description || a.desc || fb.desc || '',
              running: a.running ?? fb.running ?? false,
              narrator: (a.name || fb.name) === 'Narrator',
            }
          })
          setAgents(mapped)
        }
      } catch {
        // 保留 fallback
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [novel?.id, tickStatus?.current_tick])

  // —— 派生值 ——
  const novelTitle = novel?.title || novel?.id || '未选择作品'
  const novelId = novel?.id || ''
  const sectionNo =
    tickStatus?.current_section ??
    tickStatus?.section_index ??
    stats?.total_sections ??
    null
  const currentTick =
    typeof tickStatus?.current_tick === 'number'
      ? tickStatus.current_tick
      : null
  const totalWords = stats?.total_words ?? null
  const charCount = tickStatus?.character_count ?? null
  const runtimeMs = stats?.runtime_ms ?? stats?.uptime_ms ?? null
  const running = Boolean(tickStatus && !tickStatus.is_paused)

  const sectionLabel = useMemo(() => {
    if (typeof sectionNo === 'number' && sectionNo > 0) {
      return `第 ${sectionNo} 节`
    }
    return '总览'
  }, [sectionNo])

  // World snapshot — 后端在 tickStatus 里给的 world_state 子集 (不是所有部署都有)
  const ws = tickStatus?.world_state || tickStatus?.world || {}
  const snapshot = {
    时间: ws.time || ws.calendar || ws.datetime || null,
    天气: ws.weather || null,
    地理: ws.location || ws.place || ws.region || null,
    社会: ws.social || ws.regime || ws.society || null,
  }
  const hasAnySnapshot = Object.values(snapshot).some(Boolean)

  // —— Section § 03 — Open loops grid 拼接 (设计是 4 列, 第 12 格空着) ——
  const agentCells = useMemo(() => {
    const filled = agents.slice(0, 11)
    while (filled.length < 11) filled.push(null)
    return [...filled, PLACEHOLDER_AGENT]
  }, [agents])

  return (
    <div className="na-d-overview na-d-fade">
      {/* —— 进度小条 (只在 generating 时出现) —— */}
      {generating && (
        <div className="na-d-genbar">
          <span className="na-d-genbar-spin" />
          <span className="na-d-genbar-msg">
            {statusText || '正在生成中…'}
          </span>
          <span className="na-d-genbar-pct">{progressPct ?? 0}%</span>
          <div className="na-d-genbar-track">
            <div
              className="na-d-genbar-fill"
              style={{ width: `${Math.min(100, progressPct ?? 0)}%` }}
            />
          </div>
        </div>
      )}

      {/* ━━━━━━━━━━━━━━━━━━━━ § 01 · HERO ━━━━━━━━━━━━━━━━━━━━ */}
      <section className="na-d-hero">
        <div className="na-d-hero-left">
          <div className="na-d-kicker">
            <span className="na-d-kicker-bar" />
            <span className="na-d-kicker-text">ACTIVE NOVEL</span>
            {novelId && (
              <span className="na-d-kicker-aux">· novel_id = {novelId}</span>
            )}
          </div>

          <div className="na-d-hero-title-group">
            <button
              type="button"
              className="na-d-hero-title"
              onClick={onJumpReader}
              title="跳转至 连续阅读"
            >
              <span>{novelTitle}</span>
              <span className="na-d-hero-title-dot">·</span>
              <span>{sectionLabel}</span>
            </button>
            <div className="na-d-hero-stats">
              <span>
                <span className="na-d-stat-num">
                  {formatTickRange(currentTick)}
                </span>{' '}
                <span className="na-d-stat-label">tick</span>
              </span>
              <span>
                <span className="na-d-stat-num">{formatNum(totalWords)}</span>{' '}
                <span className="na-d-stat-label">字</span>
              </span>
              <span>
                <span className="na-d-stat-num">{formatRuntime(runtimeMs)}</span>{' '}
                <span className="na-d-stat-label">运行</span>
              </span>
              <span>
                <span className="na-d-stat-num">{charCount ?? '—'}</span>{' '}
                <span className="na-d-stat-label">角色</span>
              </span>
            </div>
          </div>

          {/* —— Narrator excerpt card —— */}
          {narrative ? (
            <div
              className="na-d-narr"
              onClick={onJumpReader}
              title="阅读全文"
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') onJumpReader?.()
              }}
            >
              <div className="na-d-narr-head">
                <div className="na-d-narr-head-l">
                  <span className="na-d-narr-tag">NARRATOR</span>
                  <span className="na-d-narr-meta">
                    tick{' '}
                    <span className="na-d-narr-meta-num">
                      {formatTickRange(narrative.tick ?? currentTick)}
                    </span>
                    {typeof narrative.char_count === 'number' && (
                      <>
                        {' '}· <span className="na-d-narr-meta-num">
                          {narrative.char_count.toLocaleString()}
                        </span>{' '}
                        字
                      </>
                    )}
                  </span>
                </div>
                <span className="na-d-narr-meta">
                  价值 <span className="na-d-narr-meta-num">—</span> · 幻觉{' '}
                  <span className="na-d-narr-meta-num">—</span>
                </span>
              </div>
              <p
                className={`na-d-narr-body ${
                  (narrative.text || '').length > 360 ? 'is-clipped' : ''
                }`}
              >
                {narrative.text || '（无正文）'}
              </p>
              <div className="na-d-narr-foot">
                <span>章节 · {sectionLabel}</span>
                <span>·</span>
                <span>tick · {formatTickRange(narrative.tick ?? currentTick)}</span>
                <span className="na-d-narr-cta">阅读全文 →</span>
              </div>
            </div>
          ) : (
            <div className="na-d-narr">
              <div className="na-d-narr-empty">
                尚无叙述者输出 — 推进 tick 后 Narrator 会在此呈现最近一次的写作片段。
              </div>
            </div>
          )}
        </div>

        {/* —— Right column · World snapshot mini —— */}
        <div className="na-d-hero-right">
          <div className="na-d-kicker">
            <span
              className="na-d-kicker-bar"
              style={{ background: 'var(--na-d-text)' }}
            />
            <span
              className="na-d-kicker-text"
              style={{ color: 'var(--na-d-text)' }}
            >
              WORLD SNAPSHOT
            </span>
          </div>
          <div className="na-d-snapshot">
            <div className="na-d-snap-grid">
              {Object.entries(snapshot).map(([k, v]) => (
                <div key={k}>
                  <div className="na-d-snap-k">{k}</div>
                  <div className="na-d-snap-v">{v || '—'}</div>
                </div>
              ))}
            </div>
            <div className="na-d-snap-sep" />
            <div>
              <div className="na-d-snap-k">当前 tick</div>
              <div className="na-d-snap-v">
                {currentTick !== null ? `tick ${formatTickRange(currentTick)}` : '尚未推进'}
                {' · '}
                {running ? '运行中' : '已暂停'}
              </div>
            </div>
            {!hasAnySnapshot && (
              <div className="na-d-snap-sep" />
            )}
            {!hasAnySnapshot && (
              <div
                style={{
                  font: "400 11px/1.5 'Inter', sans-serif",
                  color: 'var(--na-d-text3)',
                }}
              >
                世界快照字段尚未在 tickStatus 暴露 — 待后端 /api/tick/status 扩展.
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ━━━━━━━━━━━━━━━━━━━━ § 02 · 智能体 grid ━━━━━━━━━━━━━━━━━━━━ */}
      <section className="na-d-agents">
        <div className="na-d-sec-head">
          <span className="na-d-sec-num">§ 02</span>
          <button
            type="button"
            className="na-d-sec-title"
            onClick={onJumpAgents}
            title="跳转至 Agent 上下文"
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            智能体
          </button>
          <span className="na-d-sec-sub">
            10 LLM agent + 1 调度器, 7 阶段 tick 循环
          </span>
          <span className="na-d-sec-meta">
            {agents.filter((a) => a?.running).length} ACTIVE
          </span>
        </div>

        <div className="na-d-agents-grid">
          {agentCells.map((a, i) => {
            if (!a) {
              return (
                <div
                  key={`empty-${i}`}
                  className="na-d-agent na-d-agent-empty"
                  aria-hidden="true"
                />
              )
            }
            const statusText = a.empty
              ? 'PURE PY'
              : statusFromFreq(a.running, a.num) || a.freq?.toUpperCase()
            return (
              <div
                key={`${a.num}-${a.name}`}
                className={[
                  'na-d-agent',
                  a.narrator ? 'na-d-agent-narrator' : '',
                  a.empty ? 'na-d-agent-empty' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                onClick={a.empty ? undefined : onJumpAgents}
                title={a.empty ? undefined : '跳转至 Agent 上下文'}
                role={a.empty ? undefined : 'button'}
              >
                <div className="na-d-agent-head">
                  <span className="na-d-agent-num">{a.num}</span>
                  <span className="na-d-agent-status">
                    {!a.empty && (
                      <span
                        className={`na-d-agent-dot ${a.running ? '' : 'is-idle'}`}
                      />
                    )}
                    <span
                      className={`na-d-agent-status-text ${
                        a.running || a.empty ? 'is-active' : 'is-idle'
                      }`}
                      style={
                        a.empty
                          ? { color: 'var(--na-d-text4)' }
                          : undefined
                      }
                    >
                      {statusText || 'IDLE'}
                    </span>
                  </span>
                </div>
                <div>
                  <div className="na-d-agent-name">{a.name}</div>
                  <div className="na-d-agent-cn">{a.cn}</div>
                </div>
                <div className="na-d-agent-tags">
                  <span>{a.freq}</span>
                  <span className="na-d-agent-tag-sep">·</span>
                  <span>{a.tier}</span>
                </div>
                <div className="na-d-agent-desc">{a.desc}</div>
              </div>
            )
          })}
        </div>
      </section>

      {/* ━━━━━━━━━━━━━━━━━━━━ § 03 · 伏笔池 ━━━━━━━━━━━━━━━━━━━━ */}
      <section className="na-d-loops">
        <div className="na-d-sec-head">
          <span className="na-d-sec-num">§ 03</span>
          <h2 className="na-d-sec-title">伏笔池</h2>
          <span className="na-d-sec-sub">Showrunner 维护 ≥ 3 开放</span>
          <span className="na-d-sec-meta">
            {openLoops.length} OPEN
          </span>
        </div>

        {openLoops.length === 0 ? (
          <div className="na-d-loops-empty">
            当前作品没有活跃伏笔 — Showrunner 会在 OpenLoop 池 &lt; 3 时主动补线索。
          </div>
        ) : (
          <div className="na-d-loops-list">
            {openLoops.map((raw, i) => {
              const l = classifyLoop(raw)
              const high = l.priority === 'high'
              return (
                <div
                  key={l.origin || l.title + i}
                  className={`na-d-loop ${high ? 'is-high' : ''}`}
                >
                  <div className="na-d-loop-row">
                    <div className="na-d-loop-left">
                      <span className="na-d-loop-title">{l.title}</span>
                      <span
                        className={`na-d-loop-pri ${high ? 'is-high' : ''}`}
                      >
                        {high ? 'HIGH' : 'MEDIUM'}
                      </span>
                    </div>
                    {l.age !== null && (
                      <span className="na-d-loop-age">{l.age} tick</span>
                    )}
                  </div>
                  {l.body && <div className="na-d-loop-body">{l.body}</div>}
                  <div className="na-d-loop-meta">
                    {l.origin && <span>origin = {l.origin}</span>}
                    {l.refs !== null && <span>refs × {l.refs}</span>}
                    {l.protectedFlag && (
                      <span className="na-d-loop-meta-red">protected</span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
