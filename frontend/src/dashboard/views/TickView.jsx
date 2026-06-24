import React, { useCallback, useEffect, useState } from 'react'
import {
  addTickOpenLoop,
  closeTickOpenLoop,
  fetchActionPatterns,
  fetchCharacterStates,
  fetchCriticLogStats,
  fetchEventStats,
  fetchHallucinationDiagnostic,
  fetchNoveltyWarnings,
  fetchStyleAnchors,
  fetchTickHistory,
  fetchTickOpenLoops,
} from '../../services/api'
import { showToast } from '../../utils/toast'
import { formatTick } from '../utils'

// v2.47 — § Tick 控制: runtime bar (大数字 + 启动/单步) + 7 阶段流水线 +
// 调度参数 + 最近 tick 日志表.

const STAGES = [
  { num: '01', name: 'WorldSimulator', cn: '世界推演',  match: 'WorldSimulator' },
  { num: '02', name: 'EventInjector',  cn: '事件注入',  match: 'EventInjector' },
  { num: '03', name: 'CharacterAgent', cn: '角色决策',  match: 'CharacterAgent' },
  { num: '04', name: 'ActionResolver', cn: '行动裁决',  match: 'ActionResolver' },
  { num: '05', name: 'Narrator',       cn: '选择性叙述', match: 'NarratorAgent' },
  { num: '06', name: 'Guardian',       cn: '一致性',    match: 'ConsistencyGuardian' },
  { num: '07', name: 'SectionCloser',  cn: '切节 + KG', match: 'SectionCloser' },
]

function classifyStage(name, lastTick) {
  // 用 lastTick.agents_called 判断哪一阶段刚 done.
  if (!lastTick) return 'queued'
  const called = lastTick.agents_called || []
  if (called.includes(name) || called.includes(name.replace('Agent', ''))) return 'done'
  return 'queued'
}

