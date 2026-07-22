import React, { useEffect, useMemo, useState } from 'react'
import { bootstrapWorld, createNovel, fetchPresets } from '../../services/api'
import { showToast } from '../../utils/toast'

// v2.47 — 新建小说 modal. 创建 + 立即 bootstrap_world.
// v2.48 — 替换 7 chip 硬编码为 Phase 5+ preset matrix (theme + style + ⭐⚠ 推荐),
// 加 advanced 折叠 (positioning + references), bootstrap 时带 also_generate_first_section=true.

const DEFAULT_POSITIONING = '古典含蓄、心理白描、节奏舒缓、避免华丽辞藻'
const DEFAULT_REFERENCES = 'Le Guin / 古龙'

export default function NewNovelModal({ onClose, onCreated }) {
  const [title, setTitle] = useState('')
  const [novelId, setNovelId] = useState('')
  const [seed, setSeed] = useState('')
  const [theme, setTheme] = useState('')
  const [style, setStyle] = useState('')
  const [positioning, setPositioning] = useState('')
  const [references, setReferences] = useState('')
  const [generationMode, setGenerationMode] = useState('author')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  // Phase 5+ — 启动时拉 presets (21 theme × 16 style + 208-cell recommendations).
  // 失败时 silent fallback (presets.available=false → 仅 seed 模式).
  const [presets, setPresets] = useState({
    themes: [],
    styles: [],
    available: false,
    recommendations: { available: false, by_theme: {}, avoid_pairs: [] },
  })

  useEffect(() => {
    let cancelled = false
    fetchPresets()
      .then((data) => {
        if (!cancelled && data && data.available) setPresets(data)
      })
      .catch(() => {
        /* silent — UI 回落到 seed-only 模式 */
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Phase 5-D follow-up — 根据已选 theme 计算 ⭐ top-3 / ⚠ avoid / mean 标注.
  const recommendedStyles = useMemo(() => {
    if (!theme) return []
    const rec = presets?.recommendations
    if (!rec?.available) return []
    return rec.by_theme?.[theme] || []
  }, [theme, presets])

  const recommendedByStyle = useMemo(() => {
    const m = {}
    for (const r of recommendedStyles) m[r.style] = r
    return m
  }, [recommendedStyles])

  const avoidStyleKeys = useMemo(() => {
    if (!theme) return new Set()
    const rec = presets?.recommendations
    if (!rec?.available) return new Set()
    return new Set(
      (rec.avoid_pairs || [])
        .filter((p) => p.theme === theme)
        .map((p) => p.style),
    )
  }, [theme, presets])

  const sortedStyles = useMemo(() => {
    if (!theme || recommendedStyles.length === 0) return presets.styles
    const rankOf = (k) => recommendedByStyle[k]?.rank ?? 9999
    return [...presets.styles].sort((a, b) => rankOf(a.key) - rankOf(b.key))
  }, [theme, presets.styles, recommendedStyles, recommendedByStyle])

  async function submit() {
    if (!title.trim()) {
      showToast('请填小说名', 'error')
      return
    }
    setBusy(true)
    try {
      const res = await createNovel(title.trim(), generationMode)
      const id = res?.id || res?.novel_id || novelId.trim() || null
      if (id) {
        try {
          // Phase 5+: theme + style 跟 seed 一起送, 后端持久化 style_preset_key.
          // also_generate_first_section=true 链式触发首节生成 (HomeView 同款).
          const payload = {
            seed: seed.trim() ? seed : (theme
              ? presets.themes.find((t) => t.key === theme)?.seed || `${theme} · ${title.trim()}`
              : title.trim()),
            also_generate_first_section: true,
            positioning: positioning.trim() ? positioning : DEFAULT_POSITIONING,
            references: references.trim() ? references : DEFAULT_REFERENCES,
          }
          if (theme) payload.theme = theme
          if (style) payload.style = style
          await bootstrapWorld(id, payload)
        } catch {
          /* bootstrap 失败不阻塞 — 用户可在 overview 重新触发冷启动 */
        }
      }
      showToast(
        generationMode === 'author'
          ? '已创建作者模式作品 — 正在建立创作权威 + 首节'
          : '已创建实验模拟作品 — 正在冷启动世界 + 首节',
        'success',
      )
      onCreated?.(id || title.trim(), generationMode)
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
          <span className="dc-modal-row-label">生成模式</span>
          <div className="dc-au-new-mode" role="radiogroup" aria-label="生成模式">
            <button
              type="button"
              role="radio"
              aria-checked={generationMode === 'author'}
              className={generationMode === 'author' ? 'is-active' : ''}
              onClick={() => setGenerationMode('author')}
            >
              <span>DEFAULT</span>
              <strong>作者模式</strong>
              <p>StoryBible + 本节目标 + 单 Writer，默认选择。</p>
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={generationMode === 'simulation'}
              className={generationMode === 'simulation' ? 'is-active is-experimental' : 'is-experimental'}
              onClick={() => setGenerationMode('simulation')}
            >
              <span>EXPERIMENTAL</span>
              <strong>世界模拟</strong>
              <p>启用 9 Agent + Tick 实验运行时，可稍后切换。</p>
            </button>
          </div>
        </div>

        {/* v2.48 — Phase 5+ preset matrix. presets 失败时不渲染下拉, fallback 到 seed only. */}
        {presets.available && (
          <>
            <div className="dc-modal-row">
              <span className="dc-modal-row-label">主题 preset (可选)</span>
              <select
                className="dc-input"
                value={theme}
                onChange={(e) => {
                  const k = e.target.value
                  const prevTheme = theme
                  setTheme(k)
                  // 选了主题且 seed 为空 → 自动填充
                  if (k && !seed.trim()) {
                    const t = presets.themes.find((x) => x.key === k)
                    if (t) setSeed(t.seed)
                  } else if (!k && prevTheme) {
                    // 反选清空之前自动填充的 seed
                    const old = presets.themes.find((x) => x.key === prevTheme)
                    if (old && seed.trim() === old.seed.trim()) setSeed('')
                  }
                }}
              >
                <option value="">(自定义 seed)</option>
                {presets.themes.map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="dc-modal-row">
              <span className="dc-modal-row-label">
                风格 preset (可选)
                {theme && recommendedStyles.length > 0 && (
                  <span className="dc-modal-row-hint"> · ⭐ 本主题推荐</span>
                )}
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <select
                  className="dc-input"
                  value={style}
                  onChange={(e) => setStyle(e.target.value)}
                  title={
                    style
                      ? presets.styles.find((x) => x.key === style)?.description || ''
                      : '默认 literary (描写细致)'
                  }
                >
                  <option value="">默认 (literary)</option>
                  {sortedStyles.map((s) => {
                    const rec = recommendedByStyle[s.key]
                    const isAvoid = avoidStyleKeys.has(s.key)
                    const prefix = rec?.is_top ? '⭐ ' : isAvoid ? '⚠ ' : ''
                    const suffix = rec ? `  (${rec.mean.toFixed(2)})` : ''
                    return (
                      <option key={s.key} value={s.key}>
                        {prefix}{s.label}{suffix}
                      </option>
                    )
                  })}
                </select>
                {theme && recommendedStyles.length > 0 && (
                  <div className="dc-modal-row-hint">
                    推荐: {recommendedStyles.slice(0, 3).map((r) => {
                      const s = presets.styles.find((x) => x.key === r.style)
                      return s ? `${s.label} (${r.mean.toFixed(2)})` : r.style
                    }).join(' / ')}
                  </div>
                )}
              </div>
            </div>
          </>
        )}

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

        {/* v2.48 — Advanced: positioning + references, 默认折叠. 不填用 DEFAULT_*. */}
        <div className="dc-modal-row">
          <button
            type="button"
            className="dc-modal-advanced-toggle"
            onClick={() => setAdvancedOpen((v) => !v)}
          >
            {advancedOpen ? '▾' : '▸'} 高级配置 (positioning / references)
          </button>
        </div>
        {advancedOpen && (
          <>
            <div className="dc-modal-row">
              <span className="dc-modal-row-label">写作定位</span>
              <input
                className="dc-input"
                placeholder={DEFAULT_POSITIONING}
                value={positioning}
                onChange={(e) => setPositioning(e.target.value)}
              />
            </div>
            <div className="dc-modal-row">
              <span className="dc-modal-row-label">参考作家</span>
              <input
                className="dc-input"
                placeholder={DEFAULT_REFERENCES}
                value={references}
                onChange={(e) => setReferences(e.target.value)}
              />
            </div>
          </>
        )}

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
            {generationMode === 'author'
              ? '默认只装配作者模式运行时 · 自动建立创作圣经与首节事务'
              : '将装配实验性世界模拟运行时 · 自动推进首节'}
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
            创建并开始创作
          </button>
        </div>
      </div>
    </div>
  )
}
