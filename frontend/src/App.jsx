import React, { useCallback, useEffect, useState } from 'react'
import GraphView from './components/GraphView'
import MemoryView from './components/MemoryView'
import TickControlPanel from './components/TickControlPanel'
import SectionsList from './components/SectionsList'
import HomeView from './views/HomeView'
import NovelView from './views/NovelView'
import ConfigView from './views/ConfigView'
import AgentContextView from './views/AgentContextView'
import {
  deleteNovel,
  fetchNovels,
  fetchStats,
  switchNovel,
  updateNovelTitle,
} from './services/api'
import { showToast } from './utils/toast'

const PRIMARY_NAV = [
  { key: 'home', label: '创作工坊', icon: 'fa-pen-fancy' },
  { key: 'novel', label: '作品详情', icon: 'fa-book-open' },
  { key: 'agents', label: 'Agent 上下文', icon: 'fa-robot' },
  { key: 'config', label: '系统设置', icon: 'fa-sliders-h' },
]

const TOOL_NAV = [
  { key: 'sections', label: '章节速览', icon: 'fa-list-ul' },
  { key: 'graph', label: '知识图谱', icon: 'fa-project-diagram' },
  { key: 'memory', label: '记忆系统', icon: 'fa-brain' },
  { key: 'control', label: 'Tick 控制台', icon: 'fa-gauge-high' },
]

const VIEW_TITLES = {
  home: { label: '创作工坊', icon: 'fa-pen-fancy' },
  novel: { label: '作品详情', icon: 'fa-book-open' },
  agents: { label: 'Agent 上下文', icon: 'fa-robot' },
  config: { label: '系统设置', icon: 'fa-sliders-h' },
  sections: { label: '章节速览', icon: 'fa-list-ul' },
  graph: { label: '知识图谱', icon: 'fa-project-diagram' },
  memory: { label: '记忆系统', icon: 'fa-brain' },
  control: { label: 'Tick 控制台', icon: 'fa-gauge-high' },
}

