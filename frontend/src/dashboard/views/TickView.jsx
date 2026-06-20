import React, { useEffect, useState } from 'react'
import { fetchTickHistory } from '../../services/api'
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
