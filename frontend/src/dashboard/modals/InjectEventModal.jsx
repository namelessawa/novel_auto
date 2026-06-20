import React, { useState } from 'react'
import { injectTickEvent } from '../../services/api'
import { showToast } from '../../utils/toast'

// v2.47 — 注入事件 modal.
// POST /api/tick/inject-event 接口字段:
//   { event_type, description, target, narrative_value (1-10) }

const KINDS = [
  { key: 'endogenous', label: '内生' },
  { key: 'exogenous',  label: '外生' },
  { key: 'dramatic',   label: '戏剧' },
  { key: 'natural',    label: '自然' },
]

export default function InjectEventModal({ tickStatus, onClose }) {
  const [kind, setKind] = useState('dramatic')
  const [target, setTarget] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!description.trim()) {
      showToast('请填事件描述', 'error')
      return
    }
    setBusy(true)
    try {
      await injectTickEvent({
        event_type: kind,
        description: description.trim(),
        target: target.trim() || null,
        narrative_value: 7,
      })
      showToast('已加入下一 tick 队列, 由 EventInjector 应用', 'success')
      onClose?.()
    } catch (err) {
      showToast(err.message || '注入失败', 'error')
    } finally {
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
                className={`dc-chip ${kind === k.key ? 'is-active' : ''}`}
                onClick={() => setKind(k.key)}
              >
                {k.label}
              </span>
            ))}
          </div>
        </div>

        <div className="dc-modal-row">
          <span className="dc-modal-row-label">作用对象</span>
          <input
            className="dc-input"
            placeholder="角色 / 地点 / 物件 · 如 阿莱拉"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          />
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
            value={description}
            onChange={(e) => setDescription(e.target.value)}
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
