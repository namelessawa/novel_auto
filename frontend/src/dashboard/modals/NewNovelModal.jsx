import React, { useState } from 'react'
import { bootstrapWorld, createNovel } from '../../services/api'
import { showToast } from '../../utils/toast'

// v2.47 — 新建小说 modal. 创建 + 立即 bootstrap_world.

const GENRES = ['古典', '武侠', '科幻', '玄幻', '现实', '言情', '悬疑']

export default function NewNovelModal({ onClose, onCreated }) {
  const [title, setTitle] = useState('')
  const [novelId, setNovelId] = useState('')
  const [seed, setSeed] = useState('')
  const [genre, setGenre] = useState('古典')
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!title.trim()) {
      showToast('请填小说名', 'error')
      return
    }
    setBusy(true)
    try {
      const res = await createNovel(title.trim())
      const id = res?.id || res?.novel_id || novelId.trim() || null
      if (id) {
        try {
          await bootstrapWorld(id, {
            seed: seed.trim() || `${genre} · ${title.trim()}`,
            genre,
          })
        } catch {
          /* bootstrap 失败不阻塞 — 用户可在 home 重新点冷启动 */
        }
      }
      showToast('已创建作品 — 正在冷启动世界', 'success')
      onCreated?.(id || title.trim())
      onClose?.()
    } catch (err) {
      showToast(err.message || '创建失败', 'error')
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
            <span className="dc-modal-kicker">NEW NOVEL</span>
            <span className="dc-modal-title">新建小说</span>
          </div>
          <button
            type="button"
            className="dc-modal-close"
            onClick={onClose}
            title="关闭"
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
          <span className="dc-modal-row-label">小说名</span>
          <input
            className="dc-input"
            placeholder="例如 · 山阵"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>

        <div className="dc-modal-row">
          <span className="dc-modal-row-label">novel_id (可选)</span>
          <input
            className="dc-input"
            placeholder="mountain (留空则后端自动生成)"
            value={novelId}
            onChange={(e) => setNovelId(e.target.value)}
            style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13 }}
          />
        </div>

        <div className="dc-modal-row">
          <span className="dc-modal-row-label">题材</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {GENRES.map((g) => (
              <span
                key={g}
                className={`dc-chip ${genre === g ? 'is-active' : ''}`}
                onClick={() => setGenre(g)}
              >
                {g}
              </span>
            ))}
          </div>
        </div>

        <div className="dc-modal-row">
          <span className="dc-modal-row-label">冷启动 seed (可选)</span>
          <textarea
            className="dc-input"
            rows={2}
            placeholder="一段 50–200 字的世界开场, 留空则使用题材模版"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            style={{ resize: 'none', fontFamily: "'Noto Serif SC', serif" }}
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
            将以当前 LLM 提供方冷启动世界 · bootstrap_world
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
            <span>+</span>
            创建并冷启动
          </button>
        </div>
      </div>
    </div>
  )
}
