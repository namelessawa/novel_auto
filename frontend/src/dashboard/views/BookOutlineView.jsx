import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchBookOutline,
  fetchProductionSpec,
  generateBookOutline,
  saveBookOutline,
} from '../../services/api'
import AsyncState, { InlineNotice } from '../components/AsyncState'
import { showToast } from '../../utils/toast'

const DEFAULT_API = {
  fetchBookOutline,
  fetchProductionSpec,
  generateBookOutline,
  saveBookOutline,
}

export function moveChapter(chapters, chapterId, direction) {
  const rows = [...chapters].sort((a, b) => a.ordinal - b.ordinal)
  const index = rows.findIndex((item) => item.id === chapterId)
  const target = index + direction
  if (index < 0 || target < 0 || target >= rows.length) return chapters
  if (isCommitted(rows[index]) || isCommitted(rows[target])) return chapters
  const next = [...rows]
  ;[next[index], next[target]] = [next[target], next[index]]
  return next.map((item, idx) => ({ ...item, ordinal: idx + 1 }))
}

export function outlineChangeSummary(original, current) {
  if (!original || !current) return []
  const notes = []
  if (original.logline !== current.logline) notes.push('故事主线')
  if (original.global_arc !== current.global_arc) notes.push('全局弧线')
  const originalById = new Map((original.chapters || []).map((item) => [item.id, item]))
  let edited = 0
  let moved = 0
  for (const chapter of current.chapters || []) {
    const before = originalById.get(chapter.id)
    if (!before) continue
    if (before.ordinal !== chapter.ordinal) moved += 1
    if (
      before.objective !== chapter.objective ||
      before.viewpoint_character_id !== chapter.viewpoint_character_id ||
      before.location_id !== chapter.location_id ||
      Number(before.target_chars) !== Number(chapter.target_chars)
    ) edited += 1
  }
  if (edited) notes.push(`${edited} 章目标`)
  if (moved) notes.push(`${moved} 章顺序`)
  return notes
}

