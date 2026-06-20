import React from 'react'
import { formatNum, formatRuntime, formatTick, formatNarrMeta } from '../../utils'

// v2.47 — § Hero: ACTIVE NOVEL kicker + 大标题 + 4 stats + Narrator excerpt + World snapshot.
// 所有数据从 props 进来; 缺失字段显示 "—" 不假造.

export default function HeroSection({
  novel,
  tickStatus,
  stats,
  narrative,
  onJumpReader,
  onJumpChapter,
}) {
  const novelTitle = novel?.title || novel?.id || '未选择作品'
  const novelId = novel?.id || ''
  const sectionNo =
    tickStatus?.current_section ?? tickStatus?.section_index ?? stats?.total_sections ?? null
  const sectionLabel =
    typeof sectionNo === 'number' && sectionNo > 0 ? `第 ${sectionNo} 节` : '总览'

  const currentTick =
    typeof tickStatus?.current_tick === 'number' ? tickStatus.current_tick : null
  const totalWords = stats?.total_words ?? null
  const charCount = tickStatus?.character_count ?? null
  const runtimeMs = stats?.runtime_ms ?? stats?.uptime_ms ?? null
  const running = Boolean(tickStatus && !tickStatus.is_paused)

  const ws = tickStatus?.world_state || tickStatus?.world || {}
  const snapshot = {
    时间: ws.time || ws.calendar || ws.datetime || ws.world_time || null,
    天气: ws.weather || null,
    地理: ws.location || ws.place || ws.region || null,
    社会: ws.social || ws.regime || ws.society || null,
  }
  const hasAnySnapshot = Object.values(snapshot).some(Boolean)

  return (
    <section className="dc-ov-hero">
      {/* —— Left —— */}
      <div className="dc-ov-hero-left">
        <div className="dc-kicker">
          <span className="dc-kicker-bar" />
          <span className="dc-kicker-text">ACTIVE NOVEL</span>
          {novelId && <span className="dc-kicker-aux">· novel_id = {novelId}</span>}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <button
            type="button"
            className="dc-ov-h1 is-jump"
            onClick={onJumpChapter}
            title="跳转至 章节与多模态"
          >
            <span>{novelTitle}</span>
            <span className="dc-ov-h1-dot"> · </span>
            <span>{sectionLabel}</span>
          </button>
          <div className="dc-ov-hero-stats">
            <span>
              <span className="dc-ov-hero-stat-num">{formatTick(currentTick)}</span>{' '}
              <span className="dc-ov-hero-stat-lbl">tick</span>
            </span>
            <span>
              <span className="dc-ov-hero-stat-num">{formatNum(totalWords)}</span>{' '}
              <span className="dc-ov-hero-stat-lbl">字</span>
            </span>
            <span>
              <span className="dc-ov-hero-stat-num">{formatRuntime(runtimeMs)}</span>{' '}
              <span className="dc-ov-hero-stat-lbl">运行</span>
            </span>
            <span>
              <span className="dc-ov-hero-stat-num">{charCount ?? '—'}</span>{' '}
              <span className="dc-ov-hero-stat-lbl">角色</span>
            </span>
          </div>
        </div>

        {/* Narrator excerpt card */}
        {narrative ? (
          <div
            className="dc-ov-narr"
            onClick={onJumpReader}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') onJumpReader?.()
            }}
            title="阅读全文"
          >
            <div className="dc-ov-narr-head">
              <div className="dc-ov-narr-head-l">
                <span className="dc-ov-narr-tag">NARRATOR</span>
                <span className="dc-ov-narr-meta">{formatNarrMeta(narrative)}</span>
              </div>
              <span className="dc-ov-narr-meta">
                价值 <span className="dc-ov-narr-meta-num">—</span>
                {' · '}幻觉 <span className="dc-ov-narr-meta-num">—</span>
              </span>
            </div>
            <p className="dc-ov-narr-body">{narrative.text || '（无正文）'}</p>
            <div className="dc-ov-narr-foot">
              <span>章节 · {sectionLabel}</span>
              <span>·</span>
              <span>tick · {formatTick(narrative.tick ?? currentTick)}</span>
              <span className="dc-ov-narr-cta">阅读全文 →</span>
            </div>
          </div>
        ) : (
          <div className="dc-ov-narr">
            <div className="dc-ov-narr-empty">
              尚无叙述者输出 — 推进 tick 后 Narrator 会在此呈现最近一次的写作片段。
            </div>
          </div>
        )}
      </div>

      {/* —— Right: World snapshot —— */}
      <div className="dc-ov-hero-right">
        <div className="dc-kicker is-ink">
          <span className="dc-kicker-bar" />
          <span className="dc-kicker-text">WORLD SNAPSHOT</span>
        </div>

        <div className="dc-ov-snap">
          <div className="dc-ov-snap-grid">
            {Object.entries(snapshot).map(([k, v]) => (
              <div key={k}>
                <div className="dc-ov-snap-k">{k}</div>
                <div className="dc-ov-snap-v">{v || '—'}</div>
              </div>
            ))}
          </div>

          <div className="dc-ov-snap-sep" />

          <div>
            <div className="dc-ov-snap-k">当前 tick</div>
            <div className="dc-ov-snap-v">
              {currentTick !== null ? `tick ${formatTick(currentTick)}` : '尚未推进'}
              {' · '}
              {running ? '运行中' : '已暂停'}
            </div>
          </div>

          {!hasAnySnapshot && (
            <>
              <div className="dc-ov-snap-sep" />
              <div
                style={{
                  font: "400 11px/1.5 'Inter', sans-serif",
                  color: 'var(--text3)',
                }}
              >
                世界快照字段尚未在 tickStatus 暴露 — 待后端 /api/tick/status 扩展.
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  )
}
