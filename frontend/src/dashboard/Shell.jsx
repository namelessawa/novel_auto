import React, { useCallback, useEffect, useRef, useState } from 'react'
import './styles/index.css'

import TopBar from './TopBar'
import Sidebar, { NAV_ITEMS } from './Sidebar'
import { ThemeProvider } from './ThemeContext'

import OverviewView from './views/OverviewView'
import TickView from './views/TickView'
import AgentView from './views/AgentView'
import ChapterView from './views/ChapterView'
import KGView from './views/KGView'
import ConfigView from './views/ConfigView'
import AuthorStudioView from './views/AuthorStudioView'
import StoryBibleView from './views/StoryBibleView'
import CanonicalStateView from './views/CanonicalStateView'
import StoryThreadsView from './views/StoryThreadsView'
// v2.48 — 多模态 authoring 直接挂载 legacy MultimodalView (996 行 SSE/blob/race-safe).
// 重写风险大, 直接复用; 视觉用 global.css 的 .card/.btn 类, 暂与 dashboard chrome 风格略有差异.
import MultimodalView from '../views/MultimodalView'
import ReaderOverlay from './ReaderOverlay'
import InjectEventModal from './modals/InjectEventModal'
import NewNovelModal from './modals/NewNovelModal'

import { useAuth } from '../auth/AuthContext'
import SettingsModal from '../auth/SettingsModal'
import {
  createSectionTask,
  fetchGenerationMode,
  fetchNovels,
  fetchStats,
  fetchTickStatus,
  listTasks,
  pauseTick,
  resumeTick,
  runOneTick,
  switchNovel,
} from '../services/api'
import { showToast } from '../utils/toast'

// v2.47 — Dashboard 主 Shell. App.jsx 登录后渲染 <DashboardShell />.

export default function DashboardShell() {
  return (
    <ThemeProvider>
      <DashboardShellInner />
    </ThemeProvider>
  )
}

