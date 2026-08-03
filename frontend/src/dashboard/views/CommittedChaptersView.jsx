import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  downloadAuthorManuscript,
  fetchCommittedChapter,
  fetchCommittedChapters,
} from '../../services/api'
import AsyncState, { InlineNotice } from '../components/AsyncState'
import { showToast } from '../../utils/toast'

const DEFAULT_API = {
  downloadAuthorManuscript,
  fetchCommittedChapter,
  fetchCommittedChapters,
}

export function isCommittedChapter(chapter) {
  if (!chapter) return false
  const status = String(chapter.status || chapter.phase || '').toLowerCase()
  if (status) return status === 'committed' && chapter.committed !== false
  return chapter.committed === true
}

export function isCommittedSection(section) {
  if (!section) return false
  const status = String(section.status || section.phase || '').toLowerCase()
  if (status) return status === 'committed' && section.committed !== false
  return (
    section.committed === true ||
    (
      section.validation_passed === true &&
      Boolean(section.committed_at) &&
      Boolean(section.transaction_id)
    )
  )
}

export default function CommittedChaptersView({
  novel,
  api = DEFAULT_API,
  notify = showToast,
}) {
  const [chapters, setChapters] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [detail, setDetail] = useState(null)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')
  const [exportBusy, setExportBusy] = useState(false)

  const load = useCallback(async () => {
    if (!novel?.id) return
    setLoading(true)
    setError('')
    try {
      const result = await api.fetchCommittedChapters(novel.id)
      const rows = (
        result?.chapters ||
        result?.items ||
        []
      ).filter(isCommittedChapter)
      rows.sort((a, b) =>
        (a.ordinal ?? a.chapter ?? 0) - (b.ordinal ?? b.chapter ?? 0),
      )
      setChapters(rows)
      setSelectedId((current) =>
        rows.some((item) => chapterId(item) === current)
          ? current
          : rows[0] ? chapterId(rows[0]) : '',
      )
    } catch (loadError) {
      setError(loadError.message || '正式章节读取失败')
    } finally {
      setLoading(false)
    }
  }, [api, novel?.id])

  useEffect(() => {
    setChapters([])
    setSelectedId('')
    setDetail(null)
    load()
  }, [load])

  useEffect(() => {
    if (!novel?.id || !selectedId) {
      setDetail(null)
      return undefined
    }
    let cancelled = false
    setDetailLoading(true)
    setError('')
    api.fetchCommittedChapter(novel.id, selectedId)
      .then((result) => {
        if (cancelled) return
        const next =
          result?.chapter ||
          result?.committed_chapter ||
          result
        if (!isCommittedChapter(next)) {
          setDetail(null)
          setError('后端拒绝展示未正式提交的候选正文。')
          return
        }
        setDetail(next)
      })
      .catch((detailError) => {
        if (!cancelled) {
          setDetail(null)
          setError(detailError.message || '章节正文读取失败')
        }
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [api, novel?.id, selectedId])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return chapters
    return chapters.filter((chapter) => [
      chapter.title,
      chapter.objective,
      chapter.viewpoint_character_id,
      chapter.location_id,
      chapter.ordinal,
    ].some((value) => String(value || '').toLowerCase().includes(needle)))
  }, [chapters, query])

  const selectedIndex = chapters.findIndex(
    (item) => chapterId(item) === selectedId,
  )

  async function exportManuscript() {
    setExportBusy(true)
    setError('')
    try {
      const artifact = await api.downloadAuthorManuscript(novel.id)
      saveArtifact(artifact)
      notify(
        `正式稿已导出${artifact?.sha256 ? ` · ${artifact.sha256.slice(0, 12)}…` : ''}`,
        'success',
      )
    } catch (exportError) {
      setError(exportError.message || '正式稿导出失败')
    } finally {
      setExportBusy(false)
    }
  }

  if (!novel?.id) return <AsyncState kind="empty" title="请先选择作品" />
  if (loading && chapters.length === 0) {
    return <AsyncState title="正在装订正式章节" />
  }

  return (
    <div className="dc-view-switch dc-production-root dc-committed-root" data-testid="committed-chapters">
      <header className="dc-product-masthead">
        <div>
          <span className="dc-product-eyebrow">COMMITTED MANUSCRIPT ONLY</span>
          <h1>章节</h1>
          <p>只显示通过 Validator 且事务 phase=committed 的正式章节。</p>
        </div>
        <button type="button" className="dc-btn" onClick={exportManuscript} disabled={exportBusy || chapters.length === 0}>
          {exportBusy ? '导出中…' : '导出正式稿'}
        </button>
      </header>

      {error && (
        <InlineNotice
          kind="error"
          actions={<button type="button" onClick={load}>重新读取</button>}
        >
          {error}
        </InlineNotice>
      )}

      {chapters.length === 0 ? (
        <AsyncState
          kind="empty"
          title="尚无正式提交章节"
          detail="开始整书生产后，只有完整提交的章节才会出现在这里。"
        />
      ) : (
        <div className="dc-committed-layout">
          <aside className="dc-committed-toc">
            <label className="dc-chapter-search">
              <span aria-hidden="true">⌕</span>
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索章名、POV、地点"
                aria-label="搜索正式章节"
              />
            </label>
            <div>
              {filtered.map((chapter) => {
                const id = chapterId(chapter)
                return (
                  <button
                    type="button"
                    key={id}
                    className={id === selectedId ? 'is-active' : ''}
                    onClick={() => setSelectedId(id)}
                  >
                    <span>{String(chapter.ordinal ?? chapter.chapter ?? 0).padStart(3, '0')}</span>
                    <div>
                      <strong>{chapter.title || `第 ${chapter.ordinal || chapter.chapter} 章`}</strong>
                      <p>{Number(chapter.char_count || chapter.word_count || 0).toLocaleString()} 字 · {chapter.viewpoint_character_id || '多视角'}</p>
                    </div>
                  </button>
                )
              })}
              {filtered.length === 0 && (
                <p className="dc-committed-no-search">没有匹配的正式章节。</p>
              )}
            </div>
          </aside>

          <main className="dc-chapter-reader">
            {detailLoading ? (
              <AsyncState compact title="正在读取章节正文" />
            ) : detail ? (
              <>
                <header>
                  <span>第 {detail.ordinal ?? detail.chapter ?? selectedIndex + 1} 章</span>
                  <h2>{detail.title || '未命名章节'}</h2>
                  <ChapterMetadata chapter={detail} />
                </header>
                <article>
                  {chapterContent(detail).split(/\n{2,}/).filter(Boolean).map((paragraph, index) => (
                    <p key={`${index}-${paragraph.slice(0, 12)}`}>{paragraph}</p>
                  ))}
                </article>
                <footer>
                  <button
                    type="button"
                    className="dc-btn-ghost"
                    disabled={selectedIndex <= 0}
                    onClick={() => setSelectedId(chapterId(chapters[selectedIndex - 1]))}
                  >
                    ← 上一章
                  </button>
                  <span>{selectedIndex + 1} / {chapters.length}</span>
                  <button
                    type="button"
                    className="dc-btn-ghost"
                    disabled={selectedIndex < 0 || selectedIndex >= chapters.length - 1}
                    onClick={() => setSelectedId(chapterId(chapters[selectedIndex + 1]))}
                  >
                    下一章 →
                  </button>
                </footer>
              </>
            ) : (
              <AsyncState kind="empty" compact title="选择一章开始阅读" />
            )}
          </main>
        </div>
      )}
    </div>
  )
}

export function chapterMetadata(chapter = {}) {
  const transactionIds = Array.isArray(chapter.transaction_ids)
    ? chapter.transaction_ids.filter(Boolean).map(String)
    : []
  const representativeTransaction =
    chapter.transaction_id || chapter.committed_transaction_id
  if (!transactionIds.length && representativeTransaction) {
    transactionIds.push(String(representativeTransaction))
  }
  const storyBibleStart =
    chapter.story_bible_revision_start ?? chapter.story_bible_revision
  const storyBibleEnd =
    chapter.story_bible_revision_end ?? chapter.story_bible_revision
  const canonicalStart =
    chapter.canonical_revision_start ??
    chapter.canonical_state_revision ??
    chapter.canonical_revision
  const canonicalEnd =
    chapter.canonical_revision_end ??
    chapter.canonical_state_revision ??
    chapter.canonical_revision
  const repairPerformed = chapter.repair_performed != null
    ? Boolean(chapter.repair_performed)
    : (
        Number(chapter.repair_total || 0) > 0 ||
        (chapter.sections || []).some((section) => section.repair_performed)
      )
  return {
    transactionIds,
    transactionLabel: transactionIds.length > 1
      ? `${transactionIds.length} 个 · ${shortId(transactionIds.at(-1))}`
      : shortId(transactionIds[0]),
    storyBibleRevision: revisionRange(storyBibleStart, storyBibleEnd),
    canonicalRevision: revisionRange(canonicalStart, canonicalEnd),
    repairPerformed,
  }
}

function ChapterMetadata({ chapter }) {
  const metadata = chapterMetadata(chapter)
  const style =
    chapter.style_profile ||
    chapter.style_snapshot ||
    {}
  const validation =
    chapter.validation_report ||
    chapter.validation ||
    {}
  return (
    <dl className="dc-chapter-meta">
      <div><dt>字数</dt><dd>{Number(chapter.char_count || chapter.word_count || 0).toLocaleString()}</dd></div>
      <div><dt>事务</dt><dd title={metadata.transactionIds.join(', ')}>{metadata.transactionLabel}</dd></div>
      <div><dt>风格</dt><dd>{style.name || chapter.style_profile_name || '—'} · R{style.revision || chapter.style_profile_revision || '—'}</dd></div>
      <div><dt>Bible / Canon</dt><dd>R{metadata.storyBibleRevision} / R{metadata.canonicalRevision}</dd></div>
      <div><dt>校验</dt><dd>{validation.accepted === false ? '未通过' : '已通过'}</dd></div>
      <div><dt>Repair</dt><dd>{metadata.repairPerformed ? '是' : '否'}</dd></div>
    </dl>
  )
}

function chapterId(chapter) {
  return String(chapter?.id || chapter?.chapter_id || chapter?.ordinal || '')
}

export function chapterContent(chapter) {
  if (typeof chapter.content === 'string') return chapter.content
  if (typeof chapter.text === 'string') return chapter.text
  return (chapter.sections || [])
    .filter(isCommittedSection)
    .map((section) => section.content || section.text || '')
    .filter(Boolean)
    .join('\n\n')
}

function shortId(value) {
  if (!value) return '—'
  const text = String(value)
  return text.length > 12 ? `${text.slice(0, 10)}…` : text
}

function revisionRange(start, end) {
  const first = Number(start || 0)
  const last = Number(end || 0)
  if (!first && !last) return '—'
  if (first && last && first !== last) return `${first}→${last}`
  return String(last || first)
}

function saveArtifact(artifact) {
  if (!artifact?.blob || typeof document === 'undefined') return
  const href = URL.createObjectURL(artifact.blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = artifact.filename || 'manuscript.md'
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(href), 0)
}
