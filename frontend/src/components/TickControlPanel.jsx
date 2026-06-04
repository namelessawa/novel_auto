import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchTickStatus,
  runOneTick,
  pauseTick,
  resumeTick,
  injectTickEvent,
  fetchTickHistory,
  fetchTickOpenLoops,
} from '../services/api'
import { showToast } from '../utils/toast'

const EVENT_TYPES = [
  { value: 'dramatic', label: 'dramatic — 高戏剧性事件' },
  { value: 'endogenous', label: 'endogenous — 角色内驱事件' },
  { value: 'exogenous', label: 'exogenous — 外部环境事件' },
  { value: 'character_action', label: 'character_action — 角色行动' },
]

const DEFAULT_FORM = {
  type: 'dramatic',
  // v2.20 — 可选显式 id; 留空时后端自动生成 evt_user_{tick}_{idx}。重复 id 后端 409。
  id: '',
  location: '',
  participants: '',
  // v2.20 — visible_to 控制事件的可见性子集。逗号/空格分隔的 character_id 列表;
  // 留空时后端 fallback 为 ['all_in_location'] (location 必须非空)。
  // 特殊 token: 'all' (全部角色) / 'all_in_location' (location 内全员)。
  visible_to: '',
  description: '',
  narrative_value: 8,
}

