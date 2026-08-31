import React, { useCallback, useEffect, useRef, useState } from 'react'
import './styles/index.css'

import TopBar from './TopBar'
import Sidebar, { NAV_ITEMS } from './Sidebar'
import { ThemeProvider } from './ThemeContext'
import {
  DEFAULT_VIEW,
  hashForView,
  mainNavigationView,
  viewFromHash,
} from './routing'

import ProductionCenterView from './views/ProductionCenterView'
import StoryBlueprintView from './views/StoryBlueprintView'
import CommittedChaptersView from './views/CommittedChaptersView'
import StyleStudioView from './views/StyleStudioView'
import CanonicalStateView from './views/CanonicalStateView'
import ThreadsMemoryView from './views/ThreadsMemoryView'
import ProviderConfigView from './views/ProviderConfigView'
import ExportView from './views/ExportView'
import ExperimentLabView from './views/ExperimentLabView'

import AuthorStudioView from './views/AuthorStudioView'
import OverviewView from './views/OverviewView'
import TickView from './views/TickView'
import AgentView from './views/AgentView'
import KGView from './views/KGView'
import MultimodalView from '../views/MultimodalView'
import PipelineView from './views/PipelineView'

import ReaderOverlay from './ReaderOverlay'
import InjectEventModal from './modals/InjectEventModal'
import NewNovelModal from './modals/NewNovelModal'
import SettingsModal from '../auth/SettingsModal'
import { useAuth } from '../auth/AuthContext'
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

export function shouldFetchTickStatus(mode, force = false) {
  return Boolean(force || mode === 'simulation')
}

export default function DashboardShell() {
  return (
    <ThemeProvider>
      <DashboardShellInner />
    </ThemeProvider>
  )
}

