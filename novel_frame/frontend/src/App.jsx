import React, { useState, useEffect, useCallback } from 'react'
import GeneratePanel from './components/GeneratePanel'
import SectionsList from './components/SectionsList'
import GraphView from './components/GraphView'
import MemoryView from './components/MemoryView'
import ControlPanel from './components/ControlPanel'
import { fetchStats } from './services/api'

const TABS = [
  { key: 'generate', label: '生成' },
  { key: 'sections', label: '章节' },
  { key: 'graph', label: '知识图谱' },
  { key: 'memory', label: '记忆系统' },
  { key: 'control', label: '控制台' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('generate')
  const [stats, setStats] = useState(null)
  const [backendOnline, setBackendOnline] = useState(true)
  const [refreshKey, setRefreshKey] = useState(0)

  const refreshStats = useCallback(async () => {
    try {
      const data = await fetchStats()
      setStats(data)
      setBackendOnline(true)
    } catch (err) {
      console.error('Failed to fetch stats:', err)
      setBackendOnline(false)
    }
  }, [])

  const handleGenerated = useCallback(() => {
    refreshStats()
    setRefreshKey((k) => k + 1)
  }, [refreshStats])

  useEffect(() => {
    refreshStats()
    const interval = setInterval(refreshStats, 5000)
    return () => clearInterval(interval)
  }, [refreshStats])

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>AI Novel Agent</h1>
        {!backendOnline && (
          <div style={{
            background: '#dc2626',
            color: 'white',
            padding: '4px 12px',
            borderRadius: 4,
            fontSize: 13,
            fontWeight: 500,
          }}>
            后端未连接 — 请启动后端服务 (python main.py)
          </div>
        )}
        {stats && (
          <div className="header-stats">
            <span>
              章节 <span className="stat-value">{stats.current_chapter}-{stats.current_section}</span>
            </span>
            <span>
              总节数 <span className="stat-value">{stats.total_sections}</span>
            </span>
            <span>
              总字数 <span className="stat-value">{stats.total_words?.toLocaleString()}</span>
            </span>
            <span>
              实体 <span className="stat-value">{stats.entity_count}</span>
            </span>
          </div>
        )}
      </header>

      <nav className="tab-bar">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <main className="main-content">
        <div style={{ display: activeTab === 'generate' ? 'block' : 'none' }}>
          <GeneratePanel onGenerated={handleGenerated} />
        </div>
        <div style={{ display: activeTab === 'sections' ? 'block' : 'none' }}>
          <SectionsList refreshKey={refreshKey} />
        </div>
        <div style={{ display: activeTab === 'graph' ? 'block' : 'none' }}>
          <GraphView refreshKey={refreshKey} isVisible={activeTab === 'graph'} />
        </div>
        <div style={{ display: activeTab === 'memory' ? 'block' : 'none' }}>
          <MemoryView refreshKey={refreshKey} />
        </div>
        <div style={{ display: activeTab === 'control' ? 'block' : 'none' }}>
          <ControlPanel onAction={handleGenerated} refreshKey={refreshKey} />
        </div>
      </main>
    </div>
  )
}
