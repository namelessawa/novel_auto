import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchAuthorMemories,
  fetchStoryThreads,
} from '../../services/api'
import AsyncState, { InlineNotice } from '../components/AsyncState'

const DEFAULT_API = { fetchAuthorMemories, fetchStoryThreads }

export default function ThreadsMemoryView({ novel, api = DEFAULT_API }) {
  const [threads, setThreads] = useState([])
  const [memories, setMemories] = useState([])
  const [memoryRevision, setMemoryRevision] = useState(0)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!novel?.id) return
    setLoading(true)
    setError('')
    const [threadResult, memoryResult] = await Promise.allSettled([
      api.fetchStoryThreads(novel.id),
      api.fetchAuthorMemories(novel.id, 300),
    ])
    if (threadResult.status === 'fulfilled') {
      const raw = threadResult.value?.threads || {}
      setThreads(Array.isArray(raw) ? raw : Object.values(raw))
    } else {
      setError(threadResult.reason?.message || '故事线读取失败')
    }
    if (memoryResult.status === 'fulfilled') {
      setMemories(memoryResult.value?.records || memoryResult.value?.memories || [])
      setMemoryRevision(memoryResult.value?.revision || 0)
    }
    setLoading(false)
  }, [api, novel?.id])

  useEffect(() => {
    setThreads([])
    setMemories([])
    load()
  }, [load])

  const needle = query.trim().toLowerCase()
  const filteredThreads = useMemo(
    () => threads.filter((item) => !needle || JSON.stringify(item).toLowerCase().includes(needle)),
    [needle, threads],
  )
  const filteredMemories = useMemo(
    () => memories.filter((item) => !needle || JSON.stringify(item).toLowerCase().includes(needle)),
    [memories, needle],
  )

  if (!novel?.id) return <AsyncState kind="empty" title="请先选择作品" />
  if (loading && !threads.length && !memories.length) {
    return <AsyncState title="正在检索故事线与记忆" />
  }

  return (
    <div className="dc-view-switch dc-production-root dc-memory-root">
      <header className="dc-product-masthead">
        <div>
          <span className="dc-product-eyebrow">THREADS · MEMORY R{memoryRevision}</span>
          <h1>故事线与记忆</h1>
          <p>Memory 只参与检索；CanonicalState 仍是唯一当前事实源。</p>
        </div>
        <label className="dc-memory-search">
          <span>⌕</span>
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索故事线、实体或摘要" />
        </label>
      </header>
      {error && <InlineNotice kind="error">{error}</InlineNotice>}
      <div className="dc-memory-grid">
        <section>
          <header><span>ACTIVE THREADS</span><strong>{filteredThreads.length}</strong></header>
          <div>
            {filteredThreads.map((thread) => (
              <article key={thread.id || thread.description}>
                <div><code>{thread.id || 'thread'}</code><em>{thread.status || 'open'}</em></div>
                <strong>{thread.description || thread.title || thread.id}</strong>
                <p>urgency {thread.urgency ?? '—'} · progress R{thread.last_progress_revision ?? thread.last_advanced_revision ?? '—'}</p>
              </article>
            ))}
            {!filteredThreads.length && <p className="dc-list-empty">没有匹配的故事线。</p>}
          </div>
        </section>
        <section>
          <header><span>RETRIEVAL MEMORY</span><strong>{filteredMemories.length}</strong></header>
          <div>
            {filteredMemories.map((memory) => (
              <article key={memory.id}>
                <div><code>{memory.type || 'memory'} · R{memory.created_at_revision || 0}</code><em>{memory.canon_status || 'confirmed'}</em></div>
                <strong>{memory.summary || memory.id}</strong>
                <p>{(memory.entities || []).join(' · ') || memory.section_id || '—'} · importance {memory.importance ?? '—'}</p>
              </article>
            ))}
            {!filteredMemories.length && <p className="dc-list-empty">没有匹配的检索记忆。</p>}
          </div>
        </section>
      </div>
    </div>
  )
}
