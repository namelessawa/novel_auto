import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  downloadAuthorEvidence,
  downloadAuthorManuscript,
  fetchAuthorSectionStatus,
  fetchAuthorLongRunStatus,
  fetchAuthorMemories,
  fetchAuthorTransactions,
  fetchCanonicalState,
  fetchContextManifest,
  fetchGenerationMode,
  fetchStoryBible,
  fetchStoryThreads,
  generateAuthorSection,
  listTickSections,
  previewAuthorNarrativeContract,
  resumeAuthorRecovery,
  updateGenerationMode,
} from '../../services/api'
import { showToast } from '../../utils/toast'

const DEFAULT_API = {
  downloadAuthorEvidence,
  downloadAuthorManuscript,
  fetchAuthorSectionStatus,
  fetchAuthorLongRunStatus,
  fetchAuthorMemories,
  fetchAuthorTransactions,
  fetchCanonicalState,
  fetchContextManifest,
  fetchGenerationMode,
  fetchStoryBible,
  fetchStoryThreads,
  generateAuthorSection,
  listTickSections,
  previewAuthorNarrativeContract,
  resumeAuthorRecovery,
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
  const [memories, setMemories] = useState([])
  const [memoryRevision, setMemoryRevision] = useState(0)
  const [transactions, setTransactions] = useState([])
  const [longRunStatus, setLongRunStatus] = useState(null)
  const [contractPreview, setContractPreview] = useState(null)
  const [contractOpen, setContractOpen] = useState(false)
  const [previewBusy, setPreviewBusy] = useState(false)
  const [debugOpen, setDebugOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [modeBusy, setModeBusy] = useState(false)
  const [recoveryBusy, setRecoveryBusy] = useState(false)
  const [exportBusy, setExportBusy] = useState('')
  const [recoveryResult, setRecoveryResult] = useState(null)
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
      const [
        bibleData,
        stateData,
        threadData,
        modeData,
        sectionData,
        manifestData,
        memoryData,
        transactionData,
        longRunData,
      ] = await Promise.all([
        api.fetchStoryBible(novel.id),
        api.fetchCanonicalState(novel.id),
        api.fetchStoryThreads(novel.id),
        api.fetchGenerationMode(novel.id),
        api.listTickSections(novel.id),
        api.fetchContextManifest
          ? api.fetchContextManifest(novel.id).catch(() => null)
          : Promise.resolve(null),
        api.fetchAuthorMemories
          ? api.fetchAuthorMemories(novel.id).catch(() => null)
          : Promise.resolve(null),
        api.fetchAuthorTransactions
          ? api.fetchAuthorTransactions(novel.id).catch(() => null)
          : Promise.resolve(null),
        api.fetchAuthorLongRunStatus
          ? api.fetchAuthorLongRunStatus(novel.id).catch(() => null)
          : Promise.resolve(null),
      ])
      setBible(bibleData.story_bible)
      setCanonical(stateData.canonical_state)
      setThreads(threadData.threads || {})
      setMode(modeData)
      setSections(sectionData.sections || [])
      if (manifestData) setManifest(manifestData)
      if (memoryData) {
        setMemories(memoryData.records || [])
        setMemoryRevision(memoryData.revision || 0)
      }
      if (transactionData) setTransactions(transactionData.transactions || [])
      if (longRunData) setLongRunStatus(longRunData)
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
    setContractPreview(null)
    setContractOpen(false)
    setRecoveryResult(null)
    load()
  }, [load])

  useEffect(() => {
    setContractPreview(null)
    setContractOpen(false)
  }, [
    goal.objective,
    goal.viewpoint_character_id,
    goal.location_id,
    goal.involved_characters,
    goal.target_threads,
    goal.desired_length,
  ])

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
  const authorityReport = generation?.transaction?.validation_report
    || generation?.task?.validation_report
    || null
  const narrativeReport = generation?.transaction?.narrative_validation_report
    || generation?.task?.narrative_validation_report
    || null
  const styleReport = generation?.transaction?.style_validation_report
    || generation?.task?.style_validation_report
    || null
  const activeContract = contractPreview
    ? contractPreview.narrative_contract
    : generation?.transaction?.narrative_contract
      || generation?.task?.narrative_contract
      || null
  const activeEventPlan = contractPreview
    ? contractPreview.event_execution_plan
    : generation?.transaction?.event_execution_plan
      || generation?.task?.event_execution_plan
      || null
  const activeWritingPlan = contractPreview
    ? contractPreview.section_writing_plan
    : generation?.transaction?.section_writing_plan
      || generation?.task?.section_writing_plan
      || null
  const activeBudgetPlan = contractPreview
    ? contractPreview.section_budget_plan
    : generation?.transaction?.section_budget_plan
      || generation?.task?.section_budget_plan
      || null
  const initialLengthReport = generation?.transaction?.initial_length_report
    || generation?.task?.initial_length_report
    || null
  const finalLengthReport = generation?.transaction?.final_length_report
    || generation?.task?.final_length_report
    || null
  const initialEndingReport = generation?.transaction?.initial_ending_report
    || generation?.task?.initial_ending_report
    || null
  const finalEndingReport = generation?.transaction?.final_ending_report
    || generation?.task?.final_ending_report
    || null
  const finalBalanceReport = generation?.transaction?.final_balance_report
    || generation?.task?.final_balance_report
    || null
  const taskStatus = generation?.task?.status || (taskId ? 'queued' : 'idle')
  const generating = ['queued', 'running'].includes(taskStatus)
  const selectedMemoryIds = new Set(manifest?.selected_memory_ids || [])
  const selectedMemories = memories.filter((item) => (
    item.selected || selectedMemoryIds.has(item.id)
  ))

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
      const task = await api.generateAuthorSection(novel.id, goalPayload(goal))
      setTaskId(task.id)
      setGeneration({ task, transaction: null, section: null })
      notify('章节事务已入队', 'success')
    } catch (err) {
      setError(err.message || '章节生成失败')
    }
  }

  async function previewContract() {
    if (!goal.objective.trim()) {
      setError('请先写明本节目标。')
      return
    }
    if (!api.previewAuthorNarrativeContract) {
      setError('当前 API 不支持正文契约预览。')
      return
    }
    setPreviewBusy(true)
    setError('')
    try {
      const data = await api.previewAuthorNarrativeContract(novel.id, goalPayload(goal))
      setContractPreview({
        narrative_contract: data.narrative_contract,
        event_execution_plan: data.event_execution_plan || null,
        section_writing_plan: data.section_writing_plan || null,
        section_budget_plan: data.section_budget_plan || null,
      })
      setContractOpen(true)
    } catch (err) {
      setError(err.message || '正文契约预览失败')
    } finally {
      setPreviewBusy(false)
    }
  }

  async function resumeRecovery() {
    if (!api.resumeAuthorRecovery || recoveryBusy) return
    setRecoveryBusy(true)
    setError('')
    try {
      const result = await api.resumeAuthorRecovery(novel.id)
      setRecoveryResult(result)
      await load()
      notify(
        result.recovered_transaction_ids?.length
          ? `已恢复 ${result.recovered_transaction_ids.length} 个待提交事务`
          : '没有需要恢复的事务',
        'success',
      )
    } catch (err) {
      setError(err.message || '恢复检查失败')
    } finally {
      setRecoveryBusy(false)
    }
  }

  async function exportArtifact(kind) {
    const downloader = kind === 'manuscript'
      ? api.downloadAuthorManuscript
      : api.downloadAuthorEvidence
    if (!downloader || exportBusy) return
    setExportBusy(kind)
    setError('')
    try {
      const artifact = await downloader(novel.id)
      saveArtifact(artifact)
      notify(
        `${kind === 'manuscript' ? '正式稿件' : '审计证据'}已导出`
          + (artifact?.sha256 ? ` · SHA-256 ${artifact.sha256.slice(0, 12)}…` : ''),
        'success',
      )
    } catch (err) {
      setError(err.message || '导出失败')
    } finally {
      setExportBusy('')
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
          <p>固定上下文与正文契约 → Writer 候选 → 正文/状态双校验 → 最多一次修复 → 原子提交。</p>
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
            <div className="dc-au-contract-preview">
              <button
                type="button"
                onClick={contractPreview ? () => setContractOpen((value) => !value) : previewContract}
                disabled={previewBusy || generating || !bible || !canonical}
              >
                <span>{previewBusy ? '正在构建正文契约…' : contractOpen ? '收起本节正文契约' : '查看本节正文契约'}</span>
                <em>默认折叠 · 不显示 Prompt 或模型分析</em>
              </button>
              {contractOpen && activeContract && (
                <ContractPreview
                  contract={activeContract}
                  eventPlan={activeEventPlan}
                  writingPlan={activeWritingPlan}
                  budgetPlan={activeBudgetPlan}
                />
              )}
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
            {(narrativeReport || authorityReport || styleReport) && (
              <ValidationPanel
                narrativeReport={narrativeReport}
                authorityReport={authorityReport}
                styleReport={styleReport}
                narrativeHistory={generation?.transaction?.narrative_validation_history || []}
                repaired={generation?.transaction?.repair_performed || generation?.task?.repair_performed}
                eventPlan={activeEventPlan}
                repairPlan={generation?.transaction?.repair_plan || generation?.task?.repair_plan}
                repairPatches={generation?.transaction?.repair_patches || generation?.task?.repair_patches}
                repairPatchReport={generation?.transaction?.repair_patch_report || generation?.task?.repair_patch_report}
                repairAuditCodes={generation?.transaction?.repair_audit_codes || generation?.task?.repair_audit_codes || []}
                initialLengthReport={initialLengthReport}
                finalLengthReport={finalLengthReport}
                initialEndingReport={initialEndingReport}
                finalEndingReport={finalEndingReport}
                finalBalanceReport={finalBalanceReport}
              />
            )}
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

      <section className="dc-au-evidence-ledger" data-testid="author-evidence-ledger">
        <header className="dc-au-evidence-head">
          <div>
            <div className="dc-au-card-number">03 · EVIDENCE LEDGER</div>
            <h2>权威上下文与事务证据</h2>
            <p>只展示冻结 revision、选择理由、确定性计划、校验差异与提交凭证。</p>
          </div>
          <div className="dc-au-evidence-actions">
            <button type="button" onClick={resumeRecovery} disabled={recoveryBusy}>
              <span>{recoveryBusy ? '检查中…' : '恢复待提交事务'}</span>
              <em>IDEMPOTENT</em>
            </button>
            <button
              type="button"
              onClick={() => exportArtifact('manuscript')}
              disabled={Boolean(exportBusy)}
            >
              <span>{exportBusy === 'manuscript' ? '导出中…' : '导出正式稿件'}</span>
              <em>COMMITTED ONLY</em>
            </button>
            <button
              type="button"
              onClick={() => exportArtifact('evidence')}
              disabled={Boolean(exportBusy)}
            >
              <span>{exportBusy === 'evidence' ? '导出中…' : '导出审计证据'}</span>
              <em>JSON + SHA-256</em>
            </button>
          </div>
        </header>

        {recoveryResult && (
          <div className="dc-au-recovery-result" data-testid="author-recovery-result">
            <strong>{recoveryResult.status === 'recovered' ? 'RECOVERED' : 'CLEAN'}</strong>
            <span>
              恢复 {recoveryResult.recovered_transaction_ids?.length || 0} ·
              尚待处理 {recoveryResult.pending_after?.length || 0}
            </span>
          </div>
        )}

        <div className="dc-au-authority-stamps">
          <div><span>STORY BIBLE</span><strong>R{bible?.revision || '—'}</strong></div>
          <div><span>CANONICAL STATE</span><strong>R{canonical?.revision || '—'}</strong></div>
          <div><span>MEMORY LEDGER</span><strong>R{memoryRevision || '—'}</strong></div>
          <div>
            <span>CONTRACT HASH</span>
            <strong title={manifest?.contract_hash || ''}>
              {shortHash(manifest?.contract_hash)}
            </strong>
          </div>
          <div>
            <span>EXECUTION SPEC</span>
            <strong title={manifest?.execution_spec_hash || ''}>
              {shortHash(manifest?.execution_spec_hash)}
            </strong>
          </div>
        </div>

        <div className="dc-au-evidence-grid">
          <section>
            <header><span>SELECTED MEMORY</span><strong>{selectedMemories.length}</strong></header>
            <div className="dc-au-evidence-list">
              {selectedMemories.map((memory) => (
                <article key={memory.id}>
                  <div>
                    <code>{memory.type || 'memory'} · R{memory.created_at_revision || 0}</code>
                    <em>{memory.canon_status || 'confirmed'}</em>
                  </div>
                  <strong>{memory.summary || memory.id}</strong>
                  <p>{memory.id} · importance {memory.importance ?? '—'}</p>
                </article>
              ))}
              {!selectedMemories.length && (
                <p className="dc-au-evidence-empty">本次 ContextManifest 未选择长期记忆。</p>
              )}
            </div>
          </section>

          <section>
            <header><span>ACTIVE THREADS</span><strong>{activeThreads.length}</strong></header>
            <div className="dc-au-evidence-list">
              {activeThreads.map((thread) => (
                <article key={thread.id || thread.description}>
                  <div>
                    <code>{thread.id || 'thread'}</code>
                    <em>{thread.status || 'open'}</em>
                  </div>
                  <strong>{thread.description || thread.id}</strong>
                  <p>
                    urgency {thread.urgency ?? '—'} · progress R
                    {thread.last_progress_revision ?? thread.last_advanced_revision ?? '—'}
                  </p>
                </article>
              ))}
              {!activeThreads.length && (
                <p className="dc-au-evidence-empty">没有活跃故事线。</p>
              )}
            </div>
          </section>
        </div>

        <section className="dc-au-transaction-ledger">
          <header>
            <span>TRANSACTION RECEIPTS</span>
            <strong>{transactions.length}</strong>
          </header>
          <div>
            {transactions.slice(0, 12).map((transaction) => (
              <article
                className={`is-${transaction.phase}`}
                key={transaction.id}
                data-transaction-phase={transaction.phase}
              >
                <div className="dc-au-receipt-id">
                  <code>{transaction.id}</code>
                  <strong>{transaction.phase?.toUpperCase()}</strong>
                </div>
                <div className="dc-au-receipt-revisions">
                  <span>BIBLE R{transaction.story_bible_revision}</span>
                  <span>
                    STATE R{transaction.canonical_state_revision}
                    →R{transaction.target_canonical_revision}
                  </span>
                </div>
                <div className="dc-au-receipt-gates">
                  <span>INITIAL {gateLabel(transaction.initial_preflight_report)}</span>
                  <span>
                    REPAIR {transaction.repair_performed
                      ? `Δ${transaction.repair_patch_report?.char_delta ?? '—'}`
                      : 'SKIP'}
                  </span>
                  <span>FINAL {gateLabel(transaction.final_preflight_report)}</span>
                </div>
                <div className="dc-au-receipt-metrics">
                  <span>{transaction.writer_calls || 0} Writer</span>
                  <span>{transaction.planner_calls || 0} Planner</span>
                  <span>{transaction.usage?.total_tokens || 0} tokens</span>
                  <span>{elapsedSeconds(transaction)}s</span>
                </div>
                {(transaction.error_code || transaction.error) && (
                  <p className="dc-au-reject-reason">
                    <code>{transaction.error_code || 'REJECTED'}</code>
                    {transaction.error || '事务未提交'}
                  </p>
                )}
              </article>
            ))}
            {!transactions.length && (
              <p className="dc-au-evidence-empty">尚无章节事务凭证。</p>
            )}
          </div>
        </section>
      </section>

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
            {(manifest?.budget_utilization || 0) >= 0.85 && !manifest?.rejected_reason && (
              <p className="dc-au-notice is-warning" data-warning="context-budget">
                Context 已使用 {Math.round(manifest.budget_utilization * 100)}%，不可变规则不会被静默截断。
              </p>
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
            {longRunStatus && <LongRunStatus status={longRunStatus} />}
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
        ['固定上下文', 'StoryBible + CanonicalState + NarrativeContract'],
        ['Writer 候选', '不直接写盘'],
        ['分层校验', '正文契约 → 权威状态 → 风格观察'],
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

function ContractPreview({ contract, eventPlan, writingPlan, budgetPlan }) {
  const groups = [
    ['SectionBudget 分段', (budgetPlan?.segments || writingPlan?.structure || []).map((item) => (
      item.name
        ? `${item.name} · 约 ${item.budget} 字 · 最多 ${item.max_chars} 字`
        : `${item.part} · ${item.target_chars} 字 · ${item.purpose}`
    ))],
    ['停止条件', budgetPlan?.stop_conditions || []],
    ['风格平衡限制', budgetPlan?.style_balance_contract?.limits || []],
    ['风格平衡禁止', budgetPlan?.style_balance_contract?.forbidden || []],
    ['风格扩写允许', writingPlan?.style_adaptation?.allowed_expansion || []],
    ['风格扩写禁止', writingPlan?.style_adaptation?.forbidden_expansion || []],
    ['执行顺序', (eventPlan?.ordered_events || []).map((item) => `${item.order}. ${item.description || `${item.actor || ''} ${item.action || ''} ${item.target || ''}`}`)],
    ['必须发生', (contract.required_events || []).map((item) => item.description || `${item.actor || ''} ${item.action || ''} ${item.target || ''}`)],
    ['最终必须达到', (contract.required_end_state || []).map((item) => item.description || `${item.path} = ${String(item.expected)}`)],
    ['不得新增', contract.forbidden_additions || []],
    ['时间限制', (contract.time_constraints || []).map((item) => item.description || item.deadline)],
    ['允许人物', (contract.allowed_entities?.characters || []).map((item) => item.name || item.id)],
  ]
  return (
    <div className="dc-au-contract-grid" data-testid="narrative-contract-preview">
      {groups.map(([label, values]) => (
        <div key={label}>
          <strong>{label}</strong>
          {values.length
            ? <ul>{values.map((value, index) => <li key={`${label}-${index}`}>{value}</li>)}</ul>
            : <p>本节没有额外条目</p>}
        </div>
      ))}
      <div>
        <strong>服务端长度目标</strong>
        <p>
          {budgetPlan?.target_chars || writingPlan?.target_chars || '—'} 字 · 接受区间 {budgetPlan?.min_chars || writingPlan?.min_chars || contract.length_constraint?.min_chars || '—'}—{budgetPlan?.max_chars || writingPlan?.max_chars || contract.length_constraint?.max_chars || '—'} 字
        </p>
      </div>
    </div>
  )
}

function ValidationPanel({
  narrativeReport,
  authorityReport,
  styleReport,
  narrativeHistory,
  repaired,
  eventPlan,
  repairPlan,
  repairPatches,
  repairPatchReport,
  repairAuditCodes,
  initialLengthReport,
  finalLengthReport,
  initialEndingReport,
  finalEndingReport,
  finalBalanceReport,
}) {
  const accepted = Boolean(narrativeReport?.accepted && authorityReport?.accepted)
  return (
    <div className={`dc-au-validation ${accepted ? 'is-ok' : 'is-fail'}`}>
      <div>
        <strong>{accepted ? '两类硬契约通过' : '契约校验未通过'}</strong>
        <span>{repaired ? '已执行一次定向修复' : '未执行修复'}</span>
      </div>
      {repaired && narrativeHistory.length >= 2 && (
        <p className="dc-au-repair-result" data-testid="repair-result">
          正文契约：修复前 {narrativeHistory[0].accepted ? '通过' : '未通过'} → 修复后 {narrativeHistory.at(-1).accepted ? '通过' : '未通过'}
        </p>
      )}
      {(initialLengthReport || finalLengthReport) && (
        <section className="dc-au-validation-group" data-validation-layer="section-length">
          <header><strong>章节长度</strong><span>{finalLengthReport?.accepted ? 'PASS' : 'ATTENTION'}</span></header>
          {initialLengthReport && (
            <p data-testid="initial-length-report">
              <code>INITIAL</code>{initialLengthReport.chars}/{initialLengthReport.target} 字 · ratio {initialLengthReport.ratio}
            </p>
          )}
          {finalLengthReport && (
            <p data-testid="final-length-report">
              <code>{finalLengthReport.phase?.toUpperCase() || 'FINAL'}</code>
              {finalLengthReport.chars}/{finalLengthReport.target} 字 · ratio {finalLengthReport.ratio}
              {finalLengthReport.violation_code ? ` · ${finalLengthReport.violation_code}` : ''}
            </p>
          )}
        </section>
      )}
      {(initialEndingReport || finalEndingReport) && (
        <section className="dc-au-validation-group" data-validation-layer="ending-completion">
          <header><strong>Ending Gate</strong><span>{finalEndingReport?.accepted ? 'PASS' : 'COMPACT'}</span></header>
          <p data-testid="ending-completion-report">
            终态后字符 {finalEndingReport?.post_resolution_chars ?? initialEndingReport?.post_resolution_chars ?? 0}
            {finalEndingReport?.violation_code ? ` · ${finalEndingReport.violation_code}` : ''}
          </p>
        </section>
      )}
      {finalBalanceReport && (
        <section className="dc-au-validation-group" data-validation-layer="section-balance">
          <header><strong>联合门禁</strong><span>{finalBalanceReport.accepted ? 'PASS' : 'FAIL'}</span></header>
          <p data-testid="section-balance-report">
            Event {finalBalanceReport.event_pass ? 'PASS' : 'FAIL'} · EndState {finalBalanceReport.end_state_pass ? 'PASS' : 'FAIL'} · Length {finalBalanceReport.length_pass ? 'PASS' : 'FAIL'} · Ending {finalBalanceReport.ending_pass ? 'PASS' : 'FAIL'}
          </p>
        </section>
      )}
      <EventCompletionGroup report={narrativeReport} eventPlan={eventPlan} />
      <EndStateGroup report={narrativeReport} />
      <ValidationGroup
        title="正文契约"
        report={narrativeReport}
        excludeCodes={['REQUIRED_EVENT_', 'END_STATE_']}
      />
      <ValidationGroup
        title="状态变更"
        report={authorityReport}
        excludeCodes={['THREAD_']}
        proposalKind="delta"
      />
      <ValidationGroup
        title="故事线提案"
        report={authorityReport}
        includeCodes={['THREAD_']}
        proposalKind="thread"
      />
      <ValidationGroup title="风格检查" report={styleReport} observational />
      {repairPlan && (
        <RepairPlanSummary
          plan={repairPlan}
          patches={repairPatches}
          patchReport={repairPatchReport}
          auditCodes={repairAuditCodes}
        />
      )}
    </div>
  )
}

function EventCompletionGroup({ report, eventPlan }) {
  if (!report?.event_results?.length && !eventPlan?.ordered_events?.length) return null
  const statuses = new Map((report?.event_results || []).map((item) => [item.event_id, item]))
  const events = eventPlan?.ordered_events?.length
    ? eventPlan.ordered_events
    : (report.event_results || []).map((item, index) => ({ id: item.event_id, order: index + 1 }))
  return (
    <section className="dc-au-validation-group" data-validation-layer="event-completion">
      <header><strong>事件完成状态</strong><span>{report?.accepted ? 'CHECKED' : 'ATTENTION'}</span></header>
      {events.map((event) => {
        const result = statuses.get(event.id)
        return (
          <p key={event.id} data-event-status={result?.status || 'unchecked'}>
            <code>{event.order}. {event.id}</code>
            {result?.status || 'unchecked'}
            {result?.evidence ? ` · ${result.evidence}` : ''}
          </p>
        )
      })}
    </section>
  )
}

function EndStateGroup({ report }) {
  const violations = (report?.violations || []).filter((item) => item.code?.startsWith('END_STATE_'))
  if (!report?.end_state_results?.length && !violations.length) return null
  return (
    <section className="dc-au-validation-group" data-validation-layer="end-state">
      <header><strong>最终状态</strong><span>CHECKED</span></header>
      {(report.end_state_results || []).map((item) => (
        <p key={item.id} data-end-state={item.reached ? 'reached' : 'missing'}>
          <code>{item.id}</code>
          {item.path} = {String(item.expected)} · {item.reached ? 'reached' : item.violation_code || 'missing'}
        </p>
      ))}
      {violations.map((item, index) => (
        <p key={`${item.code}-${item.path || index}`}>
          <code>{item.code}</code>{item.message}
        </p>
      ))}
    </section>
  )
}

function RepairPlanSummary({ plan, patches, patchReport, auditCodes = [] }) {
  const metrics = [
    ['missing', plan.missing_events?.length || 0],
    ['incomplete', plan.incomplete_events?.length || 0],
    ['wrong actor', plan.wrong_actor_events?.length || 0],
    ['wrong target', plan.wrong_target_events?.length || 0],
    ['end state', plan.wrong_end_states?.length || 0],
    ['unsupported', plan.unsupported_additions?.length || 0],
  ]
  const patchItems = patches?.patches || []
  const patchTypes = patchItems.map((item) => item.patch_type).join(' / ')
  const patchCodes = patchReport?.violations?.map((item) => item.code) || []
  return (
    <section className="dc-au-validation-group" data-validation-layer="repair-plan">
      <header><strong>RepairPlan 摘要</strong><span>PATCH MODE</span></header>
      <p>{metrics.map(([label, value]) => `${label}: ${value}`).join(' · ')}</p>
      <p><code>preserve</code>{plan.must_preserve_spans?.length || 0} spans / {plan.must_preserve_facts?.length || 0} facts</p>
      <p data-testid="repair-patch-summary">
        <code>{patchReport?.accepted ? 'PATCH APPLIED' : 'PATCH BLOCKED'}</code>
        {patchItems.length} local patch(es){patchTypes ? ` · ${patchTypes}` : ''}
        {typeof patchReport?.char_delta === 'number' ? ` · Δ${patchReport.char_delta} chars` : ''}
      </p>
      {patchCodes.length > 0 && (
        <p data-testid="repair-patch-codes">
          <code>PATCH VALIDATOR</code>{patchCodes.join(' · ')}
        </p>
      )}
      {auditCodes.length > 0 && (
        <p data-testid="repair-audit-codes">
          <code>AUDIT</code>{auditCodes.join(' · ')}
        </p>
      )}
    </section>
  )
}

function ValidationGroup({
  title,
  report,
  observational = false,
  includeCodes = [],
  excludeCodes = [],
  proposalKind = '',
}) {
  if (!report) return null
  const passed = report.passed ?? report.accepted
  const findings = (report.violations || report.findings || []).filter((violation) => {
    if (includeCodes.length && !includeCodes.some((prefix) => violation.code?.startsWith(prefix))) return false
    return !excludeCodes.some((prefix) => violation.code?.startsWith(prefix))
  })
  const dropCount = proposalKind === 'delta'
    ? report.dropped_delta_count
    : proposalKind === 'thread'
      ? report.dropped_thread_change_count
      : 0
  return (
    <section className="dc-au-validation-group" data-validation-layer={title}>
      <header>
        <strong>{title}</strong>
        <span>{observational ? '事实通过后观察' : passed ? 'PASS' : 'BLOCKED'}</span>
      </header>
      {typeof report.contract_coverage === 'number' && (
        <p>契约覆盖率 {Math.round(report.contract_coverage * 100)}%</p>
      )}
      {dropCount > 0 && <p data-proposal-drops={proposalKind}><code>DROPPED</code>{dropCount}</p>}
      {(report.missing_required_events || []).map((eventId) => (
        <p key={`missing-${eventId}`}><code>缺失事件</code>{eventId}</p>
      ))}
      {findings.map((violation, index) => (
        <p key={`${violation.code}-${violation.path || index}`}>
          <code>{violation.code}</code>{violation.message}
        </p>
      ))}
    </section>
  )
}

function LongRunStatus({ status }) {
  const metrics = [
    ['当前运行', status.run_id || '—'],
    ['已完成章节', status.completed_sections || 0],
    ['合同通过率', `${Math.round((status.contract_pass_rate || 0) * 100)}%`],
    ['Repair 率', `${Math.round((status.repair_rate || 0) * 100)}%`],
    ['硬拒绝', status.hard_reject_count || 0],
    ['Canonical', `R${status.canonical_revision || 0}`],
    ['Token', status.total_tokens || 0],
    ['平均耗时', `${status.average_latency_seconds || 0}s`],
    ['重启恢复', status.restart_recovery_count || 0],
  ]
  return (
    <section className="dc-au-longrun" data-testid="author-longrun-status">
      <h3>LONG-RUN STATUS</h3>
      <div>{metrics.map(([label, value]) => <p key={label}><span>{label}</span><strong>{value}</strong></p>)}</div>
    </section>
  )
}

function goalPayload(goal) {
  return {
    objective: goal.objective.trim(),
    viewpoint_character_id: goal.viewpoint_character_id,
    location_id: goal.location_id,
    involved_characters: splitIds(goal.involved_characters),
    target_threads: splitIds(goal.target_threads),
    desired_length: Number(goal.desired_length) || 1800,
  }
}

function splitIds(value) {
  return String(value || '').split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean)
}

function shortHash(value) {
  return value ? `${String(value).slice(0, 10)}…` : '—'
}

function gateLabel(report) {
  if (!report) return '—'
  return (report.accepted ?? report.passed) ? 'PASS' : 'FAIL'
}

function elapsedSeconds(transaction) {
  const start = Date.parse(transaction.created_at || '')
  const end = Date.parse(transaction.updated_at || '')
  if (!Number.isFinite(start) || !Number.isFinite(end)) return 0
  return Math.max(0, Math.round((end - start) / 100) / 10)
}

function saveArtifact(artifact) {
  if (!artifact?.blob || typeof document === 'undefined' || typeof URL === 'undefined') return
  const href = URL.createObjectURL(artifact.blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = artifact.filename || 'novel-auto-artifact'
  anchor.click()
  URL.revokeObjectURL(href)
}
