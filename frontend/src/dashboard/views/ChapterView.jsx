import React, { useEffect, useMemo, useState } from 'react'
import {
  fetchMultimodalAssetBlobUrl,
  fetchTickNarratives,
  getMultimodalManifest,
  listTickSections,
  listMultimodalSections,
} from '../../services/api'

// v2.47 — § 章节与多模态. 左 section list, 右选中节正文 + 多模态资产 4 tile + mimo 评分.

export default function ChapterView({ novel, onJumpReader }) {
  const [sections, setSections] = useState([])
  const [mmIndex, setMmIndex] = useState(new Map()) // key: chapter:section → status
  const [sel, setSel] = useState(null)
  const [selPreview, setSelPreview] = useState(null) // narratives 片段
  const [selManifest, setSelManifest] = useState(null)
  const [thumbs, setThumbs] = useState({}) // tile_idx → blob url

  // —— load section list + mm status ——
  useEffect(() => {
    if (!novel?.id) return undefined
    let cancelled = false
    async function load() {
      try {
        const r = await listTickSections(novel.id)
        const items = r?.sections || r?.items || []
        if (!cancelled) setSections(items)
        if (items.length > 0 && !sel) {
          setSel(items[0])
        }
      } catch {
        if (!cancelled) setSections([])
      }
      try {
        const r = await listMultimodalSections(novel.id)
        const items = r?.items || []
        const map = new Map()
        items.forEach((it) => map.set(`${it.chapter}:${it.section}`, it))
        if (!cancelled) setMmIndex(map)
      } catch {
        if (!cancelled) setMmIndex(new Map())
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [novel?.id])

  // —— load selected section detail ——
  useEffect(() => {
    if (!novel?.id || !sel) return undefined
    let cancelled = false
    async function load() {
      const tickStart = sel.start_tick ?? sel.tick_start ?? 0
      const tickEnd = sel.end_tick ?? sel.tick_end ?? 0
      try {
        const r = await fetchTickNarratives({ startTick: tickStart, endTick: tickEnd, limit: 1 })
        const last = (r?.narratives || []).slice(-1)[0] || null
        if (!cancelled) setSelPreview(last)
      } catch {
        if (!cancelled) setSelPreview(null)
      }
      const chapter = sel.chapter ?? 1
      const section = sel.section ?? sel.index ?? sel.id ?? 1
      try {
        const m = await getMultimodalManifest(novel.id, chapter, section)
        if (!cancelled) setSelManifest(m)
      } catch {
        if (!cancelled) setSelManifest(null)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [sel, novel?.id])

  // —— blob preview for first 4 images ——
  useEffect(() => {
    if (!novel?.id || !sel || !selManifest) return undefined
    const seg = (selManifest?.segments || []).slice(0, 4)
    let cancelled = false
    const created = []
    async function load() {
      const out = {}
      for (let i = 0; i < seg.length; i++) {
        const s = seg[i]
        if (!s?.image_filename) continue
        try {
          const url = await fetchMultimodalAssetBlobUrl(
            novel.id,
            sel.chapter ?? 1,
            sel.section ?? sel.index ?? 1,
            s.image_filename,
          )
          if (cancelled) {
            URL.revokeObjectURL(url)
            return
          }
          out[i] = url
          created.push(url)
        } catch {
          /* skip */
        }
      }
      if (!cancelled) setThumbs(out)
    }
    load()
    return () => {
      cancelled = true
      created.forEach((u) => URL.revokeObjectURL(u))
    }
  }, [selManifest, novel?.id, sel])

  const totalWords = useMemo(
    () => sections.reduce((s, x) => s + (x.word_count || x.words || 0), 0),
    [sections],
  )

  return (
    <div className="dc-view-switch dc-ch-root">
      <div className="dc-sec-head">
        <span className="dc-sec-num">§ Chapter</span>
        <h2 className="dc-sec-title">章节与多模态</h2>
        <span className="dc-sec-sub">{sections.length} 节 · mimo 配图与配音</span>
        <span className="dc-sec-meta">
          {totalWords > 0 ? `${totalWords.toLocaleString()} 字` : '—'}
        </span>
      </div>

      <div className="dc-ch-row">
        {/* —— Section list —— */}
        <div className="dc-ch-col">
          <span className="dc-ch-col-kicker">节 · SECTION</span>
          <div className="dc-ch-list">
            {sections.map((s, i) => {
              const chap = s.chapter ?? 1
              const sec = s.section ?? s.index ?? s.id ?? i + 1
              const mm = mmIndex.get(`${chap}:${sec}`)
              const status = mm?.video_status || s.status || 'idle'
              const isActive = sel === s
              return (
                <div
                  key={`${chap}-${sec}-${i}`}
                  className={`dc-ch-list-row ${isActive ? 'is-active' : ''}`}
                  onClick={() => setSel(s)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') setSel(s)
                  }}
                >
                  <span className="dc-ch-list-idx">
                    {String(sec).padStart(2, '0')}
                  </span>
                  <div className="dc-ch-list-body">
                    <span className="dc-ch-list-title">
                      {s.title || s.heading || `第 ${sec} 节`}
                    </span>
                    <span className="dc-ch-list-meta">
                      tick {s.start_tick ?? '—'}–{s.end_tick ?? '—'} ·{' '}
                      {(s.word_count || s.words || 0).toLocaleString()} 字
                    </span>
                  </div>
                  <span className="dc-ch-list-score">
                    {typeof s.score === 'number' ? s.score.toFixed(1) : '—'}
                  </span>
                  <span
                    className={`dc-ch-list-status ${
                      status === 'completed' ? 'is-ok' : status === 'running' ? 'is-running' : ''
                    }`}
                  >
                    {labelStatus(status)}
                  </span>
                </div>
              )
            })}
            {sections.length === 0 && (
              <div style={{ font: "400 12px/1.6 'Inter', sans-serif", color: 'var(--text3)' }}>
                作品尚未切节 — 节级管线运行后会出现.
              </div>
            )}
          </div>
        </div>

        {/* —— Selected detail —— */}
        <div className="dc-ch-detail">
          {sel ? (
            <div className="dc-ch-preview" onClick={onJumpReader} role="button" tabIndex={0}>
              <div className="dc-ch-preview-head">
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
                  <span className="dc-ch-preview-heading">
                    {sel.title || sel.heading || `第 ${sel.section ?? sel.index ?? 1} 节`}
                  </span>
                  <span className="dc-ch-preview-range">
                    tick {sel.start_tick ?? '—'}–{sel.end_tick ?? '—'}
                  </span>
                </div>
                <span className="dc-ch-list-status">{labelStatus(sel.status || 'idle')}</span>
              </div>
              <p className="dc-ch-preview-body">
                {selPreview?.text || '（暂无正文 — 推进到该节区间后会自动出现）'}
              </p>
              <div className="dc-ch-preview-foot">
                <span>章节 · {sel.chapter ?? 1}</span>
                <span className="dc-ch-preview-foot-sep">·</span>
                <span>tick · {selPreview?.tick ?? sel.start_tick ?? '—'}</span>
                <span className="dc-ch-preview-cta">阅读全文 →</span>
              </div>
            </div>
          ) : (
            <div className="dc-ch-preview">
              <div className="dc-ch-preview-body">请在左侧选择一节查看详情。</div>
            </div>
          )}

          {/* mm tile grid */}
          <div>
            <div className="dc-ch-mm-head">
              <span className="dc-ch-col-kicker">多模态资产 · mimo</span>
              <span style={{ font: "400 11px/1 'Inter', sans-serif", color: 'var(--text3)' }}>
                {selManifest?.video_status || '—'}
              </span>
            </div>
            <div className="dc-ch-mm-grid" style={{ marginTop: 14 }}>
              {Array.from({ length: 4 }, (_, i) => {
                const thumb = thumbs[i]
                const seg = selManifest?.segments?.[i]
                return (
                  <div
                    key={i}
                    className={`dc-ch-mm-tile ${thumb ? 'is-loaded' : ''}`}
                  >
                    <span className="dc-ch-mm-tile-ratio">{seg?.image_size || '768×768'}</span>
                    {thumb ? (
                      <img
                        src={thumb}
                        alt={`segment ${i + 1}`}
                        className="dc-ch-mm-tile-img"
                      />
                    ) : (
                      <>
                        <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
                          <rect x="2" y="4" width="22" height="18" rx="1.5" stroke="var(--text4)" strokeWidth="1.4" />
                          <path d="M2 17 L9 11 L14 15 L18 12 L24 17" stroke="var(--text4)" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                          <circle cx="9" cy="9" r="1.6" fill="var(--text4)" />
                        </svg>
                        <span className="dc-ch-mm-tile-label">
                          {seg ? `段 ${i + 1}` : '占位'}
                        </span>
                        <span className="dc-ch-mm-tile-tag">
                          {seg ? '待生成' : '—'}
                        </span>
                      </>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function labelStatus(s) {
  if (!s) return 'idle'
  const m = String(s).toLowerCase()
  if (m === 'completed' || m === 'done' || m === 'ok') return '已完成'
  if (m === 'running') return '生成中'
  if (m === 'failed' || m === 'error') return '失败'
  if (m === 'queued' || m === 'pending') return '排队'
  return m
}
