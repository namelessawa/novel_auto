import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchAuthorSectionStatus,
  fetchCanonicalState,
  fetchContextManifest,
  fetchGenerationMode,
  fetchStoryBible,
  fetchStoryThreads,
  generateAuthorSection,
  listTickSections,
  updateGenerationMode,
} from '../../services/api'
import { showToast } from '../../utils/toast'

const DEFAULT_API = {
  fetchAuthorSectionStatus,
  fetchCanonicalState,
  fetchContextManifest,
  fetchGenerationMode,
  fetchStoryBible,
  fetchStoryThreads,
  generateAuthorSection,
  listTickSections,
  updateGenerationMode,
}

export default function AuthorStudioView({
  novel,
  onOpenSimulation,
  onModeChange,
  api = DEFAULT_API,
  notify = showToast,
}) {
  const [bible, setBible] = useState(null)
  const [canonical, setCanonical] = useState(null)
  const [threads, setThreads] = useState({})
  const [mode, setMode] = useState(null)
  const [sections, setSections] = useState([])
  const [manifest, setManifest] = useState(null)
  const [debugOpen, setDebugOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [modeBusy, setModeBusy] = useState(false)
  const [taskId, setTaskId] = useState('')
  const [generation, setGeneration] = useState(null)
  const [error, setError] = useState('')
  const [goal, setGoal] = useState({
    objective: '',
    viewpoint_character_id: '',
    location_id: '',
    involved_characters: '',
    target_threads: '',
    desired_length: 1800,
  })

  const load = useCallback(async () => {
    if (!novel?.id) return
    setLoading(true)
    setError('')
    try {
      const [bibleData, stateData, threadData, modeData, sectionData] = await Promise.all([
        api.fetchStoryBible(novel.id),
        api.fetchCanonicalState(novel.id),
        api.fetchStoryThreads(novel.id),
        api.fetchGenerationMode(novel.id),
        api.listTickSections(novel.id),
      ])
      setBible(bibleData.story_bible)
      setCanonical(stateData.canonical_state)
      setThreads(threadData.threads || {})
      setMode(modeData)
      setSections(sectionData.sections || [])
      setGoal((current) => ({
        ...current,
        objective: current.objective || bibleData.story_bible?.main_conflicts?.[0] || '',
      }))
    } catch (err) {
      setError(err.message || '创作台加载失败')
    } finally {
      setLoading(false)
    }
  }, [novel?.id, api])

  useEffect(() => {
    setTaskId('')
    setGeneration(null)
    setManifest(null)
    load()
  }, [load])

  useEffect(() => {
    if (!taskId || !novel?.id) return undefined
    let cancelled = false
    let timer = null
    async function poll() {
      try {
        const status = await api.fetchAuthorSectionStatus(novel.id, taskId)
        if (cancelled) return
        setGeneration(status)
        const taskStatus = status.task?.status
        const phase = status.transaction?.phase
        const terminal = ['completed', 'failed', 'cancelled'].includes(taskStatus)
          || ['committed', 'rejected', 'failed', 'stale_context'].includes(phase)
        if (!terminal) {
          timer = window.setTimeout(poll, 900)
          return
        }
        if (phase === 'committed' || status.task?.committed) {
          notify('正文与权威状态已提交', 'success')
        }
        const [manifestData] = await Promise.all([
          api.fetchContextManifest(novel.id).catch(() => null),
          load(),
        ])
        if (!cancelled && manifestData) setManifest(manifestData)
      } catch (err) {
        if (!cancelled) setError(err.message || '生成状态查询失败')
      }
    }
    poll()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [taskId, novel?.id, load, api, notify])

  const characters = Object.entries(canonical?.characters || {})
  const locations = useMemo(() => {
    const raw = canonical?.world?.locations || []
    if (Array.isArray(raw)) {
      return raw.map((item) => ({
        id: typeof item === 'string' ? item : item.id || item.name,
        label: typeof item === 'string' ? item : item.name || item.id,
      })).filter((item) => item.id)
    }
    return Object.keys(raw).map((id) => ({ id, label: raw[id]?.name || id }))
  }, [canonical])
  const activeThreads = Object.values(threads).filter(
    (thread) => !['resolved', 'abandoned'].includes(thread.status),
  )
  const lastSection = sections[sections.length - 1] || null
  const report = generation?.transaction?.validation_report
    || generation?.task?.validation_report
    || null
  const taskStatus = generation?.task?.status || (taskId ? 'queued' : 'idle')
  const generating = ['queued', 'running'].includes(taskStatus)

  async function switchMode(nextMode) {
    if (!mode || nextMode === mode.mode || modeBusy) return
    const message = nextMode === 'simulation'
      ? '世界模拟模式会装配多 Agent 实验运行时。权威状态仍由同一 Validator 提交。确认切换？'
      : '切回作者模式后，默认按创作圣经和章节目标生成。确认切换？'
    if (!window.confirm(message)) return
    setModeBusy(true)
    setError('')
    try {
      const updated = await api.updateGenerationMode(novel.id, mode.revision, nextMode)
      setMode((current) => ({ ...current, ...updated }))
      onModeChange?.(updated)
      notify(nextMode === 'author' ? '已切换为作者模式' : '实验性世界模拟已启用', 'success')
    } catch (err) {
      setError(
        err.code === 'REVISION_CONFLICT'
          ? '生成模式已在其他会话改变，请刷新。'
          : err.message || '模式切换失败',
      )
    } finally {
      setModeBusy(false)
    }
  }

  async function generate() {
    if (!goal.objective.trim()) {
      setError('请先写明本节目标。')
      return
    }
    setError('')
    setGeneration(null)
    try {
      const task = await api.generateAuthorSection(novel.id, {
        objective: goal.objective.trim(),
        viewpoint_character_id: goal.viewpoint_character_id,
        location_id: goal.location_id,
        involved_characters: splitIds(goal.involved_characters),
        target_threads: splitIds(goal.target_threads),
        desired_length: Number(goal.desired_length) || 1800,
      })
      setTaskId(task.id)
      setGeneration({ task, transaction: null, section: null })
      notify('章节事务已入队', 'success')
    } catch (err) {
      setError(err.message || '章节生成失败')
    }
  }

  if (!novel?.id) return <div className="dc-au-empty">请先选择作品。</div>
  if (loading && !bible) return <div className="dc-au-empty">正在展开创作台…</div>

  return (
    <div className="dc-view-switch dc-au-root dc-au-studio">
      <header className="dc-au-masthead">
        <div>
          <span className="dc-au-eyebrow">AUTHOR STUDIO · 单 Writer 章节事务</span>
          <h1>章节创作</h1>
          <p>固定上下文 → Writer 候选 → 一致性校验 → 最多一次修复 → 原子提交。</p>
        </div>
        <div className="dc-au-revision-pair">
          <div><span>BIBLE</span><strong>R{bible?.revision || '—'}</strong></div>
          <div><span>STATE</span><strong>R{canonical?.revision || '—'}</strong></div>
        </div>
      </header>
      {error && <div className="dc-au-notice is-error">{error}</div>}

      <section className="dc-au-mode-switch">
        <button
          type="button"
          className={mode?.mode === 'author' ? 'is-active' : ''}
          onClick={() => switchMode('author')}
          disabled={modeBusy}
        >
          <span>默认</span>
          <strong>作者模式</strong>
          <p>围绕创作圣经和本节目标写作；默认 1 次 Writer，必要时只修复 1 次。</p>
        </button>
        <button
          type="button"
          className={mode?.mode === 'simulation' ? 'is-active is-experimental' : 'is-experimental'}
          onClick={() => switchMode('simulation')}
          disabled={modeBusy}
        >
          <span>EXPERIMENTAL</span>
          <strong>世界模拟模式</strong>
          <p>多 Agent 先推进世界，再选择性叙述；共享同一 CanonicalState 与 Validator。</p>
        </button>
      </section>

      {mode?.mode === 'simulation' ? (
        <section className="dc-au-simulation-gate">
          <span>实验运行时已启用</span>
          <h2>当前作品由世界模拟推进</h2>
          <p>此区域属于高级实验工具。切回作者模式不会破坏正文、圣经或权威状态。</p>
          <button type="button" className="dc-btn" onClick={onOpenSimulation}>进入实验调度台</button>
        </section>
      ) : (
        <div className="dc-au-studio-grid">
          <section className="dc-au-goal-card">
            <div className="dc-au-card-number">01 · SECTION GOAL</div>
            <h2>这一节必须完成什么？</h2>
            <label>
              <span>本节目标</span>
              <textarea
                rows={6}
                value={goal.objective}
                onChange={(event) => setGoal((current) => ({ ...current, objective: event.target.value }))}
                placeholder="例如：让阿澜第一次为守住身份付出不可逆的关系代价，并推进潮门故事线。"
              />
            </label>
            <div className="dc-au-form-grid">
              <label>
                <span>视角人物</span>
                <select
                  value={goal.viewpoint_character_id}
                  onChange={(event) => setGoal((current) => ({ ...current, viewpoint_character_id: event.target.value }))}
                >
                  <option value="">自动选择</option>
                  {characters.map(([id, character]) => <option value={id} key={id}>{character.name || id}</option>)}
                </select>
              </label>
              <label>
                <span>起始地点</span>
                <select
                  value={goal.location_id}
                  onChange={(event) => setGoal((current) => ({ ...current, location_id: event.target.value }))}
                >
                  <option value="">沿用上一节</option>
                  {locations.map((location) => <option value={location.id} key={location.id}>{location.label}</option>)}
                </select>
              </label>
              <label>
                <span>涉及人物 ID</span>
                <input
                  value={goal.involved_characters}
                  onChange={(event) => setGoal((current) => ({ ...current, involved_characters: event.target.value }))}
                  placeholder="a, b"
                />
              </label>
              <label>
                <span>目标故事线 ID</span>
                <input
                  value={goal.target_threads}
                  onChange={(event) => setGoal((current) => ({ ...current, target_threads: event.target.value }))}
                  placeholder={activeThreads.slice(0, 2).map((thread) => thread.id).join(', ')}
                />
              </label>
              <label>
                <span>目标字数</span>
                <input
                  type="number"
                  min="200"
                  max="10000"
                  value={goal.desired_length}
                  onChange={(event) => setGoal((current) => ({ ...current, desired_length: event.target.value }))}
                />
              </label>
            </div>
            <button
              type="button"
              className="dc-au-generate"
              onClick={generate}
              disabled={generating || !bible || !canonical}
            >
              <span>{generating ? '事务执行中' : '生成并验证下一节'}</span>
              <em>{generating ? generation?.task?.progress?.last_message || 'PREPARING' : '1 WRITER · ≤1 REPAIR'}</em>
            </button>
          </section>

          <section className="dc-au-transaction-card">
            <div className="dc-au-card-number">02 · TRANSACTION</div>
            <h2>生成事务</h2>
            <TransactionTimeline generation={generation} />
            {generation?.transaction?.error_code === 'STORY_BIBLE_REVISION_STALE' && (
              <div className="dc-au-notice is-error" data-error-code="STORY_BIBLE_REVISION_STALE">
                创作圣经在生成期间发生了变化。本次候选基于旧版本，未提交，请重新生成。
              </div>
            )}
            {report && <ValidationPanel report={report} repaired={generation?.transaction?.repair_performed || generation?.task?.repair_performed} />}
            {!generation && (
              <div className="dc-au-transaction-empty">
                <span>尚未启动</span>
                <p>正文成功但状态提交失败时，不会被标记为正式章节。</p>
              </div>
            )}
          </section>
        </div>
      )}

      {lastSection && (
        <section className="dc-au-latest">
          <div className="dc-au-card-number">LATEST COMMITTED SECTION</div>
          <div className="dc-au-latest-head">
            <h2>{lastSection.title || `第 ${lastSection.section} 节`}</h2>
            <span>{lastSection.word_count || 0} 字 · STATE R{lastSection.canonical_state_revision || '—'}</span>
          </div>
          <p>{lastSection.content || '正文已提交，可在章节页阅读全文。'}</p>
        </section>
      )}

      <section className="dc-au-manifest">
        <button type="button" onClick={() => setDebugOpen((value) => !value)}>
          <span>{debugOpen ? '收起' : '查看'}脱敏 Context Manifest</span>
          <em>只显示槽位、字符数、引用 ID 与截断情况</em>
        </button>
        {debugOpen && (
          <div className="dc-au-slot-list">
            {manifest && (
              <div className="dc-au-manifest-total">
                <span>TOTAL</span>
                <strong>{manifest.total_chars} / {manifest.max_context_chars || '—'} chars</strong>
                <em>~{manifest.total_token_estimate} / {manifest.max_context_token_estimate || '—'} tokens</em>
                <i>{Math.round((manifest.budget_utilization || 0) * 100)}%</i>
              </div>
            )}
            {manifest?.rejected_reason && (
              <p className="dc-au-notice is-error">{manifest.rejected_reason}</p>
            )}
            {(manifest?.slots || []).map((slot, index) => (
              <div key={slot.name}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <strong>{slot.name}</strong>
                <em>{slot.char_count} chars · ~{slot.token_estimate} tokens</em>
                <i className={slot.truncated ? 'is-cut' : ''}>{slot.truncated ? 'TRUNCATED' : 'FULL'}</i>
              </div>
            ))}
            {!manifest?.slots?.length && <p>完成一次章节生成后会出现 context manifest。</p>}
          </div>
        )}
      </section>
    </div>
  )
}

function TransactionTimeline({ generation }) {
  const phase = generation?.transaction?.phase || generation?.task?.status || 'idle'
  const order = ['prepared', 'generated', 'validated', 'committed']
  const phaseIndex = phase === 'running' ? 1 : phase === 'completed' ? 3 : order.indexOf(phase)
  return (
    <ol className="dc-au-timeline">
      {[
        ['固定上下文', 'StoryBible + CanonicalState'],
        ['Writer 候选', '不直接写盘'],
        ['统一校验', '事实、知识、主题、故事线'],
        ['原子提交', '正文 + 状态 + 记忆'],
      ].map(([title, detail], index) => (
        <li className={phaseIndex >= index ? 'is-done' : ''} key={title}>
          <i>{phaseIndex > index ? '✓' : index + 1}</i>
          <div><strong>{title}</strong><span>{detail}</span></div>
        </li>
      ))}
    </ol>
  )
}

function ValidationPanel({ report, repaired }) {
  return (
    <div className={`dc-au-validation ${report.accepted ? 'is-ok' : 'is-fail'}`}>
      <div>
        <strong>{report.accepted ? '校验通过' : '校验未通过'}</strong>
        <span>{repaired ? '已执行一次定向修复' : '未执行修复'} · {report.severity}</span>
      </div>
      {(report.violations || []).map((violation) => (
        <p key={`${violation.code}-${violation.path}`}>
          <code>{violation.code}</code>{violation.message}
        </p>
      ))}
    </div>
  )
}

function splitIds(value) {
  return String(value || '').split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean)
}
