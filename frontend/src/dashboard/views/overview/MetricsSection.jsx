import React, { useMemo } from 'react'
import { classifyBar, formatNum } from '../../utils'

// v2.47 — § 01 实时指标: 6 KPI 卡 + 60-tick value 时间线 + TICK 控制 (ink).
//
// 6 cards (left → right):
//   1. TOKENS / TICK         (cur vs base, -77% etc.)
//   2. TICK DURATION         (cur vs base)
//   3. 幻觉率                (current vs threshold)
//   4. 创造力                (TTR / struct / emo)
//   5. 伏笔池                (count + 5-cell bar)
//   6. 测试 / 健康           (575/575 · 6.1s · smoke + budget)
//
// 60-tick timeline = recent ticks 的 narrative_value (后端 history row 里有
// narrator_produced_text + 价值不是直接给出, 这里用 0/1 fallback).
// 真后端度量字段尚未引入时使用占位, 数值显示 "—".

const TIMELINE_LEN = 60

export default function MetricsSection({
  tickStatus,
  history,
  openLoopsCount,
  hallucinationStats,
  onToggleRun,
  onStepOne,
  onOpenInject,
  running,
}) {
  const currentTick =
    typeof tickStatus?.current_tick === 'number' ? tickStatus.current_tick : null
  const runningTickStr = currentTick != null ? currentTick.toLocaleString() : '—'

  // —— Card 1: tokens / tick ——
  // history row 形式: { tick, agents_called, ... } — tokens_used 字段不一定有.
  const tokensSeries = useMemo(() => {
    return (history || []).map((r) => r.tokens_used ?? r.tokens ?? null)
  }, [history])
  const tokensCur = avgFinite(tokensSeries.slice(-10))
  const tokensBase = avgFinite(tokensSeries) // 整段均值当 baseline
  const tokensDelta = pctDelta(tokensCur, tokensBase)

  // —— Card 2: tick duration ——
  const durSeries = useMemo(() => {
    return (history || []).map((r) => r.duration_ms ?? r.duration ?? r.took_ms ?? null)
  }, [history])
  const durCur = avgFinite(durSeries.slice(-10))
  const durBase = avgFinite(durSeries)
  const durDelta = pctDelta(durCur, durBase)

  // —— Card 3: 幻觉率 ——
  const hallStats = hallucinationStats?.stats || hallucinationStats || []
  const totalFlagged = Array.isArray(hallStats) ? hallStats.length : 0
  // rate = flagged / max(1, history) — 占位估算; 后端无 per-tick rate.
  const hallRate =
    totalFlagged > 0 && (history || []).length > 0
      ? totalFlagged / history.length
      : null
  const hallAuto = Boolean(hallucinationStats?.auto_degrade_active)

  // —— Card 4: 创造力 ——
  // 后端没有直接的 TTR / struct / emo 度量, 这里展示 "—".
  // Phase 6 后会有 prose_dynamics 度量, 那时再接.

  // —— Card 5: 伏笔池 ——
  const loopCount = openLoopsCount ?? null
  const loopMin = 3

  // —— Card 6: 测试 / 健康 (静态 — CI 数据不入 runtime) ——

  // —— Timeline: 最近 60 tick "narrator produced text" 比例 ——
  const bars = useMemo(() => {
    if (!Array.isArray(history) || history.length === 0) {
      return Array(TIMELINE_LEN).fill(0)
    }
    const tail = history.slice(-TIMELINE_LEN)
    const arr = tail.map((r) => {
      const v = r.narrator_produced_text ? 1 : 0
      const dur = r.duration_ms ?? r.took_ms ?? null
      // 联合: 有叙述 → 高; 无叙述但耗时 high → 中等; 否则低
      if (v) return 0.85
      if (typeof dur === 'number' && dur > 8000) return 0.45
      return 0.18
    })
    while (arr.length < TIMELINE_LEN) arr.unshift(0)
    return arr
  }, [history])

  return (
    <section className="dc-ov-section">
      <div className="dc-sec-head">
        <span className="dc-sec-num">§ 01</span>
        <h2 className="dc-sec-title">实时指标</h2>
        <span className="dc-sec-sub">最近 50 tick 滑窗</span>
        <span className="dc-sec-meta">
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: running ? 'var(--accent)' : '#A3A3A3',
              animation: running ? 'dc-run-pulse 1.8s ease-in-out infinite' : 'none',
              display: 'inline-block',
              marginRight: 6,
            }}
          />
          LIVE
        </span>
      </div>

      <div className="dc-ov-metrics">
        {/* 1: tokens / tick */}
        <div className="dc-ov-metric">
          <div className="dc-ov-metric-head">
            <span className="dc-ov-metric-kicker">tokens / tick</span>
            <span className={`dc-ov-metric-delta ${tokensDelta == null ? 'is-mute' : ''}`}>
              {tokensDelta == null ? '—' : `${tokensDelta >= 0 ? '+' : ''}${tokensDelta}%`}
            </span>
          </div>
          <div className="dc-ov-metric-num">
            {tokensCur != null ? formatKLike(tokensCur) : '—'}
          </div>
          <div className="dc-ov-metric-bars">
            <div className="dc-ov-metric-bar-row">
              <span className="dc-ov-metric-bar-lbl">cur</span>
              <div className="dc-ov-metric-bar-track">
                <div
                  className="dc-ov-metric-bar-fill"
                  style={{ width: tokensCur && tokensBase ? `${Math.min(100, (tokensCur / tokensBase) * 100)}%` : '0%' }}
                />
              </div>
            </div>
            <div className="dc-ov-metric-bar-row">
              <span className="dc-ov-metric-bar-lbl">base</span>
              <div className="dc-ov-metric-bar-track">
                <div className="dc-ov-metric-bar-fill is-base" style={{ width: '100%' }} />
              </div>
            </div>
          </div>
        </div>

        {/* 2: tick duration */}
        <div className="dc-ov-metric">
          <div className="dc-ov-metric-head">
            <span className="dc-ov-metric-kicker">tick duration</span>
            <span className={`dc-ov-metric-delta ${durDelta == null ? 'is-mute' : ''}`}>
              {durDelta == null ? '—' : `${durDelta >= 0 ? '+' : ''}${durDelta}%`}
            </span>
          </div>
          <div className="dc-ov-metric-num">
            {durCur != null ? (durCur / 1000).toFixed(1) : '—'}
            <span className="dc-ov-metric-num-unit"> s</span>
          </div>
          <div className="dc-ov-metric-bars">
            <div className="dc-ov-metric-bar-row">
              <span className="dc-ov-metric-bar-lbl">cur</span>
              <div className="dc-ov-metric-bar-track">
                <div
                  className="dc-ov-metric-bar-fill"
                  style={{ width: durCur && durBase ? `${Math.min(100, (durCur / durBase) * 100)}%` : '0%' }}
                />
              </div>
            </div>
            <div className="dc-ov-metric-bar-row">
              <span className="dc-ov-metric-bar-lbl">base</span>
              <div className="dc-ov-metric-bar-track">
                <div className="dc-ov-metric-bar-fill is-base" style={{ width: '100%' }} />
              </div>
            </div>
          </div>
        </div>

        {/* 3: 幻觉率 */}
        <div className="dc-ov-metric">
          <div className="dc-ov-metric-head">
            <span className="dc-ov-metric-kicker">幻觉率</span>
            <span className="dc-ov-metric-delta is-mute">阈值 0.30</span>
          </div>
          <div className="dc-ov-metric-num">
            {hallRate != null ? hallRate.toFixed(2) : '—'}
          </div>
          <div className="dc-ov-metric-bar-track" style={{ position: 'relative' }}>
            <div
              className="dc-ov-metric-bar-fill"
              style={{
                background: 'var(--ink)',
                width: `${hallRate != null ? Math.min(100, (hallRate / 0.3) * 100) : 0}%`,
              }}
            />
          </div>
          <div className="dc-ov-metric-foot">
            Guardian {totalFlagged} 命中 · auto_degrade {hallAuto ? 'on' : 'off'}
          </div>
        </div>

        {/* 4: 创造力 */}
        <div className="dc-ov-metric">
          <div className="dc-ov-metric-head">
            <span className="dc-ov-metric-kicker">创造力</span>
            <span className="dc-ov-metric-delta is-mute">vs 基线</span>
          </div>
          <div className="dc-ov-metric-num">—</div>
          <div className="dc-ov-metric-pairs">
            <div className="dc-ov-metric-pair">
              <span className="dc-ov-metric-pair-k">TTR</span>
              <span>—</span>
            </div>
            <div className="dc-ov-metric-pair">
              <span className="dc-ov-metric-pair-k">struct</span>
              <span>—</span>
            </div>
            <div className="dc-ov-metric-pair">
              <span className="dc-ov-metric-pair-k">emo</span>
              <span>—</span>
            </div>
          </div>
        </div>

        {/* 5: 伏笔池 */}
        <div className="dc-ov-metric">
          <div className="dc-ov-metric-head">
            <span className="dc-ov-metric-kicker">伏笔池</span>
            <span className="dc-ov-metric-delta">最低 ≥ {loopMin}</span>
          </div>
          <div className="dc-ov-metric-num">{loopCount != null ? loopCount : '—'}</div>
          <div style={{ display: 'flex', gap: 3 }}>
            {Array.from({ length: 5 }, (_, i) => {
              const filled = loopCount != null && i < loopCount
              return (
                <div
                  key={i}
                  style={{
                    flex: 1,
                    height: 18,
                    background: filled ? 'var(--red-tint)' : 'var(--track)',
                    borderTop: `2px solid ${filled ? 'var(--accent)' : 'var(--border2)'}`,
                  }}
                />
              )
            })}
          </div>
          <div className="dc-ov-metric-foot">
            {loopCount != null ? `${loopCount} 个活跃` : '后端尚未返回伏笔列表'}
          </div>
        </div>

        {/* 6: 测试 / 健康 */}
        <div className="dc-ov-metric">
          <div className="dc-ov-metric-head">
            <span className="dc-ov-metric-kicker">健康</span>
            <span className="dc-ov-metric-delta">LIVE</span>
          </div>
          <div className="dc-ov-metric-num">
            {history && history.length > 0 ? formatNum(history.length) : '—'}
          </div>
          <div className="dc-ov-metric-pairs">
            <div className="dc-ov-metric-pair">
              <span className="dc-ov-metric-pair-k">tick</span>
              <span>{runningTickStr}</span>
            </div>
            <div className="dc-ov-metric-pair">
              <span className="dc-ov-metric-pair-k">runtime</span>
              <span>{running ? 'RUN' : 'PAUSE'}</span>
            </div>
            <div className="dc-ov-metric-pair">
              <span className="dc-ov-metric-pair-k">guardian</span>
              <span>{totalFlagged ? `${totalFlagged} 命中` : '—'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Timeline strip + Tick control */}
      <div className="dc-ov-tline-row">
        <div className="dc-ov-tline-card">
          <div className="dc-ov-tline-head">
            <span className="dc-ov-tline-kicker">最近 {TIMELINE_LEN} TICK · NARRATOR 价值密度</span>
            <span className="dc-ov-tline-aux">
              tick {currentTick ? Math.max(0, currentTick - TIMELINE_LEN) : 0} — {runningTickStr}
            </span>
          </div>
          <div className="dc-ov-tline-bars">
            {bars.map((v, i) => {
              const isNow = i >= bars.length - 5
              const cls = classifyBar(v, isNow)
              return (
                <div
                  key={i}
                  className={`dc-ov-tline-bar ${cls}`}
                  style={{ height: `${Math.max(8, v * 100)}%` }}
                />
              )
            })}
          </div>
          <div className="dc-ov-tline-axis">
            <span>−{TIMELINE_LEN}</span>
            <span>−45</span>
            <span>−30</span>
            <span>−15</span>
            <span className="dc-ov-tline-axis-now">now</span>
          </div>
        </div>

        <div className="dc-ov-tickctl">
          <div className="dc-ov-tickctl-head">
            <span className="dc-ov-tickctl-kicker">TICK 控制</span>
            <span className="dc-ov-tickctl-label">{running ? 'RUNNING' : 'PAUSED'}</span>
          </div>
          <div className="dc-ov-tickctl-num">{runningTickStr}</div>
          <div className="dc-ov-tickctl-row">
            <button
              type="button"
              className="dc-ov-tickctl-toggle"
              onClick={onToggleRun}
            >
              {running ? '暂停调度' : '启动调度'}
            </button>
            <button
              type="button"
              className="dc-btn-ink-ghost"
              style={{ flex: 1 }}
              onClick={onStepOne}
            >
              推进 +1
            </button>
          </div>
          <button
            type="button"
            className="dc-btn-ink-ghost"
            onClick={onOpenInject}
          >
            注入事件
          </button>
        </div>
      </div>
    </section>
  )
}

function avgFinite(arr) {
  const finite = (arr || []).filter((v) => typeof v === 'number' && Number.isFinite(v))
  if (finite.length === 0) return null
  return finite.reduce((a, b) => a + b, 0) / finite.length
}

function pctDelta(cur, base) {
  if (cur == null || base == null || base === 0) return null
  return Math.round(((cur - base) / base) * 100)
}

function formatKLike(n) {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return Math.round(n).toString()
}