export default function BookOutlineView({
  novel,
  api = DEFAULT_API,
  notify = showToast,
}) {
  const [outline, setOutline] = useState(null)
  const [original, setOriginal] = useState(null)
  const [spec, setSpec] = useState(null)
  const [folded, setFolded] = useState({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!novel?.id) return
    setLoading(true)
    setError('')
    const [outlineResult, specResult] = await Promise.allSettled([
      api.fetchBookOutline(novel.id),
      api.fetchProductionSpec(novel.id),
    ])
    if (outlineResult.status === 'fulfilled') {
      const data =
        outlineResult.value?.book_outline ||
        outlineResult.value?.outline ||
        outlineResult.value
      setOutline(data)
      setOriginal(structuredCloneSafe(data))
    } else if (outlineResult.reason?.status !== 404) {
      setError(outlineResult.reason?.message || '整书大纲读取失败')
    }
    if (specResult.status === 'fulfilled') {
      setSpec(
        specResult.value?.production_spec ||
        specResult.value?.spec ||
        specResult.value,
      )
    }
    setLoading(false)
  }, [api, novel?.id])

  useEffect(() => {
    setOutline(null)
    setOriginal(null)
    load()
  }, [load])

  const changes = useMemo(
    () => outlineChangeSummary(original, outline),
    [original, outline],
  )

  async function generate() {
    setGenerating(true)
    setError('')
    try {
      const result = await api.generateBookOutline(novel.id, {
        expected_spec_revision: spec?.revision,
        expected_outline_revision: outline?.revision,
      })
      const next =
        result?.book_outline || result?.outline || result
      setOutline(next)
      setOriginal(structuredCloneSafe(next))
      notify('整书大纲已生成', 'success')
    } catch (generateError) {
      setError(generateError.message || '整书大纲生成失败')
    } finally {
      setGenerating(false)
    }
  }

  async function save() {
    if (!changes.length || saving) return
    if (!window.confirm(`将保存以下变更：${changes.join('、')}。继续？`)) return
    setSaving(true)
    setError('')
    try {
      const result = await api.saveBookOutline(
        novel.id,
        editableOutlinePayload(outline),
      )
      const next =
        result?.book_outline || result?.outline || result
      setOutline(next)
      setOriginal(structuredCloneSafe(next))
      notify(`整书大纲已保存 · revision ${next.revision}`, 'success')
    } catch (saveError) {
      setError(
        saveError.code === 'REVISION_CONFLICT'
          ? '大纲已在另一个会话更新。请重新载入后合并变更。'
          : saveError.message || '大纲保存失败',
      )
    } finally {
      setSaving(false)
    }
  }

  function updateChapter(id, patch) {
    setOutline((current) => ({
      ...current,
      chapters: current.chapters.map((item) =>
        item.id === id && !isCommitted(item) ? { ...item, ...patch } : item,
      ),
    }))
  }

  function reorder(id, direction) {
    setOutline((current) => ({
      ...current,
      chapters: moveChapter(current.chapters || [], id, direction),
    }))
  }

  if (!novel?.id) {
    return <AsyncState kind="empty" title="请先选择作品" />
  }
  if (loading && !outline) return <AsyncState title="正在展开整书大纲" />
  if (!outline) {
    return (
      <AsyncState
        kind={error ? 'error' : 'empty'}
        title={error || '这部作品还没有整书大纲'}
        detail="生成一次结构化大纲后，可逐章调整目标与顺序。"
        actionLabel={generating ? '生成中…' : '生成整书大纲'}
        onAction={generating ? undefined : generate}
      />
    )
  }

  const volumes = [...(outline.volumes || [])].sort(
    (a, b) => a.ordinal - b.ordinal,
  )
  const chapters = [...(outline.chapters || [])].sort(
    (a, b) => a.ordinal - b.ordinal,
  )

  return (
    <div className="dc-view-switch dc-production-root dc-outline-root" data-testid="book-outline">
      <header className="dc-product-masthead">
        <div>
          <span className="dc-product-eyebrow">BOOK OUTLINE · R{outline.revision}</span>
          <h1>整书大纲</h1>
          <p>{outline.logline || '按卷规划整本书，并冻结已提交章节的顺序。'}</p>
        </div>
        <div className="dc-masthead-actions">
          <button type="button" className="dc-btn-ghost" onClick={generate} disabled={generating || saving}>
            {generating ? '重新规划中…' : '重新生成'}
          </button>
          <button type="button" className="dc-btn" onClick={save} disabled={!changes.length || saving}>
            {saving ? '保存中…' : changes.length ? `保存 ${changes.length} 类变更` : '没有变更'}
          </button>
        </div>
      </header>

      {error && (
        <InlineNotice
          kind="error"
          actions={error.includes('另一个会话') ? <button type="button" onClick={load}>载入最新版本</button> : null}
        >
          {error}
        </InlineNotice>
      )}

      <section className="dc-outline-lead">
        <label>
          <span>LOGLINE</span>
          <textarea
            rows={2}
            value={outline.logline || ''}
            onChange={(event) => setOutline((current) => ({ ...current, logline: event.target.value }))}
          />
        </label>
        <label>
          <span>GLOBAL ARC</span>
          <textarea
            rows={3}
            value={outline.global_arc || ''}
            onChange={(event) => setOutline((current) => ({ ...current, global_arc: event.target.value }))}
          />
        </label>
        {changes.length > 0 && (
          <div className="dc-outline-change-summary">
            <span>待保存变更</span>
            <strong>{changes.join(' · ')}</strong>
          </div>
        )}
      </section>

      <div className="dc-volume-list">
        {volumes.map((volume) => {
          const isFolded = Boolean(folded[volume.id])
          const volumeChapters = chapters.filter(
            (chapter) => chapter.volume_id === volume.id,
          )
          return (
            <section className="dc-volume-card" key={volume.id}>
              <button
                type="button"
                className="dc-volume-head"
                onClick={() =>
                  setFolded((current) => ({
                    ...current,
                    [volume.id]: !current[volume.id],
                  }))
                }
                aria-expanded={!isFolded}
              >
                <span>{String(volume.ordinal).padStart(2, '0')}</span>
                <div>
                  <strong>{volume.title}</strong>
                  <p>{volume.objective}</p>
                </div>
                <em>{volumeChapters.length} 章 · {Number(volume.target_chars || 0).toLocaleString()} 字</em>
                <b>{isFolded ? '＋' : '−'}</b>
              </button>
              {!isFolded && (
                <div className="dc-outline-chapters">
                  {volumeChapters.map((chapter, index) => (
                    <ChapterOutlineCard
                      key={chapter.id}
                      chapter={chapter}
                      first={index === 0 && chapter.ordinal === 1}
                      last={chapter.ordinal === chapters.length}
                      onChange={(patch) => updateChapter(chapter.id, patch)}
                      onMoveUp={() => reorder(chapter.id, -1)}
                      onMoveDown={() => reorder(chapter.id, 1)}
                    />
                  ))}
                </div>
              )}
            </section>
          )
        })}
      </div>
    </div>
  )
}

