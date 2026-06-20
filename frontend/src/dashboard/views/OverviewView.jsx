import React, { useEffect, useState } from 'react'
import HeroSection from './overview/HeroSection'
import MetricsSection from './overview/MetricsSection'
import AgentsSection from './overview/AgentsSection'
import LoopsKGSection from './overview/LoopsKGSection'
import {
  fetchAgents,
  fetchGraph,
  fetchHallucinationDiagnostic,
  fetchTickHistory,
  fetchTickNarratives,
  fetchTickOpenLoops,
} from '../../services/api'

// v2.47 — § 总览 view 总装.
// 拉以下数据并往下分发到 4 个子 section:
//   - fetchTickNarratives(limit=1) → 最近一条 narrator excerpt
//   - fetchTickHistory(last_n=60)  → 60-tick 时间线 + tokens / duration 计算
//   - fetchTickOpenLoops(top_k=8)  → 伏笔池 list
//   - fetchHallucinationDiagnostic() → 幻觉率 KPI
//   - fetchAgents()                → agent grid 合并元数据
//   - fetchGraph()                 → KG mini 节点 + edge count
//
// 失败任一项不阻塞其他, 子 section 自带 empty-state.

export default function OverviewView({
  novel,
  tickStatus,
  stats,
  onJumpReader,
  onJumpAgent,
  onJumpKg,
  onJumpChapter,
  onToggleRun,
  onStepOne,
  onOpenInject,
}) {
  const [narrative, setNarrative] = useState(null)
  const [history, setHistory] = useState([])
  const [openLoops, setOpenLoops] = useState([])
  const [hallucination, setHallucination] = useState(null)
  const [agents, setAgents] = useState([])
  const [graph, setGraph] = useState({ nodes: [], edges: [] })

  useEffect(() => {
    if (!novel?.id) return undefined
    let cancelled = false

    async function load() {
      // Narrator excerpt
      try {
        const r = await fetchTickNarratives({ limit: 3 })
        if (!cancelled) {
          const last = (r?.narratives || []).slice(-1)[0] || null
          setNarrative(last)
        }
      } catch {
        if (!cancelled) setNarrative(null)
      }

      // Tick history → KPI + timeline
      try {
        const r = await fetchTickHistory(60)
        if (!cancelled) setHistory(r?.ticks || [])
      } catch {
        if (!cancelled) setHistory([])
      }

      // Open loops
      try {
        const r = await fetchTickOpenLoops(8)
        if (!cancelled) {
          const arr = Array.isArray(r) ? r : r?.open_loops || r?.loops || []
          setOpenLoops(arr.slice(0, 5))
        }
      } catch {
        if (!cancelled) setOpenLoops([])
      }

      // Hallucination
      try {
        const r = await fetchHallucinationDiagnostic()
        if (!cancelled) setHallucination(r)
      } catch {
        if (!cancelled) setHallucination(null)
      }

      // Agents
      try {
        const r = await fetchAgents()
        if (!cancelled) setAgents(r?.agents || [])
      } catch {
        if (!cancelled) setAgents([])
      }

      // KG snapshot
      try {
        const r = await fetchGraph()
        if (!cancelled) setGraph({ nodes: r?.nodes || [], edges: r?.edges || [] })
      } catch {
        if (!cancelled) setGraph({ nodes: [], edges: [] })
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [novel?.id, tickStatus?.current_tick])

  const running = Boolean(tickStatus && !tickStatus.is_paused)

  return (
    <div className="dc-view-switch dc-ov-root">
      <HeroSection
        novel={novel}
        tickStatus={tickStatus}
        stats={stats}
        narrative={narrative}
        onJumpReader={onJumpReader}
        onJumpChapter={onJumpChapter}
      />

      <MetricsSection
        tickStatus={tickStatus}
        history={history}
        openLoopsCount={openLoops.length}
        hallucinationStats={hallucination}
        running={running}
        onToggleRun={onToggleRun}
        onStepOne={onStepOne}
        onOpenInject={onOpenInject}
      />

      <AgentsSection
        agents={agents}
        currentTick={tickStatus?.current_tick}
        onJumpAgent={onJumpAgent}
      />

      <LoopsKGSection
        openLoops={openLoops}
        graph={graph}
        onJumpKg={onJumpKg}
      />
    </div>
  )
}
