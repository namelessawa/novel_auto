import React, { useCallback, useEffect, useState } from 'react'
import {
  fetchBookOutline,
  fetchProductionSpec,
  fetchStoryBible,
  generateBookOutline,
} from '../../services/api'
import BookOutlineView from './BookOutlineView'
import StoryBibleView from './StoryBibleView'
import { showToast } from '../../utils/toast'

/**
 * 故事蓝图 — 合并「创作圣经」与「整书大纲」为同一栏。
 *
 * 创作顺序（标题优先）：
 *   1. 用户先给出作品标题；
 *   2. 由标题生成创作圣经与整书大纲的其余内容；
 *   3. 之后在下方两节中分别审阅 / 编辑圣经与大纲。
 */
export default function StoryBlueprintView({ novel, notify = showToast }) {
  const [title, setTitle] = useState('')
  const [hasOutline, setHasOutline] = useState(null)
  const [hasBible, setHasBible] = useState(null)
  const [specRevision, setSpecRevision] = useState(null)
  const [outlineRevision, setOutlineRevision] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState('')

  const novelId = novel?.id

  // 探测当前作品是否已有圣经 / 大纲，决定标题优先引导是否展示。
  const probe = useCallback(async () => {
    if (!novelId) return
    setChecking(true)
    const [bibleRes, outlineRes, specRes] = await Promise.allSettled([
      fetchStoryBible(novelId),
      fetchBookOutline(novelId),
      fetchProductionSpec(novelId),
    ])
    if (bibleRes.status === 'fulfilled') {
      const bible = bibleRes.value?.story_bible
      setHasBible(Boolean(bible))
      setTitle(bible?.title || '')
    } else {
      setHasBible(false)
    }
    if (outlineRes.status === 'fulfilled') {
      const outline =
        outlineRes.value?.book_outline ||
        outlineRes.value?.outline ||
        outlineRes.value
      setHasOutline(Boolean(outline && (outline.chapters?.length || outline.volumes?.length)))
      setOutlineRevision(outline?.revision ?? null)
    } else {
      setHasOutline(false)
    }
    if (specRes.status === 'fulfilled') {
      const spec =
        specRes.value?.production_spec ||
        specRes.value?.spec ||
        specRes.value
      setSpecRevision(spec?.revision ?? null)
    }
    setChecking(false)
  }, [novelId])

  useEffect(() => {
    setHasOutline(null)
    setHasBible(null)
    probe()
  }, [probe])

  // 标题优先生成：保存标题后生成整书大纲。
  async function generateFromTitle() {
    if (!novelId) return
    if (!title.trim()) {
      setError('请先输入作品标题')
      return
    }
    if (!specRevision) {
      setError('生产规格尚未就绪，无法生成大纲')
      return
    }
    setGenerating(true)
    setError('')
    try {
      await generateBookOutline(novelId, {
        expected_spec_revision: specRevision,
        expected_outline_revision: outlineRevision ?? undefined,
      })
      notify('已根据标题生成整书大纲', 'success')
      setHasOutline(true)
      probe()
    } catch (err) {
      setError(err.message || '生成失败，请重试')
    } finally {
      setGenerating(false)
    }
  }

  if (!novelId) {
    return <div className="dc-au-empty">请先选择作品。</div>
  }

  const showTitlePrompt = !checking && !hasOutline

  return (
    <div className="dc-blueprint-root">
      <header className="dc-product-masthead">
        <div>
          <span className="dc-product-eyebrow">STORY BLUEPRINT · 故事蓝图</span>
          <h1>故事蓝图</h1>
          <p>创作圣经与整书大纲合并于此。先给出标题，再生成其余内容。</p>
        </div>
      </header>

      {/* 标题优先引导：尚无大纲时突出标题输入与生成入口 */}
      {showTitlePrompt && (
        <section className="dc-blueprint-titleprompt dc-outline-lead">
          <label>
            <span>作品标题 · TITLE（标题优先生成）</span>
            <input
              value={title}
              placeholder="输入作品标题，由此生成圣经与大纲"
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>
          <div className="dc-masthead-actions">
            <button
              type="button"
              className="dc-btn"
              onClick={generateFromTitle}
              disabled={generating || !title.trim()}
            >
              {generating ? '生成中…' : '从标题生成蓝图'}
            </button>
          </div>
          {error && <div className="dc-au-notice is-error">{error}</div>}
        </section>
      )}

      {/* 创作圣经 */}
      <section className="dc-blueprint-section">
        <StoryBibleView novel={novel} notify={notify} />
      </section>

      {/* 整书大纲 */}
      <section className="dc-blueprint-section">
        <BookOutlineView novel={novel} notify={notify} />
      </section>
    </div>
  )
}
