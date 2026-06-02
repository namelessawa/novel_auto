import React, { useState, useEffect } from 'react'
import { fetchSections } from '../services/api'

export default function SectionsList({ refreshKey }) {
  const [sections, setSections] = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadSections()
  }, [refreshKey])

  const loadSections = async () => {
    setLoading(true)
    try {
      const data = await fetchSections()
      setSections(data.sections || [])
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  if (loading) {
    return <div className="card"><p style={{ color: 'var(--text-muted)' }}>加载中…</p></div>
  }

  if (sections.length === 0) {
    return (
      <div className="card">
        <p style={{ color: 'var(--text-muted)' }}>尚未生成任何章节。请前往"生成"标签开始创作。</p>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', gap: 16 }}>
      <div className="card" style={{ width: 320, flexShrink: 0 }}>
        <div className="card-title">章节列表 ({sections.length})</div>
        {sections.map((s, i) => (
          <div
            key={i}
            className="section-item"
            style={{
              background: selected === i ? 'var(--bg-hover)' : undefined,
            }}
            onClick={() => setSelected(i)}
          >
            <div className="section-header">
              <span className="section-title">
                第{s.chapter}章 第{s.section}节
              </span>
              <span className="section-meta">{s.word_count}字</span>
            </div>
            {s.summary && (
              <div className="section-summary">{s.summary}</div>
            )}
          </div>
        ))}
      </div>

      <div className="card" style={{ flex: 1 }}>
        {selected !== null && sections[selected] ? (
          <>
            <div className="card-title">
              第{sections[selected].chapter}章 第{sections[selected].section}节 — {sections[selected].title}
            </div>
            <div className="generated-text" style={{ maxHeight: 'none' }}>
              {sections[selected].content}
            </div>
          </>
        ) : (
          <p style={{ color: 'var(--text-muted)' }}>选择一个章节查看内容</p>
        )}
      </div>
    </div>
  )
}
