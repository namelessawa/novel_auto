import React, { useCallback, useEffect, useState } from 'react'
import {
  downloadAuthorEvidence,
  downloadAuthorManuscript,
  fetchCommittedChapters,
} from '../../services/api'
import AsyncState, { InlineNotice } from '../components/AsyncState'
import { showToast } from '../../utils/toast'

const DEFAULT_API = {
  downloadAuthorEvidence,
  downloadAuthorManuscript,
  fetchCommittedChapters,
}

export default function ExportView({
  novel,
  api = DEFAULT_API,
  notify = showToast,
}) {
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [lastArtifact, setLastArtifact] = useState(null)

  const load = useCallback(async () => {
    if (!novel?.id) return
    setLoading(true)
    setError('')
    try {
      const result = await api.fetchCommittedChapters(novel.id)
      const chapters = result?.chapters || result?.items || []
      setSummary({
        chapters: Number(result?.total ?? chapters.length),
        chars: chapters.reduce(
          (total, chapter) =>
            total + Number(chapter.char_count || chapter.word_count || 0),
          0,
        ),
      })
    } catch (loadError) {
      setError(loadError.message || '导出摘要读取失败')
    } finally {
      setLoading(false)
    }
  }, [api, novel?.id])

  useEffect(() => {
    setSummary(null)
    setLastArtifact(null)
    load()
  }, [load])

  async function exportKind(kind) {
    setBusy(kind)
    setError('')
    try {
      const artifact = kind === 'manuscript'
        ? await api.downloadAuthorManuscript(novel.id)
        : await api.downloadAuthorEvidence(novel.id)
      saveArtifact(artifact)
      setLastArtifact({ ...artifact, kind })
      notify(kind === 'manuscript' ? '正式稿已导出' : '审计证据已导出', 'success')
    } catch (exportError) {
      setError(exportError.message || '导出失败')
    } finally {
      setBusy('')
    }
  }

  if (!novel?.id) return <AsyncState kind="empty" title="请先选择作品" />
  if (loading && !summary) return <AsyncState title="正在核对正式稿" />

  return (
    <div className="dc-view-switch dc-production-root dc-export-root">
      <header className="dc-product-masthead">
        <div>
          <span className="dc-product-eyebrow">EXPORT · COMMITTED ONLY</span>
          <h1>导出</h1>
          <p>正式稿只由 committed transaction 对应章节组成；拒绝稿和暂存稿永不进入。</p>
        </div>
      </header>
      {error && <InlineNotice kind="error">{error}</InlineNotice>}
      <section className="dc-export-summary">
        <div><span>正式章节</span><strong>{summary?.chapters || 0}</strong></div>
        <div><span>非空白字数</span><strong>{Number(summary?.chars || 0).toLocaleString()}</strong></div>
        <div><span>作品</span><strong>{novel.title || novel.id}</strong></div>
      </section>
      <div className="dc-export-grid">
        <article>
          <span>MANUSCRIPT</span>
          <h2>完整小说正式稿</h2>
          <p>按卷章顺序导出 Markdown/文本，仅包含正式提交章节。</p>
          <button type="button" className="dc-btn" disabled={Boolean(busy) || !summary?.chapters} onClick={() => exportKind('manuscript')}>
            {busy === 'manuscript' ? '导出中…' : '导出 manuscript'}
          </button>
        </article>
        <article>
          <span>EVIDENCE</span>
          <h2>生产审计证据</h2>
          <p>包含脱敏 revision、事务、校验和哈希，不包含凭据或 Provider 原始响应。</p>
          <button type="button" className="dc-btn-ghost" disabled={Boolean(busy)} onClick={() => exportKind('evidence')}>
            {busy === 'evidence' ? '导出中…' : '导出 evidence'}
          </button>
        </article>
      </div>
      {lastArtifact && (
        <section className="dc-export-receipt">
          <span>LAST EXPORT</span>
          <strong>{lastArtifact.filename}</strong>
          <code>SHA-256 {lastArtifact.sha256 || '—'}</code>
        </section>
      )}
    </div>
  )
}

function saveArtifact(artifact) {
  if (!artifact?.blob || typeof document === 'undefined') return
  const href = URL.createObjectURL(artifact.blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = artifact.filename || 'artifact'
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(href), 0)
}