function DashboardShellInner() {
  const { hasToken } = useAuth()
  const [view, setView] = useState(() => (
    typeof window === 'undefined'
      ? DEFAULT_VIEW
      : viewFromHash(window.location?.hash)
  ))
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false)

  const [novels, setNovels] = useState([])
  const [activeNovelId, setActiveNovelId] = useState(null)
  const [stats, setStats] = useState(null)
  const [tickStatus, setTickStatus] = useState(null)
  const [tasks, setTasks] = useState([])
  const [generationMode, setGenerationMode] = useState(null)

  const [readerOpen, setReaderOpen] = useState(false)
  const [injectOpen, setInjectOpen] = useState(false)
  const [newNovelOpen, setNewNovelOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [continuing, setContinuing] = useState(false)

  const continueIdRef = useRef(null)
  useEffect(() => {
    continueIdRef.current = activeNovelId
  }, [activeNovelId])

  const navigate = useCallback((nextView, options = {}) => {
    const next = viewFromHash(nextView)
    setView(next)
    setMobileNavigationOpen(false)
    if (typeof window === 'undefined' || !window.location) return
    const nextHash = hashForView(next)
    if (window.location.hash === nextHash) return
    if (options.replace && window.history?.replaceState) {
      window.history.replaceState(null, '', nextHash)
    } else {
      window.location.hash = nextHash
    }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const syncHash = () => setView(viewFromHash(window.location.hash))
    window.addEventListener('hashchange', syncHash)
    if (!window.location.hash) navigate(DEFAULT_VIEW, { replace: true })
    return () => window.removeEventListener('hashchange', syncHash)
  }, [navigate])

  const refreshStats = useCallback(async () => {
    if (!hasToken) return
    try {
      const data = await fetchStats()
      setStats(data)
      if (data?.active_novel_id) {
        setActiveNovelId((current) => current || data.active_novel_id)
      }
    } catch {
      // Each product view owns its visible error state.
    }
  }, [hasToken])

  const refreshNovels = useCallback(async () => {
    if (!hasToken) return
    try {
      const data = await fetchNovels()
      setNovels(data.novels || [])
      if (data.active_id) setActiveNovelId(data.active_id)
    } catch {
      // Keep the current selection while an individual view offers retry.
    }
  }, [hasToken])

  const refreshTasks = useCallback(async () => {
    if (!hasToken) return
    try {
      const data = await listTasks(activeNovelId)
      setTasks(data?.tasks || data?.items || data || [])
    } catch {
      // Sidebar task telemetry is supplementary.
    }
  }, [activeNovelId, hasToken])

  const refreshGenerationMode = useCallback(async (novelId) => {
    if (!hasToken || !novelId) {
      setGenerationMode(null)
      setTickStatus(null)
      return null
    }
    try {
      const data = await fetchGenerationMode(novelId)
      setGenerationMode(data)
      if (data?.mode !== 'simulation') setTickStatus(null)
      return data
    } catch {
      const safeDefault = { mode: 'author', revision: 0 }
      setGenerationMode(safeDefault)
      setTickStatus(null)
      return safeDefault
    }
  }, [hasToken])

  const refreshTickStatus = useCallback(async (force = false) => {
    if (!hasToken || !shouldFetchTickStatus(generationMode?.mode, force)) return
    try {
      setTickStatus(await fetchTickStatus())
    } catch {
      // Simulation diagnostics remain isolated from the production workspace.
    }
  }, [generationMode?.mode, hasToken])

  useEffect(() => {
    if (!hasToken) return undefined
    refreshStats()
    refreshNovels()
    refreshTasks()
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return
      refreshStats()
      refreshNovels()
      refreshTasks()
      refreshGenerationMode(activeNovelId)
      if (shouldFetchTickStatus(generationMode?.mode)) refreshTickStatus()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [
    activeNovelId,
    generationMode?.mode,
    hasToken,
    refreshGenerationMode,
    refreshNovels,
    refreshStats,
    refreshTasks,
    refreshTickStatus,
  ])

  useEffect(() => {
    refreshGenerationMode(activeNovelId)
  }, [activeNovelId, refreshGenerationMode])

  useEffect(() => {
    if (!hasToken || generationMode?.mode !== 'simulation') return undefined
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') refreshTickStatus()
    }, 3000)
    return () => clearInterval(timer)
  }, [generationMode?.mode, hasToken, refreshTickStatus])

  async function handleSwitchNovel(id) {
    if (!id || id === activeNovelId) return
    try {
      await switchNovel(id)
      setActiveNovelId(id)
      setGenerationMode(null)
      setTickStatus(null)
      refreshStats()
      refreshTasks()
    } catch (error) {
      showToast(`切换作品失败：${error.message}`, 'error')
    }
  }

  async function handleToggleRun() {
    const running = Boolean(tickStatus && !tickStatus.is_paused)
    try {
      if (running) await pauseTick()
      else await resumeTick()
      refreshTickStatus(true)
    } catch (error) {
      showToast(error.message || '切换实验调度失败', 'error')
    }
  }

  async function handleStepOne() {
    try {
      await runOneTick()
      showToast('实验运行时已推进 1 tick', 'success')
      refreshTickStatus(true)
      refreshStats()
    } catch (error) {
      showToast(error.message || '单步实验失败', 'error')
    }
  }

  async function handleContinueSection() {
    if (!activeNovelId) {
      showToast('请先选择作品', 'error')
      return
    }
    if (generationMode?.mode !== 'simulation') {
      navigate('production')
      showToast('默认写作请从生产中心启动整书任务', 'success')
      return
    }
    if (continuing) return
    const requestedId = activeNovelId
    setContinuing(true)
    try {
      await createSectionTask(requestedId)
      if (continueIdRef.current !== requestedId) return
      showToast('实验单节任务已入队', 'success')
      refreshTasks()
    } catch (error) {
      showToast(error.message || '实验任务入队失败', 'error')
    } finally {
      setContinuing(false)
    }
  }

  const activeNovel =
    novels.find((novel) => novel.id === activeNovelId) ||
    (activeNovelId ? { id: activeNovelId } : null)

  function labTool(title, backLabel, content) {
    return (
      <div className="dc-lab-tool-shell">
        <header className="dc-lab-tool-head">
          <button type="button" onClick={() => navigate('lab')}>← 实验室</button>
          <div>
            <span>OPT-IN DIAGNOSTIC</span>
            <strong>{title}</strong>
          </div>
          <em>{backLabel}</em>
        </header>
        {content}
      </div>
    )
  }

  function renderView() {
    switch (view) {
      case 'production':
        return <ProductionCenterView novel={activeNovel} onNavigate={navigate} />
      case 'blueprint':
        return <StoryBlueprintView novel={activeNovel} />
      case 'chapters':
        return <CommittedChaptersView novel={activeNovel} />
      case 'styles':
        return <StyleStudioView novel={activeNovel} />
      case 'state':
        return <CanonicalStateView novel={activeNovel} />
      case 'memory':
        return <ThreadsMemoryView novel={activeNovel} />
      case 'pipeline':
        return <PipelineView novelId={activeNovelId} />
      case 'provider':
        return <ProviderConfigView />
      case 'export':
        return <ExportView novel={activeNovel} />
      case 'lab':
        return (
          <ExperimentLabView
            novel={activeNovel}
            onOpen={navigate}
            onModeChange={(nextMode) => {
              setGenerationMode(nextMode)
              if (nextMode?.mode === 'simulation') refreshTickStatus(true)
              else setTickStatus(null)
            }}
          />
        )
      case 'lab-manual':
        return labTool(
          '单节事务台',
          'AUTHOR DEBUG',
          <AuthorStudioView
            novel={activeNovel}
            onOpenSimulation={() => navigate('lab-tick')}
            onModeChange={(nextMode) => {
              setGenerationMode(nextMode)
              if (nextMode?.mode === 'simulation') refreshTickStatus(true)
            }}
          />,
        )
      case 'lab-overview':
        return labTool(
          '模拟运行概览',
          'SIMULATION',
          <OverviewView
            novel={activeNovel}
            tickStatus={tickStatus}
            stats={stats}
            onJumpReader={() => setReaderOpen(true)}
            onJumpAgent={() => navigate('lab-agent')}
            onJumpKg={() => navigate('lab-kg')}
            onJumpChapter={() => navigate('chapters')}
            onToggleRun={handleToggleRun}
            onStepOne={handleStepOne}
            onOpenInject={() => setInjectOpen(true)}
            onContinueSection={handleContinueSection}
            continuing={continuing}
          />,
        )
      case 'lab-tick':
        return labTool(
          'Tick 调度',
          '9 AGENTS',
          <TickView
            tickStatus={tickStatus}
            stats={stats}
            onToggleRun={handleToggleRun}
            onStepOne={handleStepOne}
            onOpenInject={() => setInjectOpen(true)}
          />,
        )
      case 'lab-agent':
        return labTool('Agent 上下文', 'DIAGNOSTIC', <AgentView />)
      case 'lab-kg':
        return labTool(
          '知识图谱',
          'DERIVED',
          <KGView generationMode={generationMode?.mode} />,
        )
      case 'lab-multimodal':
        return labTool(
          '多模态生成',
          'MEDIA',
          <div className="dc-mm-mount">
            <MultimodalView novel={activeNovel} />
          </div>,
        )
      default:
        return <ProductionCenterView novel={activeNovel} onNavigate={navigate} />
    }
  }

  return (
    <div className="dc-root dc-shell">
      <TopBar
        novels={novels}
        activeNovelId={activeNovelId}
        onSwitchNovel={handleSwitchNovel}
        onCreateNovel={() => setNewNovelOpen(true)}
        tickStatus={tickStatus}
        generationMode={generationMode?.mode || 'author'}
        onOpenConfig={() => navigate('provider')}
        onOpenProfile={() => setSettingsOpen(true)}
        onOpenSecurity={() => setSettingsOpen(true)}
        onToggleNavigation={() => setMobileNavigationOpen(true)}
      />

      <div className="dc-body">
        <button
          type="button"
          className={`dc-sidebar-scrim ${mobileNavigationOpen ? 'is-open' : ''}`}
          onClick={() => setMobileNavigationOpen(false)}
          aria-label="关闭导航"
          tabIndex={mobileNavigationOpen ? 0 : -1}
        />
        <Sidebar
          novels={novels}
          activeNovelId={activeNovelId}
          onSwitchNovel={handleSwitchNovel}
          onCreateNovel={() => setNewNovelOpen(true)}
          view={mainNavigationView(view)}
          onView={navigate}
          tasks={tasks}
          open={mobileNavigationOpen}
          onClose={() => setMobileNavigationOpen(false)}
        />

        <main className="dc-main" data-route={view}>
          {renderView()}
        </main>
      </div>

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
          onCreated={(id) => {
            refreshNovels()
            if (id) {
              setActiveNovelId(id)
              setGenerationMode({ mode: 'author', revision: 1 })
              navigate('blueprint')
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

export { NAV_ITEMS }
