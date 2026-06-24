import React, { useRef, useState } from 'react'
import { injectTickEvent } from '../../services/api'
import { showToast } from '../../utils/toast'

// v2.47 — 注入事件 modal.
// v2.48 — 补全字段对齐 TickControlPanel:
//   id (可选, 留空后端自动生成) / location / participants / visible_to /
//   description / narrative_value (1-10).
// POST /api/tick/inject-event 接口.

const KINDS = [
  { key: 'dramatic',         label: '戏剧 · dramatic',         hint: '高戏剧性事件' },
  { key: 'endogenous',       label: '内生 · endogenous',       hint: '角色内驱事件' },
  { key: 'exogenous',        label: '外生 · exogenous',        hint: '外部环境事件' },
  { key: 'character_action', label: '行动 · character_action', hint: '角色行动' },
]

const DEFAULT_FORM = {
  type: 'dramatic',
  id: '',
  location: '',
  participants: '',
  visible_to: '',
  description: '',
  narrative_value: 8,
}

export default function InjectEventModal({ tickStatus, onClose }) {
  const [form, setForm] = useState(DEFAULT_FORM)
  const [busy, setBusy] = useState(false)
  // 防双击锁 — setState 异步, 快速双击会在 busy=false 时进第二次提交.
  const busyRef = useRef(false)

  function update(patch) {
    setForm((prev) => ({ ...prev, ...patch }))
  }

  async function submit() {
    if (busyRef.current) return
    if (!form.description.trim()) {
      showToast('请填事件描述', 'error')
      return
    }
    busyRef.current = true
    setBusy(true)
    try {
      const participants = form.participants
        .split(/[,,\s]+/)
        .map((p) => p.trim())
        .filter(Boolean)
      const visible_to = form.visible_to
        .split(/[,,\s]+/)
        .map((v) => v.trim())
        .filter(Boolean)
      const payload = {
        type: form.type,
        location: form.location.trim(),
        participants,
        description: form.description.trim(),
        narrative_value: Number(form.narrative_value) || 5,
      }
      // 仅填了才透传 — 后端 id 自动生成, visible_to fallback 到 ['all_in_location'].
      const trimmedId = form.id.trim()
      if (trimmedId) payload.id = trimmedId
      if (visible_to.length > 0) payload.visible_to = visible_to
      const res = await injectTickEvent(payload)
      showToast(`事件已注入 (tick ${res?.event?.tick ?? '?'})`, 'success')
      onClose?.()
    } catch (err) {
      showToast('注入失败: ' + (err?.message || '未知错误'), 'error')
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  return (
    <div
      className="dc-modal-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div className="dc-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="dc-modal-head">
          <div className="dc-modal-title-group">
            <span className="dc-modal-kicker">
              EVENT INJECTOR · tick {tickStatus?.current_tick ?? '—'}
            </span>
            <span className="dc-modal-title">注入事件</span>
          </div>
          <button
            type="button"
            className="dc-modal-close"
            onClick={onClose}
            title="关闭"
            aria-label="关闭"
          >
            <svg width="14" height="14" viewBox="0 0 15 15" fill="none">
              <path
                d="M3 3 L12 12 M12 3 L3 12"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>

        <div className="dc-modal-row">
          <span className="dc-modal-row-label">事件类型</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {KINDS.map((k) => (
              <span
                key={k.key}
                className={`dc-chip ${form.type === k.key ? 'is-active' : ''}`}
                onClick={() => update({ type: k.key })}
                title={k.hint}
              >
                {k.label}
              </span>
            ))}
          </div>
        </div>

        <div className="dc-modal-row">
          <span className="dc-modal-row-label">
            事件 id (可选)
            <span className="dc-modal-row-hint"> · 留空后端自动生成 evt_user_{(tickStatus?.current_tick ?? 0)}_n</span>
          </span>
          <input
            className="dc-input"
            placeholder="evt_meeting_001"
            value={form.id}
            onChange={(e) => update({ id: e.target.value })}
            style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13 }}
          />
        </div>

        <div className="dc-modal-row">
          <span className="dc-modal-row-label">作用地点 location</span>
          <input
            className="dc-input"
            placeholder="十字路口 / 主城 / 山门外"
            value={form.location}
            onChange={(e) => update({ location: e.target.value })}
          />
        </div>

        <div className="dc-modal-row">
          <span className="dc-modal-row-label">
            参与者 participants
            <span className="dc-modal-row-hint"> · 逗号或空格分隔 character_id</span>
          </span>
          <input
            className="dc-input"
            placeholder="char_001, char_002"
            value={form.participants}
            onChange={(e) => update({ participants: e.target.value })}
            style={{ fontFamily: "'JetBrains Mono', monospace" }}
          />
        </div>

        <div className="dc-modal-row">
          <span className="dc-modal-row-label">
            可见性 visible_to
            <span className="dc-modal-row-hint">
              {' · 留空 = all_in_location (需配 location); 特殊 token: all / all_in_location'}
            </span>
          </span>
          <input
            className="dc-input"
            placeholder="留空 / all / char_001, char_002"
            value={form.visible_to}
            onChange={(e) => update({ visible_to: e.target.value })}
            style={{ fontFamily: "'JetBrains Mono', monospace" }}
          />
        </div>

        <div className="dc-modal-row">
          <span className="dc-modal-row-label">
            narrative_value
            <span className="dc-modal-row-hint"> · 1-10, Narrator 决策叙述基线</span>
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <input
              type="range"
              min={1}
              max={10}
              value={form.narrative_value}
              onChange={(e) => update({ narrative_value: e.target.value })}
              style={{ flex: 1 }}
            />
            <input
              type="number"
              min={1}
              max={10}
              value={form.narrative_value}
              onChange={(e) => update({ narrative_value: e.target.value })}
              style={{
                width: 56,
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                padding: '7px 9px',
                font: "500 13px/1 'JetBrains Mono', monospace",
                color: 'var(--text)',
                textAlign: 'center',
              }}
            />
          </div>
        </div>

        <div className="dc-modal-row">
          <span className="dc-modal-row-label">事件描述</span>
          <textarea
            className="dc-input"
            rows={3}
            placeholder="中央密使在十字路口截下阿莱拉, 索要铜符……"
            style={{
              resize: 'none',
              lineHeight: 1.55,
              fontFamily: "'Inter', sans-serif",
            }}
            value={form.description}
            onChange={(e) => update({ description: e.target.value })}
          />
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '14px 16px',
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            borderRadius: 8,
          }}
        >
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: '50%',
              background: 'var(--accent)',
              flex: 'none',
            }}
          />
          <span
            style={{
              font: "400 12px/1.4 'Inter', sans-serif",
              color: 'var(--text3)',
            }}
          >
            将于下一 tick 由 EventInjector 注入并经 Guardian 校验
          </span>
        </div>

        <div className="dc-modal-foot">
          <button type="button" className="dc-btn-ghost" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="dc-btn"
            onClick={submit}
            disabled={busy}
          >
            <span style={{ font: "400 15px/1 'Inter', sans-serif" }}>⊹</span>
            注入到下一 tick
          </button>
        </div>
      </div>
    </div>
  )
}