export default function TickControlPanel({ onAction, refreshKey }) {
  const [status, setStatus] = useState(null)
  const [history, setHistory] = useState([])
  const [openLoops, setOpenLoops] = useState([])
  const [busy, setBusy] = useState(false)
  const [statusError, setStatusError] = useState('')
  const [form, setForm] = useState(DEFAULT_FORM)
  const pollTimer = useRef(null)

  const refresh = useCallback(async () => {
    try {
      const s = await fetchTickStatus()
      setStatus(s)
      setStatusError('')
    } catch (err) {
      setStatusError(err?.message || 'Tick runtime 不可用')
      setStatus(null)
    }
    try {
      const h = await fetchTickHistory(15)
      setHistory(h.ticks || [])
    } catch (err) {
      // 历史不致命,容错
    }
    try {
      const o = await fetchTickOpenLoops(5)
      setOpenLoops(o.loops || [])
    } catch (err) {
      // 同上
    }
  }, [])

  useEffect(() => {
    refresh()
    pollTimer.current = setInterval(refresh, 3000)
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current)
    }
  }, [refresh, refreshKey])

  const handleRun = async () => {
    if (busy) return
    if (status?.is_paused) {
      showToast('Tick 已暂停,请先恢复', 'error')
      return
    }
    setBusy(true)
    try {
      const res = await runOneTick()
      const summary = res?.summary
      const produced = summary?.narrator_produced_text
      const chars = summary?.narrator_output_chars || 0
      showToast(
        produced
          ? `Tick ${summary.tick} 完成 · Narrator 产出 ${chars} 字`
          : `Tick ${summary?.tick ?? '?'} 完成 · Narrator 沉默`,
        'success',
      )
      await refresh()
      onAction?.()
    } catch (err) {
      showToast('推进失败:' + (err?.message || '未知错误'), 'error')
    } finally {
      setBusy(false)
    }
  }

  const handlePause = async () => {
    setBusy(true)
    try {
      await pauseTick()
      showToast('已暂停', 'success')
      await refresh()
    } catch (err) {
      showToast('暂停失败:' + err?.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const handleResume = async () => {
    setBusy(true)
    try {
      await resumeTick()
      showToast('已恢复', 'success')
      await refresh()
    } catch (err) {
      showToast('恢复失败:' + err?.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const handleInject = async (e) => {
    e?.preventDefault?.()
    if (!form.description.trim()) {
      showToast('请填写事件描述', 'error')
      return
    }
    setBusy(true)
    try {
      const participants = form.participants
        .split(/[,，\s]+/)
        .map((p) => p.trim())
        .filter(Boolean)
      const visible_to = form.visible_to
        .split(/[,，\s]+/)
        .map((v) => v.trim())
        .filter(Boolean)
      const payload = {
        type: form.type,
        location: form.location.trim(),
        participants,
        description: form.description.trim(),
        narrative_value: Number(form.narrative_value) || 5,
      }
      // v2.20 — 仅当用户填了 id / visible_to 才透传; 空字段交给后端默认逻辑
      // (id 自动生成, visible_to fallback 到 ['all_in_location'])
      const trimmedId = form.id.trim()
      if (trimmedId) payload.id = trimmedId
      if (visible_to.length > 0) payload.visible_to = visible_to
      const res = await injectTickEvent(payload)
      showToast(`事件已注入 (tick ${res?.event?.tick})`, 'success')
      setForm(DEFAULT_FORM)
      await refresh()
      onAction?.()
    } catch (err) {
      showToast('注入失败:' + (err?.message || '未知错误'), 'error')
    } finally {
      setBusy(false)
    }
  }

  if (statusError && !status) {
    return (
      <div className="card" style={{ borderColor: 'var(--accent-rose)' }}>
        <div className="card-title" style={{ color: 'var(--accent-rose)' }}>
          Tick 控制台不可用
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
          {statusError}
        </p>
        <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>
          请确认后端已启动且 <code>/api/tick/status</code> 可达。
        </p>
      </div>
    )
  }

  const sinceLast =
    status && status.last_narration_tick >= 0
      ? status.current_tick - status.last_narration_tick
      : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Status grid */}
      <div className="card">
        <div className="card-title">运行时状态</div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
            gap: 12,
          }}
        >
          {[
            ['当前 tick', status?.current_tick ?? '—'],
            ['世界时间', status?.world_time ?? '—'],
            [
              '运行态',
              status?.is_paused ? (
                <span style={{ color: 'var(--accent-amber)' }}>已暂停</span>
              ) : (
                <span style={{ color: 'var(--accent-emerald)' }}>运行中</span>
              ),
            ],
            ['活跃伏笔', status?.open_loop_count ?? '—'],
            ['角色实例', status?.character_count ?? '—'],
            ['风格锚点', status?.style_anchor_count ?? '—'],
            [
              '距上次叙述',
              sinceLast === null ? '—' : `${sinceLast} tick`,
            ],
          ].map(([label, value]) => (
            <div
              key={label}
              style={{
                padding: 12,
                background: 'var(--bg-primary)',
                borderRadius: 6,
                border: '1px solid var(--border)',
              }}
            >
              <div
                style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}
              >
                {label}
              </div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Controls */}
      <div className="card">
        <div className="card-title">手动调度</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button
            className="btn btn-primary"
            onClick={handleRun}
            disabled={busy || status?.is_paused}
            title={status?.is_paused ? '暂停态下不能手动推进' : '同步执行一个 tick'}
          >
            <i className="fas fa-play"></i> 推进 1 tick
          </button>
          {status?.is_paused ? (
            <button
              className="btn btn-secondary"
              onClick={handleResume}
              disabled={busy}
            >
              <i className="fas fa-play-circle"></i> 恢复
            </button>
          ) : (
            <button
              className="btn btn-secondary"
              onClick={handlePause}
              disabled={busy}
            >
              <i className="fas fa-pause"></i> 暂停
            </button>
          )}
          <button className="btn btn-secondary" onClick={refresh} disabled={busy}>
            <i className="fas fa-sync"></i> 刷新
          </button>
        </div>
        <p
          style={{
            marginTop: 12,
            fontSize: 12,
            color: 'var(--text-muted)',
          }}
        >
          Narrator 在事件总价值 &lt; 5 时会主动沉默 —— 这是 feature。长期沉默时请用下方"注入事件"提供新触发器。
        </p>
      </div>

      {/* Inject event */}
      <div className="card">
        <div className="card-title">注入事件</div>
        <form
          onSubmit={handleInject}
          style={{ display: 'flex', flexDirection: 'column', gap: 10 }}
        >
          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ flex: 1 }}>
              <label className="input-label">事件类型</label>
              <select
                className="input-field"
                value={form.type}
                onChange={(e) =>
                  setForm((f) => ({ ...f, type: e.target.value }))
                }
              >
                {EVENT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ width: 140 }}>
              <label className="input-label">narrative_value</label>
              <input
                type="number"
                className="input-field"
                min={0}
                max={10}
                value={form.narrative_value}
                onChange={(e) =>
                  setForm((f) => ({ ...f, narrative_value: e.target.value }))
                }
              />
            </div>
          </div>
          <div>
            <label className="input-label">地点(可选)</label>
            <input
              type="text"
              className="input-field"
              value={form.location}
              placeholder="如:山顶小屋"
              onChange={(e) =>
                setForm((f) => ({ ...f, location: e.target.value }))
              }
            />
          </div>
          <div>
            <label className="input-label">参与者(逗号或空格分隔)</label>
            <input
              type="text"
              className="input-field"
              value={form.participants}
              placeholder="char_001, char_002"
              onChange={(e) =>
                setForm((f) => ({ ...f, participants: e.target.value }))
              }
            />
          </div>
          <div>
            <label className="input-label">
              可见性 visible_to (逗号或空格分隔, 可选)
            </label>
            <input
              type="text"
              className="input-field"
              value={form.visible_to}
              placeholder="留空 = all_in_location (需配 location);  all / char_001, char_002"
              onChange={(e) =>
                setForm((f) => ({ ...f, visible_to: e.target.value }))
              }
            />
            <p
              style={{
                fontSize: 11,
                color: 'var(--text-muted)',
                marginTop: 4,
              }}
            >
              填具体 character_id 让事件只对这些角色可见; 填 <code>all</code> 给所有角色;
              留空默认 <code>all_in_location</code> (此时 location 必填)
            </p>
          </div>
          <div>
            <label className="input-label">事件 id (可选)</label>
            <input
              type="text"
              className="input-field"
              value={form.id}
              placeholder="留空 = 后端自动生成 evt_user_{tick}_{idx}"
              onChange={(e) =>
                setForm((f) => ({ ...f, id: e.target.value }))
              }
            />
            <p
              style={{
                fontSize: 11,
                color: 'var(--text-muted)',
                marginTop: 4,
              }}
            >
              填了想自己控制 id (例如方便后续按 id 关联剧情); 重复 id 后端返 409
            </p>
          </div>
          <div>
            <label className="input-label">事件描述</label>
            <textarea
              className="input-field"
              rows={3}
              value={form.description}
              placeholder="尽量简短具体,例如:一名信使带来朝廷急报。"
              onChange={(e) =>
                setForm((f) => ({ ...f, description: e.target.value }))
              }
            />
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={busy}
            style={{ alignSelf: 'flex-start' }}
          >
            <i className="fas fa-bolt"></i> 注入到下一个 tick
          </button>
        </form>
      </div>

      {/* Open loops */}
      <div className="card">
        <div className="card-title">活跃伏笔(Top 5)</div>
        {openLoops.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            暂无活跃伏笔。
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
            }}
          >
            {openLoops.map((l) => (
              <li
                key={l.id || l.loop_id || l.description}
                style={{
                  padding: '8px 10px',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  fontSize: 13,
                  display: 'flex',
                  gap: 8,
                  alignItems: 'center',
                }}
              >
                <span
                  className="badge"
                  style={{
                    background: 'rgba(99,102,241,0.12)',
                    color: 'var(--accent-purple)',
                    minWidth: 56,
                    textAlign: 'center',
                  }}
                >
                  紧急 {l.urgency ?? '-'}
                </span>
                <span style={{ flex: 1 }}>
                  {l.description || l.summary || l.id || '(无描述)'}
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                  开自 tick {l.opened_tick ?? '?'}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* History */}
      <div className="card">
        <div className="card-title">最近 15 个 tick</div>
        {history.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            尚无 tick 记录。
          </p>
        ) : (
          <div style={{ maxHeight: 320, overflowY: 'auto' }}>
            <table
              style={{
                width: '100%',
                fontSize: 12,
                borderCollapse: 'collapse',
              }}
            >
              <thead>
                <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                  <th style={{ padding: '6px 8px' }}>tick</th>
                  <th style={{ padding: '6px 8px' }}>narrator</th>
                  <th style={{ padding: '6px 8px' }}>events</th>
                  <th style={{ padding: '6px 8px' }}>摘要</th>
                </tr>
              </thead>
              <tbody>
                {history.map((row) => (
                  <tr
                    key={row.tick ?? row.tick_id}
                    style={{ borderTop: '1px solid var(--border)' }}
                  >
                    <td
                      style={{
                        padding: '6px 8px',
                        fontFamily: 'monospace',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {row.tick ?? row.tick_id}
                    </td>
                    <td
                      style={{
                        padding: '6px 8px',
                        color: row.narrator_produced
                          ? 'var(--accent-emerald)'
                          : 'var(--text-muted)',
                      }}
                    >
                      {row.narrator_produced ? `${row.narrator_chars}字` : '沉默'}
                    </td>
                    <td style={{ padding: '6px 8px' }}>
                      {Array.isArray(row.events_generated)
                        ? row.events_generated.length
                        : 0}
                    </td>
                    <td
                      style={{
                        padding: '6px 8px',
                        color: 'var(--text-secondary)',
                        maxWidth: 360,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={row.state_changes_summary || ''}
                    >
                      {row.state_changes_summary || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