function ChapterOutlineCard({
  chapter,
  first,
  last,
  onChange,
  onMoveUp,
  onMoveDown,
}) {
  const committed = isCommitted(chapter)
  return (
    <article className={`dc-outline-chapter ${committed ? 'is-committed' : ''}`}>
      <div className="dc-outline-chapter-order">
        <strong>{String(chapter.ordinal).padStart(3, '0')}</strong>
        <div>
          <button type="button" onClick={onMoveUp} disabled={first || committed} aria-label="上移章节">↑</button>
          <button type="button" onClick={onMoveDown} disabled={last || committed} aria-label="下移章节">↓</button>
        </div>
      </div>
      <div className="dc-outline-chapter-copy">
        <div className="dc-outline-chapter-title">
          <input
            value={chapter.title || ''}
            disabled={committed}
            onChange={(event) => onChange({ title: event.target.value })}
          />
          <span className={committed ? 'is-locked' : ''}>
            {committed ? '已提交 · 顺序锁定' : chapter.status || 'draft'}
          </span>
        </div>
        <textarea
          rows={3}
          value={chapter.objective || ''}
          disabled={committed}
          onChange={(event) => onChange({ objective: event.target.value })}
          placeholder="本章必须完成的故事目标"
        />
        <div className="dc-outline-chapter-fields">
          <label><span>POV</span><input value={chapter.viewpoint_character_id || ''} disabled={committed} onChange={(e) => onChange({ viewpoint_character_id: e.target.value })} /></label>
          <label><span>地点</span><input value={chapter.location_id || ''} disabled={committed} onChange={(e) => onChange({ location_id: e.target.value })} /></label>
          <label><span>人物</span><input value={(chapter.involved_characters || []).join(', ')} disabled={committed} onChange={(e) => onChange({ involved_characters: splitCsv(e.target.value) })} /></label>
          <label><span>故事线</span><input value={(chapter.target_threads || []).join(', ')} disabled={committed} onChange={(e) => onChange({ target_threads: splitCsv(e.target.value) })} /></label>
          <label><span>目标字数</span><input type="number" min="500" value={chapter.target_chars || 0} disabled={committed} onChange={(e) => onChange({ target_chars: Number(e.target.value) })} /></label>
        </div>
      </div>
    </article>
  )
}

function isCommitted(chapter) {
  return (
    chapter?.status === 'committed' ||
    (chapter?.committed_section_ids || []).length > 0
  )
}

function splitCsv(value) {
  return value.split(/[,，]/).map((item) => item.trim()).filter(Boolean)
}

function editableOutlinePayload(outline) {
  const {
    logline,
    global_arc,
    volumes,
    chapters,
    ending_target,
    major_turning_points,
    central_conflict_progression,
    thread_schedule,
    character_arc_schedule,
  } = outline
  return {
    expected_revision: outline.revision,
    logline,
    global_arc,
    volumes,
    chapters,
    ending_target,
    major_turning_points,
    central_conflict_progression,
    thread_schedule,
    character_arc_schedule,
  }
}

function structuredCloneSafe(value) {
  if (typeof structuredClone === 'function') return structuredClone(value)
  return JSON.parse(JSON.stringify(value))
}