function DashboardShellInner() {
  const { hasToken } = useAuth()
  const [view, setView] = useState('author')

  // —— Domain data ——
  const [novels, setNovels] = useState([])
  const [activeNovelId, setActiveNovelId] = useState(null)
  const [stats, setStats] = useState(null)
  const [tickStatus, setTickStatus] = useState(null)
  const [tasks, setTasks] = useState([])
  const [generationMode, setGenerationMode] = useState(null)

  // —— Overlays / modals ——
  const [readerOpen, setReaderOpen] = useState(false)
  const [injectOpen, setInjectOpen] = useState(false)
  const [newNovelOpen, setNewNovelOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)

  // —— 续写 race-safety: 镜像 activeNovelId 至 ref,await 期间用户切了别的小说就丢弃本次 UI 更新
  // (任务本身已入队, 由 sidebar 任务面板呈现, 不会丢). 复刻 HomeView.continueIdRef.
  const [continuing, setContinuing] = useState(false)
  const continueIdRef = useRef(null)
  useEffect(() => {
    continueIdRef.current = activeNovelId
  }, [activeNovelId])

  const refreshStats = useCallback(async () => {
    if (!hasToken) return
    try {
      const data = await fetchStats()
      setStats(data)
      if (data?.active_novel_id) {
        setActiveNovelId((prev) => prev || data.active_novel_id)
      }
    } catch {
      /* */
    }
  }, [hasToken])

  const refreshNovels = useCallback(async () => {
    if (!hasToken) return
    try {
      const data = await fetchNovels()
      setNovels(data.novels || [])
      if (data.active_id) setActiveNovelId(data.active_id)
    } catch {
      /* */
    }
  }, [hasToken])

  const refreshTickStatus = useCallback(async (force = false) => {
    if (!hasToken || (!force && generationMode?.mode !== 'simulation')) return
    try {
      const data = await fetchTickStatus()
      setTickStatus(data)
    } catch {
      /* */
    }
  }, [hasToken, generationMode?.mode])

  const refreshGenerationMode = useCallback(async (novelId = activeNovelId) => {
    if (!hasToken || !novelId) {
      setGenerationMode(null)
      return null
    }
    try {
      const data = await fetchGenerationMode(novelId)
      setGenerationMode(data)
      if (data?.mode !== 'simulation') setTickStatus(null)
      return data
    } catch {
      setGenerationMode({ mode: 'author', revision: 0 })
      setTickStatus(null)
      return null
    }
  }, [hasToken, activeNovelId])

  const refreshTasks = useCallback(async () => {
    if (!hasToken) return
    try {
      const data = await listTasks(activeNovelId)
      setTasks(data?.tasks || data?.items || data || [])
    } catch {
      /* */
    }
  }, [hasToken, activeNovelId])

  // 默认作者模式只加载创作域；simulation 明确启用后才触碰 TickRuntime API.
  useEffect(() => {
    if (!hasToken) return undefined
    refreshStats()
    refreshNovels()
    refreshTasks()
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        refreshStats()
        refreshNovels()
        refreshGenerationMode()
        if (generationMode?.mode === 'simulation') refreshTickStatus()
        refreshTasks()
      }
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [
    hasToken,
    refreshStats,
    refreshNovels,
    refreshTickStatus,
    refreshTasks,
    refreshGenerationMode,
    generationMode?.mode,
  ])

  useEffect(() => {
    refreshGenerationMode(activeNovelId)
  }, [activeNovelId, refreshGenerationMode])

  // Tick clock poll — 3s 一次, 只更新 status (轻量).
  useEffect(() => {
    if (!hasToken || generationMode?.mode !== 'simulation') return undefined
    const t = setInterval(() => {
      if (document.visibilityState === 'visible') refreshTickStatus()
    }, 3000)
    return () => clearInterval(t)
  }, [hasToken, refreshTickStatus, generationMode?.mode])

  // —— Actions ——
  async function handleSwitchNovel(id) {
    if (!id || id === activeNovelId) return
    try {
      await switchNovel(id)
      setActiveNovelId(id)
      setGenerationMode(null)
      setTickStatus(null)
      refreshStats()
      refreshTasks()
    } catch (err) {
      showToast('切换作品失败: ' + err.message, 'error')
    }
  }

  async function handleToggleRun() {
    const running = Boolean(tickStatus && !tickStatus.is_paused)
    try {
      if (running) await pauseTick()
      else await resumeTick()
      refreshTickStatus()
    } catch (err) {
      showToast(err.message || '切换调度失败', 'error')
    }
  }

  async function handleStepOne() {
    try {
      await runOneTick()
      showToast('已推进 1 tick', 'success')
      refreshTickStatus()
      refreshStats()
    } catch (err) {
      showToast(err.message || '单步失败', 'error')
    }
  }

  async function handleContinueSection() {
    if (!activeNovelId) {
      showToast('请先选择作品', 'error')
      return
    }
    if (continuing) return
    if (generationMode?.mode !== 'simulation') {
      setView('author')
      showToast('请在章节创作中填写本节目标后生成', 'success')
      return
    }
    const requestedId = activeNovelId
    setContinuing(true)
    try {
      await createSectionTask(requestedId)
      if (continueIdRef.current !== requestedId) return
      showToast('已入队续写任务,见左侧任务面板', 'success')
      refreshTasks()
    } catch (err) {
      showToast(err.message || '续写失败', 'error')
    } finally {
      setContinuing(false)
    }
  }

  const activeNovel =
    novels.find((n) => n.id === activeNovelId) ||
    (activeNovelId ? { id: activeNovelId } : null)

  return (
    <div className="dc-root dc-shell">
      <TopBar
        novels={novels}
        activeNovelId={activeNovelId}
        onSwitchNovel={handleSwitchNovel}
        onCreateNovel={() => setNewNovelOpen(true)}
        tickStatus={tickStatus}
        generationMode={generationMode?.mode || 'author'}
        onOpenConfig={() => setView('config')}
        onOpenProfile={() => setSettingsOpen(true)}
        onOpenSecurity={() => setSettingsOpen(true)}
      />

      <div className="dc-body">
        <Sidebar
          novels={novels}
          activeNovelId={activeNovelId}
          onSwitchNovel={handleSwitchNovel}
          onCreateNovel={() => setNewNovelOpen(true)}
          view={view}
          onView={setView}
          tasks={tasks}
        />

        <main className="dc-main">
          {view === 'author' && (
            <AuthorStudioView
              novel={activeNovel}
              onOpenSimulation={() => setView('tick')}
              onModeChange={(nextMode) => {
                setGenerationMode(nextMode)
                if (nextMode?.mode === 'simulation') refreshTickStatus(true)
                else setTickStatus(null)
              }}
            />
          )}
          {view === 'bible' && <StoryBibleView novel={activeNovel} />}
          {view === 'state' && <CanonicalStateView novel={activeNovel} />}
          {view === 'threads' && <StoryThreadsView novel={activeNovel} />}
          {view === 'overview' && (
            <OverviewView
              novel={activeNovel}
              tickStatus={tickStatus}
              stats={stats}
              onJumpReader={() => setReaderOpen(true)}
              onJumpAgent={() => setView('agent')}
              onJumpKg={() => setView('kg')}
              onJumpChapter={() => setView('chapter')}
              onToggleRun={handleToggleRun}
              onStepOne={handleStepOne}
              onOpenInject={() => setInjectOpen(true)}
              onContinueSection={handleContinueSection}
              continuing={continuing}
            />
          )}
          {view === 'tick' && (
            <TickView
              tickStatus={tickStatus}
              stats={stats}
              onToggleRun={handleToggleRun}
              onStepOne={handleStepOne}
              onOpenInject={() => setInjectOpen(true)}
            />
          )}
          {view === 'agent' && <AgentView />}
          {view === 'chapter' && (
            <ChapterView
              novel={activeNovel}
              onJumpReader={() => setReaderOpen(true)}
              onContinueSection={handleContinueSection}
              continuing={continuing}
              onJumpMultimodal={() => setView('multimodal')}
            />
          )}
          {view === 'multimodal' && (
            <div className="dc-view-switch dc-mm-mount">
              <div className="dc-sec-head">
                <span className="dc-sec-num">§ Multimodal</span>
                <h2 className="dc-sec-title">多模态生成</h2>
                <span className="dc-sec-sub">分段 · 图像 · TTS · 视频</span>
              </div>
              <MultimodalView novel={activeNovel} />
            </div>
          )}
          {view === 'kg' && <KGView generationMode={generationMode?.mode} />}
          {view === 'config' && <ConfigView />}
        </main>
      </div>

      {/* Overlays */}
      {readerOpen && (
        <ReaderOverlay novel={activeNovel} onClose={() => setReaderOpen(false)} />
      )}
      {injectOpen && (
        <InjectEventModal
          tickStatus={tickStatus}
          onClose={() => setInjectOpen(false)}
        />
      )}
      {newNovelOpen && (
        <NewNovelModal
          onClose={() => setNewNovelOpen(false)}
          onCreated={(id, createdMode = 'author') => {
            refreshNovels()
            if (id) {
              setActiveNovelId(id)
              setGenerationMode({ mode: createdMode, revision: 1 })
              setView(createdMode === 'simulation' ? 'tick' : 'author')
            }
          }}
        />
      )}
      {settingsOpen && (
        <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      )}
    </div>
  )
}

// 防止 esling 警告未使用 — sidebar 类型供同模块导出参考.
export { NAV_ITEMS }
