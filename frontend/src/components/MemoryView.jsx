import React, { useState, useEffect } from 'react'
import { fetchMemory, fetchOutline } from '../services/api'

export default function MemoryView({ refreshKey }) {
  const [memory, setMemory] = useState(null)
  const [outline, setOutline] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [refreshKey])

  const loadData = async () => {
    setLoading(true)
    try {
      const [memData, outData] = await Promise.all([
        fetchMemory(),
        fetchOutline(),
      ])
      setMemory(memData)
      setOutline(outData)
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  if (loading) {
    return <div className="card"><p style={{ color: 'var(--text-muted)' }}>加载中…</p></div>
  }

  return (
    <div>
      {/* Working Memory */}
      <div className="card">
        <div className="card-title">工作记忆（短期缓存）</div>
        {memory?.sections?.length > 0 ? (
          <div style={{ display: 'flex', flexWrap: 'wrap' }}>
            {memory.sections.map((s, i) => (
              <div key={i} className="memory-slot">
                <span className="label">槽位{i + 1}</span>
                第{s.chapter}章 第{s.section}节 ({s.word_count}字)
              </div>
            ))}
          </div>
        ) : (
          <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            工作记忆为空。开始生成后，最近的2-3节内容将缓存于此。
          </p>
        )}
      </div>

      {/* Scene Context */}
      <div className="card">
        <div className="card-title">当前场景</div>
        {memory?.scene?.environment ? (
          <>
            <div style={{ marginBottom: 12 }}>
              <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>环境描述</span>
              <p style={{ fontSize: 14, marginTop: 4 }}>{memory.scene.environment}</p>
            </div>
            {memory.scene.active_characters?.length > 0 && (
              <div>
                <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>在场角色</span>
                <div style={{ display: 'flex', flexWrap: 'wrap', marginTop: 4 }}>
                  {memory.scene.active_characters.map((c, i) => (
                    <div key={i} className="memory-slot">
                      {c.name}
                      <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                        ({c.emotion})
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            尚无场景信息。
          </p>
        )}
      </div>

      {/* Summary Tree */}
      <div className="card">
        <div className="card-title">动态摘要树</div>
        {outline?.root_summary ? (
          <>
            <div style={{ marginBottom: 12 }}>
              <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>全书总纲</span>
              <p style={{ fontSize: 14, marginTop: 4 }}>{outline.root_summary}</p>
            </div>
            {outline.outline && (
              <div>
                <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>摘要树结构</span>
                <div className="tree-view">{outline.outline}</div>
              </div>
            )}
          </>
        ) : (
          <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            摘要树为空。生成内容后将自动构建层级摘要。
          </p>
        )}
      </div>
    </div>
  )
}