export default function App() {
  const [activeView, setActiveView] = useState('home')
  const [stats, setStats] = useState(null)
  const [backendOnline, setBackendOnline] = useState(true)
  const [refreshKey, setRefreshKey] = useState(0)
  const [novels, setNovels] = useState([])
  const [activeNovelId, setActiveNovelId] = useState(null)
  const [hoveredNovelId, setHoveredNovelId] = useState(null)

  const refreshStats = useCallback(async () => {
    try {
      const data = await fetchStats()
      setStats(data)
      setBackendOnline(true)
      if (data.active_novel_id && !activeNovelId) {
        setActiveNovelId(data.active_novel_id)
      }
    } catch (err) {
      console.error('Failed to fetch stats:', err)
      setBackendOnline(false)
    }
  }, [activeNovelId])

  const refreshNovels = useCallback(async () => {
    try {
      const data = await fetchNovels()
      setNovels(data.novels || [])
      if (data.active_id) setActiveNovelId(data.active_id)
    } catch (err) {
      console.error('Failed to fetch novels:', err)
    }
  }, [])

  const bumpRefresh = useCallback(() => {
    refreshStats()
    refreshNovels()
    setRefreshKey((k) => k + 1)
  }, [refreshStats, refreshNovels])

  useEffect(() => {
    refreshStats()
    refreshNovels()
    const interval = setInterval(refreshStats, 5000)
    return () => clearInterval(interval)
  }, [refreshStats, refreshNovels])

  const handleOpenNovel = async (novelId) => {
    try {
      await switchNovel(novelId)
      setActiveNovelId(novelId)
      setActiveView('novel')
      setRefreshKey((k) => k + 1)
    } catch (err) {
      showToast('切换作品失败:' + err.message, 'error')
    }
  }

  const handleRename = async (novelId, e) => {
    e.stopPropagation()
    const current = novels.find((n) => n.id === novelId)
    const next = window.prompt('新的小说标题', current?.title || novelId)
    if (!next || !next.trim()) return
    try {
      await updateNovelTitle(novelId, next.trim())
      showToast('标题已更新', 'success')
      await refreshNovels()
    } catch (err) {
      showToast('更新失败:' + err.message, 'error')
    }
  }

  const handleDelete = async (novelId, e) => {
    e.stopPropagation()
    const current = novels.find((n) => n.id === novelId)
    const label = current?.title || novelId
    if (novelId === activeNovelId) {
      showToast('不能删除当前活跃的小说', 'error')
      return
    }
    if (!window.confirm(`确定删除《${label}》?该操作不可撤销。`)) return
    try {
      await deleteNovel(novelId)
      showToast('已删除', 'success')
      await refreshNovels()
    } catch (err) {
      showToast('删除失败:' + err.message, 'error')
    }
  }

  const title = VIEW_TITLES[activeView] || VIEW_TITLES.home
  const activeNovel = novels.find((n) => n.id === activeNovelId)

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo">NovelAuto</div>
          <div className="sidebar-logo-sub">AI 智能小说创作平台</div>
        </div>

        <nav className="sidebar-nav">
          {PRIMARY_NAV.map((item) => (
            <button
              key={item.key}
              className={`nav-item ${activeView === item.key ? 'active' : ''}`}
              onClick={() => setActiveView(item.key)}
            >
              <i className={`fas ${item.icon}`}></i> {item.label}
            </button>
          ))}
        </nav>

        <div className="nav-divider"></div>

        <div className="sidebar-topics-header">
          <span>工具</span>
        </div>
        <nav className="sidebar-nav" style={{ paddingTop: 0 }}>
          {TOOL_NAV.map((item) => (
            <button
              key={item.key}
              className={`nav-item ${activeView === item.key ? 'active' : ''}`}
              onClick={() => setActiveView(item.key)}
            >
              <i className={`fas ${item.icon}`}></i> {item.label}
            </button>
          ))}
        </nav>

        <div className="nav-divider"></div>

        <div className="sidebar-topics-header">
          <span>我的作品</span>
          <span style={{ color: 'var(--text-muted)', textTransform: 'none' }}>
            {novels.length}
          </span>
        </div>
        <div className="sidebar-topics">
          {novels.length === 0 ? (
            <div
              style={{
                padding: '12px',
                fontSize: 13,
                color: 'var(--text-muted)',
              }}
            >
              暂无作品,前往创作工坊创建
            </div>
          ) : (
            novels.map((n) => (
              <div
                key={n.id}
                className={`topic-item ${
                  activeNovelId === n.id && activeView === 'novel' ? 'active' : ''
                }`}
                onMouseEnter={() => setHoveredNovelId(n.id)}
                onMouseLeave={() => setHoveredNovelId(null)}
                onClick={() => handleOpenNovel(n.id)}
                title={n.title || n.id}
              >
                <i className="fas fa-book"></i>
                <span className="topic-item-label">{n.title || n.id}</span>
                {hoveredNovelId === n.id && (
                  <span style={{ display: 'flex', gap: 8, marginLeft: 4 }}>
                    <i
                      className="fas fa-pen"
                      title="重命名"
                      style={{
                        fontSize: 11,
                        opacity: 0.6,
                        cursor: 'pointer',
                      }}
                      onClick={(e) => handleRename(n.id, e)}
                    ></i>
                    <i
                      className="fas fa-trash"
                      title="删除"
                      style={{
                        fontSize: 11,
                        opacity: 0.6,
                        color: 'var(--accent-rose)',
                        cursor: 'pointer',
                      }}
                      onClick={(e) => handleDelete(n.id, e)}
                    ></i>
                  </span>
                )}
              </div>
            ))
          )}
        </div>

        <div className="sidebar-footer">
          <span
            className={`status-dot ${backendOnline ? 'online' : 'offline'}`}
          ></span>
          <span>{backendOnline ? '在线' : '离线'}</span>
          {stats && (
            <span style={{ marginLeft: 'auto' }}>
              {stats.total_sections || 0} 节 · {(stats.total_words || 0).toLocaleString()} 字
            </span>
          )}
        </div>
      </aside>

      <main className="main-content">
        <div className="content-header">
          <h2>
            <i
              className={`fas ${title.icon}`}
              style={{ color: 'var(--accent-purple)' }}
            ></i>
            {title.label}
            {activeView === 'novel' && activeNovel && (
              <span
                className="badge badge-purple"
                style={{ marginLeft: 8, fontSize: 12 }}
              >
                {activeNovel.title || activeNovel.id}
              </span>
            )}
          </h2>
          {!backendOnline && (
            <div
              className="badge"
              style={{
                background: 'rgba(244, 63, 94, 0.15)',
                color: 'var(--accent-rose)',
                padding: '6px 12px',
              }}
            >
              <i
                className="fas fa-exclamation-triangle"
                style={{ marginRight: 6 }}
              ></i>
              后端未连接 · 请启动 python run.py
            </div>
          )}
        </div>

        <div className="content-body">
          {/* 所有 view 常驻挂载,通过 display 切换可见性 —— 这样切换栏目不会
              清空 HomeView 的输入框 / ConfigView 的表单 / NovelView 的选中章节
              等组件内部状态。GraphView 通过 isVisible prop 知道何时暂停渲染。 */}
          <ViewSlot active={activeView === 'home'}>
            <HomeView
              onAfterCreated={(id) => {
                refreshNovels()
                if (id) setActiveNovelId(id)
              }}
              onAfterGenerated={bumpRefresh}
            />
          </ViewSlot>
          <ViewSlot active={activeView === 'novel'}>
            <NovelView novel={activeNovel} onAfterGenerated={bumpRefresh} />
          </ViewSlot>
          <ViewSlot active={activeView === 'agents'}>
            <AgentContextView />
          </ViewSlot>
          <ViewSlot active={activeView === 'config'}>
            <ConfigView />
          </ViewSlot>
          <ViewSlot active={activeView === 'sections'}>
            <SectionsList refreshKey={refreshKey} />
          </ViewSlot>
          <ViewSlot active={activeView === 'graph'}>
            <GraphView
              refreshKey={refreshKey}
              isVisible={activeView === 'graph'}
            />
          </ViewSlot>
          <ViewSlot active={activeView === 'memory'}>
            <MemoryView refreshKey={refreshKey} />
          </ViewSlot>
          <ViewSlot active={activeView === 'control'}>
            <TickControlPanel onAction={bumpRefresh} refreshKey={refreshKey} />
          </ViewSlot>
        </div>
      </main>
    </div>
  )
}

function ViewSlot({ active, children }) {
  return (
    <div
      style={{
        display: active ? 'flex' : 'none',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
      }}
    >
      {children}
    </div>
  )
}