export default function TickView({
  tickStatus,
  stats,
  onToggleRun,
  onStepOne,
  onOpenInject,
}) {
  const [history, setHistory] = useState([])
  // v2.48 — § Diagnostics: 移植 TickDiagnosticsPanel 的 6 个端点 (Guardian / CharStates /
  // EventStats / ActionPatterns / NoveltyWarn / StyleAnchors). settled-load, 任一失败不阻塞.
  const [diag, setDiag] = useState({
    hallucination: null,
    characterStates: [],
    eventStats: null,
    actionPatterns: null,
    noveltyWarnings: [],
    styleAnchors: [],
    criticStats: null,
  })
  const [diagLoading, setDiagLoading] = useState(false)
  const [diagFailures, setDiagFailures] = useState(0)

  // v2.48 — § OpenLoop CRUD (移植 TickControlPanel). opened_tick 由前端 = current_tick+1.
  const [openLoops, setOpenLoops] = useState([])
  const [loopForm, setLoopForm] = useState({
    id: '', description: '', urgency: 5, involved_characters: '',
  })
  const [loopBusy, setLoopBusy] = useState(false)
  const refreshLoops = useCallback(async () => {
    try {
      const r = await fetchTickOpenLoops(20)
      setOpenLoops(r?.loops || [])
    } catch {
      setOpenLoops([])
    }
  }, [])
  useEffect(() => {
    refreshLoops()
  }, [refreshLoops, tickStatus?.current_tick])

  async function handleAddLoop(e) {
    e?.preventDefault?.()
    if (!loopForm.id.trim() || !loopForm.description.trim()) {
      showToast('需要 id 和描述', 'error')
      return
    }
    setLoopBusy(true)
    try {
      const involved = loopForm.involved_characters
        .split(/[,,\s]+/)
        .map((p) => p.trim())
        .filter(Boolean)
      await addTickOpenLoop({
        id: loopForm.id.trim(),
        description: loopForm.description.trim(),
        urgency: Number(loopForm.urgency) || 5,
        involved_characters: involved,
        opened_tick: (tickStatus?.current_tick ?? 0) + 1,
      })
      showToast(`OpenLoop ${loopForm.id} 已添加`, 'success')
      setLoopForm({ id: '', description: '', urgency: 5, involved_characters: '' })
      await refreshLoops()
    } catch (err) {
      showToast('添加失败: ' + (err?.message || ''), 'error')
    } finally {
      setLoopBusy(false)
    }
  }

  async function handleCloseLoop(loopId) {
    if (!loopId) return
    if (!window.confirm(`确认关闭 OpenLoop "${loopId}"? (无法恢复)`)) return
    setLoopBusy(true)
    try {
      await closeTickOpenLoop(loopId)
      showToast(`OpenLoop ${loopId} 已关闭`, 'success')
      await refreshLoops()
    } catch (err) {
      showToast('关闭失败: ' + (err?.message || ''), 'error')
    } finally {
      setLoopBusy(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const r = await fetchTickHistory(20)
        if (!cancelled) setHistory(r?.ticks || [])
      } catch {
        if (!cancelled) setHistory([])
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [tickStatus?.current_tick])

  const refreshDiag = useCallback(async () => {
    setDiagLoading(true)
    const results = await Promise.allSettled([
      fetchHallucinationDiagnostic(),
      fetchCharacterStates(),
      fetchEventStats(50),
      fetchActionPatterns(100),
      fetchNoveltyWarnings(),
      fetchStyleAnchors(20),
      fetchCriticLogStats(),
    ])
    const [hd, cs, es, ap, nw, sa, ck] = results
    setDiag({
      hallucination: hd.status === 'fulfilled' ? hd.value : null,
      characterStates:
        cs.status === 'fulfilled'
          ? cs.value?.character_states || cs.value?.states || []
          : [],
      eventStats: es.status === 'fulfilled' ? es.value : null,
      actionPatterns: ap.status === 'fulfilled' ? ap.value : null,
      noveltyWarnings:
        nw.status === 'fulfilled' ? nw.value?.warnings || [] : [],
      styleAnchors: sa.status === 'fulfilled' ? sa.value?.anchors || [] : [],
      criticStats: ck.status === 'fulfilled' ? ck.value : null,
    })
    setDiagFailures(results.filter((r) => r.status === 'rejected').length)
    setDiagLoading(false)
  }, [])

  useEffect(() => {
    refreshDiag()
  }, [refreshDiag, tickStatus?.current_tick])

  const running = Boolean(tickStatus && !tickStatus.is_paused)
  const currentTick =
    typeof tickStatus?.current_tick === 'number' ? tickStatus.current_tick : 0
  const lastTick = history[0] || null
  const sectionTickRatio =
    typeof tickStatus?.section_tick === 'number'
      ? `${tickStatus.section_tick} / §`
      : '—'

  // 简单聚合平均耗时 + tokens
  const avgDur =
    history.length > 0
      ? (
          history
            .map((r) => r.duration_ms || r.took_ms || 0)
            .filter((v) => v > 0)
            .reduce((a, b) => a + b, 0) / Math.max(1, history.length) / 1000
        ).toFixed(1)
      : '—'
  const avgTokens =
    history.length > 0
      ? Math.round(
          history
            .map((r) => r.tokens_used || r.tokens || 0)
            .reduce((a, b) => a + b, 0) / Math.max(1, history.length),
        )
      : null

  return (
    <div className="dc-view-switch dc-tk-root">
      <div className="dc-sec-head">
        <span className="dc-sec-num">§ Tick</span>
        <h2 className="dc-sec-title">Tick 控制</h2>
        <span className="dc-sec-sub">7 阶段调度器 · tick scheduler</span>
        <span className="dc-sec-meta">{running ? 'RUNNING' : 'PAUSED'}</span>
      </div>

      {/* Runtime bar */}
      <div className="dc-tk-rtbar">
        <div className="dc-tk-rtbar-col">
          <span className="dc-tk-rtbar-kicker">当前 TICK</span>
          <span className="dc-tk-rtbar-num">{formatTick(currentTick)}</span>
        </div>
        <div className="dc-tk-rtbar-sep" />
        <div className="dc-tk-rtbar-stats">
          <div className="dc-tk-rtbar-stat">
            <span className="dc-tk-rtbar-stat-lbl">本节 TICK</span>
            <span className="dc-tk-rtbar-stat-num">{sectionTickRatio}</span>
          </div>
          <div className="dc-tk-rtbar-stat">
            <span className="dc-tk-rtbar-stat-lbl">平均耗时</span>
            <span className="dc-tk-rtbar-stat-num">{avgDur} {avgDur !== '—' && 's'}</span>
          </div>
          <div className="dc-tk-rtbar-stat">
            <span className="dc-tk-rtbar-stat-lbl">TOKENS</span>
            <span className="dc-tk-rtbar-stat-num">
              {avgTokens != null ? (avgTokens >= 1000 ? `${(avgTokens / 1000).toFixed(1)}k` : avgTokens) : '—'}
            </span>
          </div>
        </div>
        <div className="dc-tk-rtbar-actions">
          <button type="button" className="dc-btn" onClick={onToggleRun}>
            {running ? '暂停' : '启动'} 调度
          </button>
          <button type="button" className="dc-btn-ghost" onClick={onStepOne}>
            单步 +1
          </button>
          <button type="button" className="dc-btn-ghost" onClick={onOpenInject}>
            注入事件
          </button>
        </div>
      </div>

      {/* 7-stage pipeline */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        <span className="dc-tk-rtbar-kicker">单 TICK 流水线 · 7 STAGE</span>
        <div className="dc-tk-pipe">
          {STAGES.map((s, i) => {
            const cls = classifyStage(s.match, lastTick)
            const isActive = i === 4 && running // narrator 默认热点
            return (
              <div
                key={s.num}
                className={`dc-tk-pipe-stage ${isActive ? 'is-active' : ''} ${cls === 'queued' ? 'is-queued' : ''}`}
              >
                <div className="dc-tk-pipe-stage-head">
                  <span className="dc-tk-pipe-stage-num">{s.num}</span>
                  <span
                    className={`dc-tk-pipe-stage-dot ${cls === 'queued' ? 'is-queued' : ''} ${isActive ? 'is-running' : ''}`}
                  />
                </div>
                <div className="dc-tk-pipe-stage-name">{s.name}</div>
                <div className="dc-tk-pipe-stage-cn">{s.cn}</div>
                <div className="dc-tk-pipe-stage-status">
                  {isActive ? 'running…' : cls === 'done' ? 'done' : 'queued'}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* v2.48 — § Diagnostics: Guardian + CharStates + EventStats + ActionPatterns +
          NoveltyWarn + StyleAnchors. 移植 TickDiagnosticsPanel 关键面板, 同样的端点. */}
      <DiagnosticsSection
        diag={diag}
        loading={diagLoading}
        failures={diagFailures}
        endpointCount={7}
        onRefresh={refreshDiag}
      />

      {/* v2.48 — § OpenLoop CRUD: 列出 + 添加 + 关闭. 移植 TickControlPanel. */}
      <OpenLoopsSection
        loops={openLoops}
        form={loopForm}
        setForm={setLoopForm}
        onAdd={handleAddLoop}
        onClose={handleCloseLoop}
        busy={loopBusy}
        currentTick={tickStatus?.current_tick ?? 0}
      />

      {/* params + log */}
      <div className="dc-tk-pl-row">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <span className="dc-tk-rtbar-kicker">调度参数</span>
          <div className="dc-tk-params">
            <ParamRow name="tick 间隔" sub="自动推进节流" val={tickStatus?.tick_interval_s ?? '—'} unit="s" />
            <ParamRow name="max_tokens 预算" sub="每 tick 上限" val={tickStatus?.max_tokens_budget ?? '—'} />
            <ParamRow
              name="auto_degrade"
              sub="超预算降级 critic"
              right={
                <span className={`dc-tk-toggle ${tickStatus?.auto_degrade ? 'is-on' : ''}`}>
                  <span className="dc-tk-toggle-knob" />
                </span>
              }
            />
            <ParamRow
              name="narrator_silent_bias"
              sub="沉默倾向"
              val={tickStatus?.narrator_silent_bias != null ? tickStatus.narrator_silent_bias.toFixed(2) : '—'}
            />
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <span className="dc-tk-rtbar-kicker">最近 TICK · 日志</span>
          <div className="dc-tk-log">
            <div className="dc-tk-log-head">
              <span>TICK</span>
              <span>主导阶段</span>
              <span>耗时</span>
              <span>tokens</span>
            </div>
            {history.slice(0, 6).map((r) => (
              <div key={r.tick} className="dc-tk-log-row">
                <span className="dc-tk-log-row-tick">{r.tick}</span>
                <span className="dc-tk-log-row-stage">
                  {(r.agents_called && r.agents_called[r.agents_called.length - 1]) || '—'}
                </span>
                <span className="dc-tk-log-row-num">
                  {r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : '—'}
                </span>
                <span className="dc-tk-log-row-tok">
                  {r.tokens_used ? formatTick(r.tokens_used) : '—'}
                </span>
              </div>
            ))}
            {history.length === 0 && (
              <div className="dc-tk-log-row" style={{ gridTemplateColumns: '1fr' }}>
                <span style={{ color: 'var(--text3)', fontFamily: "'Inter', sans-serif" }}>
                  尚无 tick 历史 — 推进调度后会出现
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function ParamRow({ name, sub, val, unit, right }) {
  return (
    <div className="dc-tk-params-row">
      <div className="dc-tk-params-body">
        <span className="dc-tk-params-name">{name}</span>
        {sub && <span className="dc-tk-params-sub">{sub}</span>}
      </div>
      {right
        ? right
        : (
          <span className="dc-tk-params-val">
            {val} {unit}
          </span>
        )}
    </div>
  )
}

// v2.48 — § Diagnostics 集成 (legacy TickDiagnosticsPanel 6 cards 的 dashboard 版).
// Phase 6-C iter#A — 加 CriticStatsCard (action_distribution + top_codes 概览).
function DiagnosticsSection({ diag, loading, failures, endpointCount = 7, onRefresh }) {
  const {
    hallucination,
    characterStates,
    eventStats,
    actionPatterns,
    noveltyWarnings,
    styleAnchors,
    criticStats,
  } = diag
  return (
    <div className="dc-tk-diag">
      <div className="dc-tk-diag-head">
        <span className="dc-tk-rtbar-kicker">DIAGNOSTICS · 质量门观测</span>
        {failures > 0 && (
          <span className="dc-tk-diag-warn">
            {failures}/{endpointCount} 端点失败 — tick runtime 未注入或后端未启动
          </span>
        )}
        <button
          type="button"
          className="dc-btn-ghost"
          onClick={onRefresh}
          disabled={loading}
          style={{ marginLeft: 'auto' }}
        >
          {loading ? '加载中…' : '刷新'}
        </button>
      </div>

      <GuardianCard data={hallucination} />

      <CriticStatsCard data={criticStats} />

      <div className="dc-tk-diag-grid">
        <CharacterStatesCard states={characterStates} />
        <EventStatsCard data={eventStats} />
        <ActionPatternsCard data={actionPatterns} />
        <NoveltyWarningsCard warnings={noveltyWarnings} />
      </div>

      <StyleAnchorsCard anchors={styleAnchors} />
    </div>
  )
}

// Phase 6-C iter#A — Critic decision aggregate dashboard.
// 数据源: GET /api/tick/critic-log/stats (orchestrator critic_log.jsonl 全扫).
//
// 视觉:
//   header — ticks_scanned · empty_decision rate (clean output 占比)
//   left   — action_distribution: ACCEPT / REVISE / REWRITE / RED_TEAM 4 bar
//   right  — top_codes: 触发 code top-10 list + bar
//
// Empty-state: stats null (端点失败) / ticks_scanned=0 (尚无 critic 行).
function CriticStatsCard({ data }) {
  const stats = data || {}
  const ticksScanned = stats.ticks_scanned ?? 0
  const emptyTicks = stats.empty_decision_ticks ?? 0
  const dist = stats.action_distribution || {}
  const topCodes = stats.top_codes || []

  const distRows = ['ACCEPT', 'REVISE', 'REWRITE', 'RED_TEAM'].map((a) => ({
    action: a,
    count: Number(dist[a] || 0),
  }))
  const distMax = Math.max(1, ...distRows.map((r) => r.count))
  const distTotal = distRows.reduce((acc, r) => acc + r.count, 0)
  const cleanRate =
    ticksScanned > 0 ? `${((emptyTicks / ticksScanned) * 100).toFixed(0)}%` : '—'

  const codeMax = Math.max(1, ...topCodes.map((c) => Number(c.count) || 0))

  return (
    <div className="dc-tk-diag-card is-wide">
      <div className="dc-tk-diag-card-head">
        <span className="dc-tk-diag-card-title">Critic Decisions · 长程聚合</span>
        <span className="dc-tk-diag-card-meta">
          {ticksScanned} tick · {distTotal} action · clean {cleanRate}
        </span>
      </div>
      {ticksScanned === 0 ? (
        <div className="dc-tk-diag-empty">
          critic_log.jsonl 暂无数据 — 推进调度产生 narrative 后会出现
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1.4fr)',
            gap: 18,
          }}
        >
          <div>
            <div
              style={{
                font: "500 11px/1 'JetBrains Mono', monospace",
                color: 'var(--text3)',
                marginBottom: 10,
                letterSpacing: 0.5,
              }}
            >
              ACTION DISTRIBUTION
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {distRows.map((r) => (
                <CriticDistRow
                  key={r.action}
                  action={r.action}
                  count={r.count}
                  max={distMax}
                />
              ))}
            </div>
          </div>
          <div>
            <div
              style={{
                font: "500 11px/1 'JetBrains Mono', monospace",
                color: 'var(--text3)',
                marginBottom: 10,
                letterSpacing: 0.5,
              }}
            >
              TOP CODES · top-10
            </div>
            {topCodes.length === 0 ? (
              <div className="dc-tk-diag-empty">无 surviving code (全 clean)</div>
            ) : (
              <ul className="dc-tk-diag-list">
                {topCodes.map((c, i) => (
                  <CriticCodeRow
                    key={`${c.code}-${i}`}
                    code={c.code}
                    count={Number(c.count) || 0}
                    max={codeMax}
                  />
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function CriticDistRow({ action, count, max }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0
  const accent =
    action === 'ACCEPT' ? 'var(--accent, #5fa8d3)'
      : action === 'REVISE' ? '#d9a55a'
        : action === 'REWRITE' ? '#d9665a'
          : '#a05ad9'
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr 40px', alignItems: 'center', gap: 10 }}>
      <span
        className="is-mono"
        style={{ font: "500 12px/1 'JetBrains Mono', monospace", color: 'var(--text2)' }}
      >
        {action}
      </span>
      <div
        style={{
          height: 10,
          background: 'var(--bg)',
          border: '1px solid var(--border)',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            width: `${pct}%`,
            background: accent,
            opacity: count > 0 ? 0.85 : 0,
            transition: 'width 180ms ease-out',
          }}
        />
      </div>
      <span
        style={{
          font: "500 12px/1 'JetBrains Mono', monospace",
          color: count > 0 ? 'var(--text)' : 'var(--text3)',
          textAlign: 'right',
        }}
      >
        {count}
      </span>
    </div>
  )
}

function CriticCodeRow({ code, count, max }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0
  return (
    <li style={{ display: 'grid', gridTemplateColumns: '100px 1fr 36px', gap: 10 }}>
      <span className="is-mono" style={{ font: "500 12px/1 'JetBrains Mono', monospace" }}>
        {code}
      </span>
      <div
        style={{
          height: 8,
          background: 'var(--bg)',
          border: '1px solid var(--border)',
          position: 'relative',
          overflow: 'hidden',
          alignSelf: 'center',
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            width: `${pct}%`,
            background: 'var(--accent, #5fa8d3)',
            opacity: 0.7,
            transition: 'width 180ms ease-out',
          }}
        />
      </div>
      <span
        className="dc-tk-diag-list-num"
        style={{ textAlign: 'right', alignSelf: 'center' }}
      >
        {count}
      </span>
    </li>
  )
}

function GuardianCard({ data }) {
  const stats = data?.stats || {}
  const agents = Object.entries(stats)
  const autoDegrade = data?.auto_degrade_active
  return (
    <div className="dc-tk-diag-card is-wide">
      <div className="dc-tk-diag-card-head">
        <span className="dc-tk-diag-card-title">Guardian 幻觉率监控</span>
        <span
          className={`dc-tk-diag-pill ${autoDegrade ? 'is-active' : 'is-shadow'}`}
        >
          {autoDegrade ? 'ACTIVE · auto-degrade ON' : 'SHADOW · 仅统计'}
        </span>
      </div>
      {agents.length === 0 ? (
        <div className="dc-tk-diag-empty">
          暂无被 Guardian 建议过降级的 agent
        </div>
      ) : (
        <table className="dc-tk-diag-table">
          <thead>
            <tr>
              <th>agent_id</th>
              <th>命中</th>
              <th>建议降级</th>
              <th>最近 tick</th>
              <th>override</th>
            </tr>
          </thead>
          <tbody>
            {agents.map(([agentId, s]) => (
              <tr key={agentId}>
                <td className="is-mono">{agentId}</td>
                <td>{s.hallucination_hits ?? 0}</td>
                <td>{s.degrade_recommendations ?? 0}</td>
                <td>{s.last_degrade_recommended_tick ?? '—'}</td>
                <td className={s.model_tier_override_active ? 'is-warn' : ''}>
                  {s.model_tier_override_active ? '是' : '否'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function CharacterStatesCard({ states }) {
  return (
    <div className="dc-tk-diag-card">
      <div className="dc-tk-diag-card-head">
        <span className="dc-tk-diag-card-title">CharacterState · {states.length}</span>
      </div>
      {states.length === 0 ? (
        <div className="dc-tk-diag-empty">暂无角色状态</div>
      ) : (
        <table className="dc-tk-diag-table is-compact">
          <thead>
            <tr>
              <th>character</th>
              <th>location</th>
              <th>arc</th>
            </tr>
          </thead>
          <tbody>
            {states.slice(0, 6).map((s) => (
              <tr key={s.character_id}>
                <td className="is-mono">{s.character_id}</td>
                <td>{s.current_location || '—'}</td>
                <td>
                  {s.arc_stage || '—'}
                  {typeof s.arc_progress === 'number'
                    ? ` (${(s.arc_progress * 100).toFixed(0)}%)`
                    : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function EventStatsCard({ data }) {
  if (!data) {
    return (
      <div className="dc-tk-diag-card">
        <div className="dc-tk-diag-card-head">
          <span className="dc-tk-diag-card-title">事件统计</span>
        </div>
        <div className="dc-tk-diag-empty">暂无数据</div>
      </div>
    )
  }
  const byType = data.by_type || {}
  const types = Object.entries(byType).sort((a, b) => b[1] - a[1])
  const totalEvents = types.reduce((acc, [, n]) => acc + (Number(n) || 0), 0)
  const narrationRate =
    typeof data.narration_rate === 'number'
      ? `${(data.narration_rate * 100).toFixed(0)}%`
      : '—'
  return (
    <div className="dc-tk-diag-card">
      <div className="dc-tk-diag-card-head">
        <span className="dc-tk-diag-card-title">事件统计</span>
        <span className="dc-tk-diag-card-meta">
          {data.ticks_sampled ?? 0} tick · {totalEvents} 条 · narrate {narrationRate}
        </span>
      </div>
      {types.length === 0 ? (
        <div className="dc-tk-diag-empty">暂无事件</div>
      ) : (
        <div className="dc-tk-diag-badges">
          {types.map(([t, n]) => (
            <span key={t} className="dc-tk-diag-badge">
              {t} · {n}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function ActionPatternsCard({ data }) {
  const patterns =
    data?.frequent_prefixes || data?.patterns || data?.action_patterns || []
  const totalSampled = data?.total_actions_sampled ?? 0
  return (
    <div className="dc-tk-diag-card">
      <div className="dc-tk-diag-card-head">
        <span className="dc-tk-diag-card-title">行动模式</span>
        <span className="dc-tk-diag-card-meta">
          {patterns.length} 前缀 · {totalSampled} 行动
        </span>
      </div>
      {patterns.length === 0 ? (
        <div className="dc-tk-diag-empty">暂无重复行动模式</div>
      ) : (
        <ul className="dc-tk-diag-list">
          {patterns.slice(0, 8).map((p, i) => (
            <li key={i}>
              <span>{p.prefix || p.pattern || p.description || JSON.stringify(p)}</span>
              {typeof p.count === 'number' && (
                <span className="dc-tk-diag-list-num">× {p.count}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function NoveltyWarningsCard({ warnings }) {
  return (
    <div className="dc-tk-diag-card">
      <div className="dc-tk-diag-card-head">
        <span className="dc-tk-diag-card-title">NoveltyCritic · {warnings.length}</span>
      </div>
      {warnings.length === 0 ? (
        <div className="dc-tk-diag-empty">暂无新颖度警告</div>
      ) : (
        <ul className="dc-tk-diag-list is-warn">
          {warnings.slice(0, 6).map((w, i) => (
            <li key={i}>
              <strong>{w.code || w.warning_type || 'WARN'}</strong>{' '}
              {w.description || w.message || ''}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// v2.48 — § OpenLoops 编辑器: 列出当前 N 个伏笔 + 添加表单 + 关闭按钮
function OpenLoopsSection({ loops, form, setForm, onAdd, onClose, busy, currentTick }) {
  return (
    <div className="dc-tk-diag">
      <div className="dc-tk-diag-head">
        <span className="dc-tk-rtbar-kicker">OPEN LOOPS · 伏笔池</span>
        <span className="dc-tk-diag-card-meta" style={{ marginLeft: 12 }}>
          {loops.length} 条 · 当前 tick {currentTick}
        </span>
      </div>
      <div className="dc-tk-diag-grid">
        <div className="dc-tk-diag-card">
          <div className="dc-tk-diag-card-head">
            <span className="dc-tk-diag-card-title">现有伏笔</span>
          </div>
          {loops.length === 0 ? (
            <div className="dc-tk-diag-empty">暂无开放伏笔</div>
          ) : (
            <ul className="dc-tk-diag-list">
              {loops.map((l) => (
                <li key={l.id}>
                  <span>
                    <strong>{l.id}</strong>
                    <span className={`dc-tk-loop-urg dc-tk-loop-urg-${urgencyBucket(l.urgency)}`}>
                      U{l.urgency ?? '?'}
                    </span>
                    {' '}{l.description || ''}
                    {l.opened_tick != null && (
                      <span className="dc-tk-diag-list-num"> · t{l.opened_tick}</span>
                    )}
                  </span>
                  <button
                    type="button"
                    className="dc-tk-loop-close"
                    onClick={() => onClose(l.id)}
                    disabled={busy}
                    title="关闭这个伏笔"
                  >
                    × 关闭
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <form className="dc-tk-diag-card" onSubmit={onAdd}>
          <div className="dc-tk-diag-card-head">
            <span className="dc-tk-diag-card-title">添加伏笔</span>
            <span className="dc-tk-diag-card-meta">opened_tick 自动 = t{currentTick + 1}</span>
          </div>
          <div className="dc-tk-loop-form">
            <input
              className="dc-input"
              type="text"
              placeholder="loop id (如 missing_letter)"
              value={form.id}
              onChange={(e) => setForm({ ...form, id: e.target.value })}
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            />
            <textarea
              className="dc-input"
              rows={2}
              placeholder="描述这个伏笔(为什么读者会记得?)"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              style={{ resize: 'none' }}
            />
            <div className="dc-tk-loop-form-row">
              <label style={{ font: "500 11px/1 'JetBrains Mono', monospace", color: 'var(--text3)' }}>
                urgency
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={form.urgency}
                  onChange={(e) => setForm({ ...form, urgency: e.target.value })}
                  style={{
                    marginLeft: 8,
                    width: 60,
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    padding: '4px 6px',
                    font: "500 12px/1 'JetBrains Mono', monospace",
                    color: 'var(--text)',
                  }}
                />
              </label>
              <input
                className="dc-input"
                type="text"
                placeholder="涉及角色 id (逗号分隔, 可选)"
                value={form.involved_characters}
                onChange={(e) => setForm({ ...form, involved_characters: e.target.value })}
                style={{ flex: 1, fontFamily: "'JetBrains Mono', monospace" }}
              />
              <button type="submit" className="dc-btn" disabled={busy}>+ 添加</button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}

function urgencyBucket(u) {
  const n = Number(u) || 0
  if (n >= 8) return 'high'
  if (n >= 5) return 'mid'
  return 'low'
}

function StyleAnchorsCard({ anchors }) {
  return (
    <div className="dc-tk-diag-card is-wide">
      <div className="dc-tk-diag-card-head">
        <span className="dc-tk-diag-card-title">Style Anchors · {anchors.length}</span>
      </div>
      {anchors.length === 0 ? (
        <div className="dc-tk-diag-empty">暂无风格锚点</div>
      ) : (
        <div className="dc-tk-diag-badges">
          {anchors.map((a, i) => {
            const excerpt = a.excerpt || a.example || a.snippet || ''
            const sceneType =
              a.scene_type || a.label || a.category || a.tag || 'general'
            const weight =
              typeof a.weight === 'number'
                ? a.weight
                : typeof a.score === 'number'
                  ? a.score
                  : null
            const tooltip = a.selection_reason
              ? `[${a.selection_reason}] ${excerpt}`
              : excerpt
            return (
              <span
                key={i}
                className="dc-tk-diag-badge is-anchor"
                title={tooltip}
              >
                {sceneType}
                {weight !== null && (
                  <span className="dc-tk-diag-badge-num">
                    {' '}({weight.toFixed(2)})
                  </span>
                )}
              </span>
            )
          })}
        </div>
      )}
    </div>
  )
}
