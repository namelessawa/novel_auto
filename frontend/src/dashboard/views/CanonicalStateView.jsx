import React, { useEffect, useMemo, useState } from 'react'
import { fetchCanonicalState, fetchStoryThreads } from '../../services/api'

const DEFAULT_API = { fetchCanonicalState, fetchStoryThreads }

export default function CanonicalStateView({ novel, api = DEFAULT_API }) {
  const [state, setState] = useState(null)
  const [threads, setThreads] = useState({})
  const [migration, setMigration] = useState(null)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!novel?.id) return undefined
    let cancelled = false
    setLoading(true)
    setError('')
    Promise.all([api.fetchCanonicalState(novel.id), api.fetchStoryThreads(novel.id)])
      .then(([canonical, storyThreads]) => {
        if (cancelled) return
        setState(canonical.canonical_state)
        setMigration(canonical.migration)
        setThreads(storyThreads.threads || {})
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || '权威状态加载失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [novel?.id, api])

  const characters = useMemo(
    () => filterEntries(state?.characters || {}, query),
    [state?.characters, query],
  )
  const items = useMemo(
    () => filterEntries(state?.items || {}, query),
    [state?.items, query],
  )
  const activeThreads = Object.values(threads).filter(
    (thread) => !['resolved', 'abandoned'].includes(thread.status),
  )

  if (!novel?.id) return <StateEmpty text="请先选择作品。" />
  if (loading) return <StateEmpty text="正在核对权威账本…" />
  if (!state) return <StateEmpty text={error || '权威状态暂不可用。'} />

  return (
    <div className="dc-view-switch dc-au-root">
      <header className="dc-au-masthead is-state">
        <div>
          <span className="dc-au-eyebrow">CANONICAL STATE · 唯一当前事实源</span>
          <h1>当前故事状态</h1>
          <p>这里记录“现在是真的什么”。历史摘要和知识图谱只能引用，不能覆盖。</p>
        </div>
        <div className="dc-au-state-stamp">
          <span>REVISION</span>
          <strong>{String(state.revision).padStart(4, '0')}</strong>
          <em>WORLD · {state.world_time}</em>
        </div>
      </header>

      {migration?.status === 'partial' && (
        <div className="dc-au-notice is-error">部分旧数据损坏；已保留原文件并使用可验证内容。</div>
      )}

      <div className="dc-au-ledger-bar">
        <div className="dc-au-ledger-metrics">
          <Metric value={Object.keys(state.characters || {}).length} label="人物" />
          <Metric value={Object.keys(state.items || {}).length} label="物品" />
          <Metric value={activeThreads.length} label="活跃故事线" />
          <Metric value={Object.keys(state.canonical_facts || {}).length} label="确认事实" />
        </div>
        <label className="dc-au-search">
          <span>筛选账本</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="人物、物品、地点…"
          />
        </label>
      </div>

      <section className="dc-au-ledger-section">
        <div className="dc-au-ledger-title">
          <span>01</span>
          <h2>人物位置、状态与知识边界</h2>
        </div>
        <div className="dc-au-character-grid">
          {characters.map(([id, character]) => (
            <details className="dc-au-entity" key={id} open={characters.length <= 4}>
              <summary>
                <div>
                  <strong>{character.name || id}</strong>
                  <span>{id}</span>
                </div>
                <em className={character.alive === false ? 'is-danger' : 'is-ok'}>
                  {character.alive === false ? '已死亡' : '存活'}
                </em>
              </summary>
              <div className="dc-au-entity-body">
                <Fact label="当前位置" value={character.location || character.current_location || '未记录'} />
                <Fact label="伤势 / 状态" value={listValue(character.injuries || character.status_effects)} />
                <Fact label="持有物" value={listValue(character.inventory)} />
                <Fact label="情绪" value={character.emotional_state || '未记录'} />
                <div className="dc-au-knowledge">
                  <span>该角色知道</span>
                  <ul>
                    {(state.character_knowledge?.[id] || []).map((fact) => <li key={String(fact)}>{String(fact)}</li>)}
                    {(state.character_knowledge?.[id] || []).length === 0 && <li>尚无明确知识记录</li>}
                  </ul>
                </div>
              </div>
            </details>
          ))}
          {characters.length === 0 && <div className="dc-au-inline-empty">没有匹配人物。</div>}
        </div>
      </section>

      <section className="dc-au-ledger-section">
        <div className="dc-au-ledger-title">
          <span>02</span>
          <h2>物品归属</h2>
        </div>
        <div className="dc-au-table-wrap">
          <table className="dc-au-table">
            <thead>
              <tr><th>物品</th><th>数量</th><th>当前持有者</th><th>状态 / 地点</th></tr>
            </thead>
            <tbody>
              {items.map(([id, item]) => (
                <tr key={id}>
                  <td><strong>{item.name || id}</strong></td>
                  <td>{item.quantity ?? 1}</td>
                  <td>{listValue(item.owners || item.owner)}</td>
                  <td>{item.status || item.location || '完好 / 未注明'}</td>
                </tr>
              ))}
              {items.length === 0 && <tr><td colSpan={4}>没有匹配物品。</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <div className="dc-au-state-columns">
        <StateBlock title="读者已知边界" value={state.reader_knowledge} />
        <StateBlock title="当前剧情位置" value={state.plot_position} />
        <StateBlock title="上一节连续性" value={state.last_scene_state} />
        <StateBlock title="人物关系" value={state.relationships} />
      </div>

      <div className="dc-au-derivation-note">
        <strong>派生视图说明</strong>
        <span>知识图谱由此状态生成，仅用于浏览与诊断；它不是第二套权威事实。</span>
      </div>
    </div>
  )
}

function filterEntries(record, query) {
  const needle = query.trim().toLowerCase()
  return Object.entries(record).filter(([id, value]) => {
    if (!needle) return true
    return `${id} ${JSON.stringify(value)}`.toLowerCase().includes(needle)
  })
}

function listValue(value) {
  if (Array.isArray(value)) return value.length ? value.join('、') : '无'
  if (value && typeof value === 'object') return Object.keys(value).join('、') || '无'
  return value || '无'
}

function Fact({ label, value }) {
  return <div className="dc-au-fact"><span>{label}</span><strong>{String(value)}</strong></div>
}

function Metric({ value, label }) {
  return <div><strong>{value}</strong><span>{label}</span></div>
}

function StateBlock({ title, value }) {
  return (
    <details className="dc-au-state-block">
      <summary>{title}<span>{Object.keys(value || {}).length}</span></summary>
      <pre>{JSON.stringify(value || {}, null, 2)}</pre>
    </details>
  )
}

function StateEmpty({ text }) {
  return <div className="dc-au-empty">{text}</div>
}
