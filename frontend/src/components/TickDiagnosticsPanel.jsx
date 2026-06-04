import React, { useCallback, useEffect, useState } from 'react'
import {
  fetchCharacterStates,
  fetchStyleAnchors,
  fetchNoveltyWarnings,
  fetchEventStats,
  fetchActionPatterns,
  fetchHallucinationDiagnostic,
} from '../services/api'
import { showToast } from '../utils/toast'

// v2.20 — Tick 诊断面板, 汇总 v2.16 / v2.18 / v2.19 引入的可观测端点。
// 6 个端点全部曾经"封装了无人调用"或"后端有前端没有", 此处合并为一个 Tab。

export default function TickDiagnosticsPanel({ refreshKey }) {
  const [characterStates, setCharacterStates] = useState([])
  const [styleAnchors, setStyleAnchors] = useState([])
  const [noveltyWarnings, setNoveltyWarnings] = useState([])
  const [eventStats, setEventStats] = useState(null)
  const [actionPatterns, setActionPatterns] = useState(null)
  const [hallucination, setHallucination] = useState(null)
  const [loading, setLoading] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    // 6 个端点全部 settled-style 加载, 任一失败不阻塞其他
    const results = await Promise.allSettled([
      fetchCharacterStates(),
      fetchStyleAnchors(20),
      fetchNoveltyWarnings(),
      fetchEventStats(50),
      fetchActionPatterns(100),
      fetchHallucinationDiagnostic(),
    ])
    const [cs, sa, nw, es, ap, hd] = results
    if (cs.status === 'fulfilled') {
      setCharacterStates(cs.value?.character_states || cs.value?.states || [])
    }
    if (sa.status === 'fulfilled') {
      setStyleAnchors(sa.value?.anchors || [])
    }
    if (nw.status === 'fulfilled') {
      setNoveltyWarnings(nw.value?.warnings || [])
    }
    if (es.status === 'fulfilled') setEventStats(es.value)
    if (ap.status === 'fulfilled') setActionPatterns(ap.value)
    if (hd.status === 'fulfilled') setHallucination(hd.value)

    const failures = results.filter((r) => r.status === 'rejected')
    if (failures.length > 0) {
      showToast(
        `${failures.length}/6 个诊断端点加载失败 (后端未启动或 tick runtime 未注入)`,
        'error'
      )
    }
    setLastUpdated(new Date())
    setLoading(false)
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh, refreshKey])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          marginBottom: 4,
        }}
      >
        <h2
          style={{
            margin: 0,
            fontSize: 18,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <i
            className="fas fa-stethoscope"
            style={{ color: 'var(--accent-emerald)' }}
          ></i>
          Tick 诊断
        </h2>
        {lastUpdated && (
          <span
            style={{ fontSize: 11, color: 'var(--text-muted)' }}
          >
            上次刷新 {lastUpdated.toLocaleTimeString()}
          </span>
        )}
        <button
          className="btn btn-secondary btn-sm"
          onClick={refresh}
          disabled={loading}
          style={{ marginLeft: 'auto' }}
        >
          <i className="fas fa-sync"></i> {loading ? '加载中…' : '刷新'}
        </button>
      </div>

      {/* Hallucination diagnostic (v2.18 Phase 9) */}
      <HallucinationCard data={hallucination} />

      {/* Character states (v2.16 硬状态转移) */}
      <CharacterStatesCard states={characterStates} />

      {/* Event stats (v2.16 18 LLM 调用点标注) */}
      <EventStatsCard data={eventStats} />

      {/* Action patterns (NoveltyCritic 输入) */}
      <ActionPatternsCard data={actionPatterns} />

      {/* Novelty warnings (NoveltyCritic 输出) */}
      <NoveltyWarningsCard warnings={noveltyWarnings} />

      {/* Style anchors (Narrator 风格) */}
      <StyleAnchorsCard anchors={styleAnchors} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// 子卡片 — 每个都做 null-safe, 端点失败时显示占位
// ---------------------------------------------------------------------------

function HallucinationCard({ data }) {
  const stats = data?.stats || {}
  const agents = Object.entries(stats)
  const autoDegrade = data?.auto_degrade_active

  return (
    <div className="card">
      <div
        className="card-title"
        style={{ display: 'flex', alignItems: 'center', gap: 8 }}
      >
        <i
          className="fas fa-exclamation-triangle"
          style={{ color: 'var(--accent-amber)' }}
        ></i>
        Guardian 幻觉率监控 (v2.18 Phase 9)
        <span
          className="badge"
          style={{
            background: autoDegrade
              ? 'rgba(244, 63, 94, 0.15)'
              : 'rgba(99, 102, 241, 0.12)',
            color: autoDegrade ? 'var(--accent-rose)' : 'var(--accent-purple)',
            marginLeft: 'auto',
          }}
        >
          {autoDegrade ? 'active (auto-degrade ON)' : 'shadow mode'}
        </span>
      </div>
      {agents.length === 0 ? (
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          暂无被 Guardian 建议过降级的 agent。
          {autoDegrade
            ? ' (active 期: 任何降级建议会立即写入 model_tier_override)'
            : ' (shadow 期: 仅累加统计, 不动 override)'}
        </p>
      ) : (
        <table
          style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}
        >
          <thead>
            <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
              <th style={{ padding: '6px 8px' }}>agent_id</th>
              <th style={{ padding: '6px 8px' }}>hallucination_hits</th>
              <th style={{ padding: '6px 8px' }}>degrade 次数</th>
              <th style={{ padding: '6px 8px' }}>最近建议 tick</th>
              <th style={{ padding: '6px 8px' }}>override 生效</th>
            </tr>
          </thead>
          <tbody>
            {agents.map(([agentId, s]) => (
              <tr
                key={agentId}
                style={{ borderTop: '1px solid var(--border)' }}
              >
                <td
                  style={{ padding: '6px 8px', fontFamily: 'monospace' }}
                >
                  {agentId}
                </td>
                <td style={{ padding: '6px 8px' }}>{s.hallucination_hits ?? 0}</td>
                <td style={{ padding: '6px 8px' }}>
                  {s.degrade_recommendations ?? 0}
                </td>
                <td style={{ padding: '6px 8px' }}>
                  {s.last_degrade_recommended_tick ?? '-'}
                </td>
                <td
                  style={{
                    padding: '6px 8px',
                    color: s.model_tier_override_active
                      ? 'var(--accent-rose)'
                      : 'var(--text-muted)',
                  }}
                >
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
    <div className="card">
      <div className="card-title">CharacterState ({states.length})</div>
      {states.length === 0 ? (
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          暂无角色状态数据。
        </p>
      ) : (
        <table
          style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}
        >
          <thead>
            <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
              <th style={{ padding: '6px 8px' }}>character_id</th>
              <th style={{ padding: '6px 8px' }}>location</th>
              <th style={{ padding: '6px 8px' }}>money</th>
              <th style={{ padding: '6px 8px' }}>inventory</th>
              <th style={{ padding: '6px 8px' }}>状态</th>
              <th style={{ padding: '6px 8px' }}>arc</th>
            </tr>
          </thead>
          <tbody>
            {states.map((s) => (
              <tr
                key={s.character_id}
                style={{ borderTop: '1px solid var(--border)' }}
              >
                <td
                  style={{ padding: '6px 8px', fontFamily: 'monospace' }}
                >
                  {s.character_id}
                </td>
                <td style={{ padding: '6px 8px' }}>
                  {s.current_location || '-'}
                </td>
                <td style={{ padding: '6px 8px' }}>{s.money ?? 0}</td>
                <td style={{ padding: '6px 8px' }}>
                  {(s.inventory || []).length}
                </td>
                <td
                  style={{
                    padding: '6px 8px',
                    color: 'var(--text-secondary)',
                    fontSize: 11,
                  }}
                >
                  {(s.status_effects || []).join(', ') || '-'}
                </td>
                <td style={{ padding: '6px 8px', fontSize: 11 }}>
                  {s.arc_stage || '-'} ({((s.arc_progress ?? 0) * 100).toFixed(0)}%)
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// v2.22 — 字段对齐 /api/tick/event-stats 实际返回:
// {by_type, high_value_count, avg_narrator_chars, narration_rate, ticks_sampled}
// 此前误读 last_n_ticks / total_events, 头部数字全部 "0 / 50"。
function EventStatsCard({ data }) {
  if (!data) {
    return (
      <div className="card">
        <div className="card-title">事件统计</div>
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          暂无事件统计数据。
        </p>
      </div>
    )
  }
  const byType = data.by_type || {}
  const types = Object.entries(byType)
  const totalEvents = types.reduce((acc, [, n]) => acc + (Number(n) || 0), 0)
  const ticksSampled = data.ticks_sampled ?? 0
  const highValue = data.high_value_count ?? 0
  const narrationRate =
    typeof data.narration_rate === 'number'
      ? `${(data.narration_rate * 100).toFixed(0)}%`
      : '—'
  return (
    <div className="card">
      <div className="card-title">
        事件统计 ({ticksSampled} tick 采样, {totalEvents} 条事件, high-value{' '}
        {highValue}, narrate {narrationRate})
      </div>
      {types.length === 0 ? (
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          暂无事件。
        </p>
      ) : (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 8,
          }}
        >
          {types
            .sort((a, b) => b[1] - a[1])
            .map(([t, n]) => (
              <span
                key={t}
                className="badge"
                style={{
                  background: 'rgba(16, 185, 129, 0.12)',
                  color: 'var(--accent-emerald)',
                  fontSize: 12,
                }}
              >
                {t}: {n}
              </span>
            ))}
        </div>
      )}
    </div>
  )
}

// v2.22 — /api/tick/action-patterns 实际返回 {frequent_prefixes: [{prefix, count}],
// total_actions_sampled}; 此前 patterns/action_patterns 都不命中, 内容永远为空。
function ActionPatternsCard({ data }) {
  if (!data) {
    return (
      <div className="card">
        <div className="card-title">行动模式</div>
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          暂无行动模式数据 (action-patterns)。
        </p>
      </div>
    )
  }
  const patterns =
    data.frequent_prefixes || data.patterns || data.action_patterns || []
  const totalSampled = data.total_actions_sampled ?? 0
  return (
    <div className="card">
      <div className="card-title">
        行动模式 ({patterns.length} 条重复前缀, 共 {totalSampled} 次行动采样)
      </div>
      {patterns.length === 0 ? (
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          暂无重复行动模式。
        </p>
      ) : (
        <ul
          style={{
            listStyle: 'none',
            padding: 0,
            margin: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
            fontSize: 12,
          }}
        >
          {patterns.slice(0, 15).map((p, i) => (
            <li
              key={i}
              style={{
                padding: '4px 8px',
                borderLeft: '2px solid var(--accent-blue)',
                color: 'var(--text-secondary)',
              }}
            >
              {p.prefix || p.pattern || p.description || JSON.stringify(p)}
              {typeof p.count === 'number' && (
                <span
                  style={{ color: 'var(--text-muted)', marginLeft: 8 }}
                >
                  × {p.count}
                </span>
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
    <div className="card">
      <div className="card-title">NoveltyCritic 警告 ({warnings.length})</div>
      {warnings.length === 0 ? (
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          暂无新颖度警告 — 重复模式检测未触发。
        </p>
      ) : (
        <ul
          style={{
            listStyle: 'none',
            padding: 0,
            margin: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            fontSize: 12,
          }}
        >
          {warnings.map((w, i) => (
            <li
              key={i}
              style={{
                padding: '6px 10px',
                background: 'rgba(245, 158, 11, 0.08)',
                borderLeft: '3px solid var(--accent-amber)',
                borderRadius: 4,
              }}
            >
              <strong>{w.code || w.warning_type || 'WARN'}</strong>:{' '}
              {w.description || w.message || JSON.stringify(w)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// v2.22 — StyleAnchor 模型字段是 excerpt / selection_reason / weight / scene_type
// (memory_system/models.py); 此前误用 label/category/tag/example/snippet/score,
// 标签全显示 #0/#1, hover 内容为空。
function StyleAnchorsCard({ anchors }) {
  return (
    <div className="card">
      <div className="card-title">Style Anchors ({anchors.length})</div>
      {anchors.length === 0 ? (
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          暂无风格锚点。
        </p>
      ) : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
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
                className="badge"
                style={{
                  background: 'rgba(99, 102, 241, 0.12)',
                  color: 'var(--accent-purple)',
                  fontSize: 11,
                }}
                title={tooltip}
              >
                {sceneType} {weight !== null && (
                  <span style={{ marginLeft: 4 }}>
                    ({weight.toFixed(2)})
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
