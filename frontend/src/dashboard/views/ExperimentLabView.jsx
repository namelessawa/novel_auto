import React, { useCallback, useEffect, useState } from 'react'
import {
  fetchGenerationMode,
  updateGenerationMode,
} from '../../services/api'
import AsyncState, { InlineNotice } from '../components/AsyncState'
import { showToast } from '../../utils/toast'

const DEFAULT_API = { fetchGenerationMode, updateGenerationMode }

const TOOLS = [
  {
    key: 'lab-manual',
    index: '01',
    title: '单节事务台',
    description: '手动填写单节目标，检查 NarrativeContract、Validator 与事务证据。',
    tag: 'AUTHOR DEBUG',
  },
  {
    key: 'lab-overview',
    index: '02',
    title: '模拟运行概览',
    description: '查看实验 TickRuntime 的指标、循环与派生图谱。',
    tag: 'SIMULATION',
  },
  {
    key: 'lab-tick',
    index: '03',
    title: 'Tick 调度',
    description: '单步、暂停与注入事件；不会参与默认整书生产。',
    tag: '9 AGENTS',
  },
  {
    key: 'lab-agent',
    index: '04',
    title: 'Agent 上下文',
    description: '诊断实验 Agent 的上下文与模型输出。',
    tag: 'DIAGNOSTIC',
  },
  {
    key: 'lab-kg',
    index: '05',
    title: '知识图谱',
    description: '查看派生关系；CanonicalState 仍是唯一事实源。',
    tag: 'DERIVED',
  },
  {
    key: 'lab-multimodal',
    index: '06',
    title: '多模态生成',
    description: '为既有节生成图像、TTS 与视频资产。',
    tag: 'MEDIA',
  },
]

export default function ExperimentLabView({
  novel,
  onOpen,
  onModeChange,
  api = DEFAULT_API,
  notify = showToast,
}) {
  const [mode, setMode] = useState(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!novel?.id) return
    setLoading(true)
    try {
      setMode(await api.fetchGenerationMode(novel.id))
    } catch (loadError) {
      setError(loadError.message || '实验模式状态读取失败')
    } finally {
      setLoading(false)
    }
  }, [api, novel?.id])

  useEffect(() => {
    setMode(null)
    load()
  }, [load])

  async function toggleSimulation() {
    if (!mode || busy) return
    const nextMode = mode.mode === 'simulation' ? 'author' : 'simulation'
    const message = nextMode === 'simulation'
      ? '启用后会装配九 Agent + Tick 实验运行时，但不会接管整书生产。确认继续？'
      : '切回作者模式会停止实验 TickRuntime，不影响已提交正文。确认继续？'
    if (!window.confirm(message)) return
    setBusy(true)
    setError('')
    try {
      const result = await api.updateGenerationMode(
        novel.id,
        mode.revision,
        nextMode,
      )
      setMode(result)
      onModeChange?.(result)
      notify(
        nextMode === 'simulation' ? '世界模拟实验已启用' : '已切回作者模式',
        'success',
      )
    } catch (toggleError) {
      setError(
        toggleError.code === 'REVISION_CONFLICT'
          ? '模式已在另一会话变化，请重新载入。'
          : toggleError.message || '实验模式切换失败',
      )
    } finally {
      setBusy(false)
    }
  }

  if (!novel?.id) return <AsyncState kind="empty" title="请先选择作品" />
  if (loading && !mode) return <AsyncState title="正在打开实验室" />

  return (
    <div className="dc-view-switch dc-production-root dc-lab-root" data-testid="experiment-lab">
      <header className="dc-product-masthead">
        <div>
          <span className="dc-product-eyebrow">EXPERIMENT LAB · OPT-IN</span>
          <h1>实验室</h1>
          <p>九 Agent 世界模拟和诊断工具集中在这里，不进入默认建书或长篇生产路径。</p>
        </div>
        <button
          type="button"
          className={mode?.mode === 'simulation' ? 'dc-btn-ghost is-danger' : 'dc-btn'}
          onClick={toggleSimulation}
          disabled={busy || !mode}
        >
          {busy
            ? '切换中…'
            : mode?.mode === 'simulation'
              ? '停用世界模拟'
              : '启用世界模拟'}
        </button>
      </header>
      {error && (
        <InlineNotice
          kind="error"
          actions={<button type="button" onClick={load}>重新载入</button>}
        >
          {error}
        </InlineNotice>
      )}
      <section className={`dc-lab-mode ${mode?.mode === 'simulation' ? 'is-live' : ''}`}>
        <span>{mode?.mode === 'simulation' ? 'SIMULATION LIVE' : 'AUTHOR PRODUCTION SAFE'}</span>
        <strong>
          {mode?.mode === 'simulation'
            ? '实验运行时已装配；整书任务仍使用作者生产链。'
            : '当前只运行作者生产模式；实验 Agent 未装配。'}
        </strong>
      </section>
      <div className="dc-lab-grid">
        {TOOLS.map((tool) => (
          <button type="button" key={tool.key} onClick={() => onOpen?.(tool.key)}>
            <span>{tool.index}</span>
            <em>{tool.tag}</em>
            <strong>{tool.title}</strong>
            <p>{tool.description}</p>
            <b>打开工具 →</b>
          </button>
        ))}
      </div>
    </div>
  )
}
