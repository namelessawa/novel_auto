import React, { useEffect, useMemo, useState } from 'react'
import { fetchStoryThreads } from '../../services/api'

const STATUS_LABELS = {
  open: '待展开',
  advancing: '推进中',
  resolved: '已兑现',
  abandoned: '已放弃',
  stale: '久未触及',
  needs_attention: '需要关注',
}

export default function StoryThreadsView({ novel }) {
  const [repository, setRepository] = useState(null)
  const [status, setStatus] = useState('active')
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!novel?.id) return undefined
    let cancelled = false
    setError('')
    fetchStoryThreads(novel.id)
      .then((data) => {
        if (!cancelled) setRepository(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || '故事线加载失败')
      })
    return () => {
      cancelled = true
    }
  }, [novel?.id])

  const threads = useMemo(() => {
    const items = Object.values(repository?.threads || {})
    return items
      .filter((thread) => {
        if (status === 'active') return !['resolved', 'abandoned'].includes(thread.status)
        if (status === 'all') return true
        return thread.status === status
      })
      .filter((thread) => {
        if (!query.trim()) return true
        return JSON.stringify(thread).toLowerCase().includes(query.trim().toLowerCase())
      })
      .sort((a, b) => (b.urgency || 0) - (a.urgency || 0))
  }, [repository, status, query])

  if (!novel?.id) return <div className="dc-au-empty">请先选择作品。</div>

  return (
    <div className="dc-view-switch dc-au-root">
      <header className="dc-au-masthead">
        <div>
          <span className="dc-au-eyebrow">STORY THREADS · 叙事承诺账本</span>
          <h1>故事线</h1>
          <p>故事线不会因为超时而自动“解决”。关闭必须有正文中的兑现证据。</p>
        </div>
        <span className="dc-au-revision">REV {repository?.revision || '—'}</span>
      </header>
      {error && <div className="dc-au-notice is-error">{error}</div>}

      <div className="dc-au-thread-toolbar">
        <div className="dc-au-segmented">
          {[
            ['active', '活跃'],
            ['needs_attention', '需关注'],
            ['resolved', '已兑现'],
            ['all', '全部'],
          ].map(([key, label]) => (
            <button
              type="button"
              className={status === key ? 'is-active' : ''}
              onClick={() => setStatus(key)}
              key={key}
            >
              {label}
            </button>
          ))}
        </div>
        <input
          className="dc-au-thread-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="筛选人物、承诺或来源…"
        />
      </div>

      <div className="dc-au-thread-list">
        {threads.map((thread, index) => (
          <article className="dc-au-thread" key={thread.id}>
            <div className="dc-au-thread-index">{String(index + 1).padStart(2, '0')}</div>
            <div className="dc-au-thread-main">
              <div className="dc-au-thread-head">
                <span className={`dc-au-thread-status is-${thread.status}`}>
                  {STATUS_LABELS[thread.status] || thread.status}
                </span>
                <span>{thread.type}</span>
                <code>{thread.id}</code>
              </div>
              <h2>{thread.description}</h2>
              {thread.promised_question && <blockquote>{thread.promised_question}</blockquote>}
              <div className="dc-au-thread-meta">
                <span>人物 · {(thread.involved_characters || []).join('、') || '未绑定'}</span>
                <span>来源 · {(thread.origin_refs || []).join('、') || 'author'}</span>
              </div>
              {(thread.resolution_requirements || []).length > 0 && (
                <div className="dc-au-thread-evidence">
                  <strong>兑现要求</strong>
                  {(thread.resolution_requirements || []).map((item) => <span key={item}>{item}</span>)}
                </div>
              )}
              {(thread.resolution_evidence || []).length > 0 && (
                <div className="dc-au-thread-evidence is-proof">
                  <strong>正文证据</strong>
                  {(thread.resolution_evidence || []).map((item) => <span key={item}>{item}</span>)}
                </div>
              )}
            </div>
            <div className="dc-au-urgency" style={{ '--urgency': `${(thread.urgency || 0) * 10}%` }}>
              <span>URGENCY</span>
              <strong>{thread.urgency || 0}</strong>
              <i />
            </div>
          </article>
        ))}
        {threads.length === 0 && (
          <div className="dc-au-empty">当前筛选下没有故事线。Writer 可提出新线，Validator 负责确认。</div>
        )}
      </div>
    </div>
  )
}
