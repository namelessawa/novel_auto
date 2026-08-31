import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  cancelProduction,
  fetchBookOutline,
  fetchContextManifest,
  fetchLLMRuntime,
  fetchProductionSpec,
  fetchProductionStatus,
  generateBookOutline,
  pauseProduction,
  resumeProduction,
  retryFailedChapter,
  startProduction,
  watchProductionEvents,
} from '../../services/api'
import AsyncState, { InlineNotice } from '../components/AsyncState'
import ProviderFailurePanel from '../components/ProviderFailurePanel'
import { showToast } from '../../utils/toast'

const DEFAULT_API = {
  cancelProduction,
  fetchBookOutline,
  fetchContextManifest,
  fetchLLMRuntime,
  fetchProductionSpec,
  fetchProductionStatus,
  generateBookOutline,
  pauseProduction,
  resumeProduction,
  retryFailedChapter,
  startProduction,
  watchProductionEvents,
}

const ACTIVE_STATUSES = new Set([
  'queued',
  'running',
  'pausing',
  'paused',
  'cancelling',
])

export function deriveProductionActions(status, hasOutline = false) {
  const state = String(status?.status || status?.job_status || 'draft')
  const hasActiveJob = ACTIVE_STATUSES.has(state)
  return {
    start: hasOutline && ['draft', 'cancelled'].includes(state),
    pause: ['queued', 'running'].includes(state),
    resume: state === 'paused',
    cancel: hasActiveJob && !['cancelling', 'cancelled'].includes(state),
    retry: state === 'failed' && Boolean(
      status?.failed_chapter_id || status?.failed_chapter || status?.failure_code,
    ),
  }
}

export function isProductionReadyOutline(outline) {
  const state = String(outline?.status || '').toLowerCase()
  return (
    ['ready', 'locked'].includes(state) &&
    Boolean(outline?.chapters?.length)
  )
}

export function productionFailureCopy(code) {
  const normalized = String(code || '').trim().toUpperCase()
  const copies = {
    PROVIDER_AUTH_FAILED: {
      title: 'Provider 认证失败',
      message: '应用登录仍然有效；请更新 Provider 凭据后恢复任务。',
    },
    PROVIDER_RATE_LIMITED: {
      title: 'Provider 请求受限',
      message: '请求已达到限流重试上限，任务停在安全边界。',
    },
    PROVIDER_UNAVAILABLE: {
      title: 'Provider 暂时不可用',
      message: '网络或上游服务暂不可用，未提交任何半成品。',
    },
    PROVIDER_OUTPUT_INVALID: {
      title: 'Provider 输出无法解析',
      message: '模型输出未通过结构化契约，当前事务没有进入正式稿。',
    },
    PROVIDER_CONFIG_INVALID: {
      title: 'Provider 配置不可用',
      message: '请检查当前 Provider runtime 后再恢复生产。',
    },
  }
  if (copies[normalized]) return copies[normalized]
  if (normalized.startsWith('PROVIDER_')) {
    return {
      title: 'Provider 调用失败',
      message: '任务已保留在安全边界，请检查模型配置后重试。',
    }
  }
  return {
    title: '生产任务失败',
    message: '任务没有继续提交正文，请查看失败原因后重试。',
  }
}

export function applyProductionEvent(current, event) {
  const data = event?.data && typeof event.data === 'object'
    ? event.data
    : {}
  const nested = data.job || data.status_snapshot || {}
  const next = { ...(current || {}), ...nested, ...data }
  if (event?.type === 'paused') next.status = 'paused'
  if (event?.type === 'pausing') next.status = 'pausing'
  if (event?.type === 'cancelling') next.status = 'cancelling'
  if (event?.type === 'cancelled') next.status = 'cancelled'
  if (event?.type === 'completed') next.status = 'completed'
  if (event?.type === 'failed') next.status = 'failed'
  if (event?.type === 'chapter_committed') {
    next.completed_chapters =
      data.completed_chapters ?? (Number(current?.completed_chapters || 0) + 1)
    next.last_committed_at = data.committed_at || data.timestamp || next.last_committed_at
  }
  return next
}

export default function ProductionCenterView({
  novel,
  onNavigate,
  api = DEFAULT_API,
  notify = showToast,
}) {
  const [spec, setSpec] = useState(null)
  const [outline, setOutline] = useState(null)
  const [status, setStatus] = useState(null)
  const [runtime, setRuntime] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [actionBusy, setActionBusy] = useState('')
  const [streamState, setStreamState] = useState('idle')
  const [manifest, setManifest] = useState(null)
  const [manifestOpen, setManifestOpen] = useState(false)
  const [transactionOpen, setTransactionOpen] = useState(false)

  const load = useCallback(async () => {
    if (!novel?.id) return
    setLoading(true)
    setError('')
    const [specResult, outlineResult, statusResult, runtimeResult] =
      await Promise.allSettled([
        api.fetchProductionSpec(novel.id),
        api.fetchBookOutline(novel.id),
        api.fetchProductionStatus(novel.id),
        api.fetchLLMRuntime(),
      ])
    if (specResult.status === 'fulfilled') {
      setSpec(
        specResult.value?.production_spec ||
        specResult.value?.spec ||
        specResult.value,
      )
    }
    if (outlineResult.status === 'fulfilled') {
      setOutline(
        outlineResult.value?.book_outline ||
        outlineResult.value?.outline ||
        outlineResult.value,
      )
    }
    if (statusResult.status === 'fulfilled') {
      setStatus(
        statusResult.value?.job
          ? {
              ...(statusResult.value.summary || {}),
              ...statusResult.value.job,
            }
          : statusResult.value,
      )
    } else if (statusResult.reason?.status !== 404) {
      setError(statusResult.reason?.message || '生产状态读取失败')
    }
    if (runtimeResult.status === 'fulfilled') setRuntime(runtimeResult.value)
    if (specResult.status === 'rejected') {
      setError(specResult.reason?.message || '整书规格读取失败')
    }
    setLoading(false)
  }, [api, novel?.id])

  useEffect(() => {
    setSpec(null)
    setOutline(null)
    setStatus(null)
    setManifest(null)
    load()
  }, [load])

  useEffect(() => {
    const jobId = status?.id || status?.job_id
    if (!novel?.id || !jobId || !api.watchProductionEvents) {
      setStreamState('idle')
      return undefined
    }
    setStreamState('connecting')
    const stream = api.watchProductionEvents(novel.id, {
      jobId,
      onOpen: () => setStreamState('live'),
      onEvent: (event) => {
        setStatus((current) => applyProductionEvent(current, event))
        setStreamState('live')
      },
      onError: (streamError) => {
        setStreamState(streamError?.status === 404 ? 'idle' : 'retry')
      },
    })
    return () => stream?.abort?.()
  }, [api, novel?.id, status?.id, status?.job_id])

  const hasOutline = isProductionReadyOutline(outline)
  const actions = deriveProductionActions(status, hasOutline)
  const metrics = useMemo(
    () => productionMetrics(spec, status, outline),
    [spec, status, outline],
  )
  const providerCode =
    status?.failure_code || status?.error_code || status?.last_error?.code || ''
  const providerFailure = String(providerCode).startsWith('PROVIDER_')
  const failureCopy = productionFailureCopy(providerCode)
  const failureMessage =
    status?.failure_message || status?.last_error?.message || failureCopy.message
  const hasFailure = Boolean(
    providerCode || status?.failure_message || status?.status === 'failed',
  )

  async function perform(name, fn) {
    if (actionBusy) return
    setActionBusy(name)
    setError('')
    try {
      const result = await fn()
      setStatus(result?.job || result?.status_snapshot || result)
      notify(`${actionLabel(name)}请求已受理`, 'success')
      await load()
    } catch (actionError) {
      setError(actionError.message || `${actionLabel(name)}失败`)
      if (String(actionError.code || '').startsWith('PROVIDER_')) {
        setStatus((current) => ({
          ...(current || {}),
          status: 'paused',
          failure_code: actionError.code,
          last_error: {
            code: actionError.code,
            details: actionError.details,
          },
        }))
      }
    } finally {
      setActionBusy('')
    }
  }

  async function generateOutline() {
    await perform('outline', async () => {
      const result = await api.generateBookOutline(novel.id, {
        expected_spec_revision: spec?.revision,
      })
      const next = result?.book_outline || result?.outline || result
      setOutline(next)
      return status || { status: 'draft' }
    })
  }

  async function showManifest() {
    setManifestOpen((current) => !current)
    if (manifest || manifestOpen || !api.fetchContextManifest) return
    try {
      setManifest(await api.fetchContextManifest(novel.id))
    } catch (manifestError) {
      setError(manifestError.message || 'Context Manifest 读取失败')
    }
  }

  if (!novel?.id) {
    return (
      <AsyncState
        kind="empty"
        title="先创建或选择一部作品"
        detail="整书生产中心会在这里展示进度、章节与 Provider 状态。"
      />
    )
  }
  if (loading && !spec) return <AsyncState title="正在载入整书生产中心" />

  return (
    <div className="dc-view-switch dc-production-root" data-testid="production-center">
      <header className="dc-product-masthead">
        <div>
          <span className="dc-product-eyebrow">WHOLE BOOK · PRODUCTION</span>
          <h1>生产中心</h1>
          <p>{spec?.premise || '从整书规格与大纲开始，按章串行推进 Canon。'}</p>
        </div>
        <div className="dc-production-live">
          <span className={streamState === 'live' ? 'is-live' : ''} />
          {streamState === 'live' ? 'LIVE EVENTS' : streamState.toUpperCase()}
        </div>
      </header>

      {error && (
        <InlineNotice
          kind="error"
          actions={<button type="button" onClick={load}>重新读取</button>}
        >
          {error}
        </InlineNotice>
      )}

      {hasFailure && (
        <InlineNotice
          kind="error"
          actions={providerFailure ? (
            <button type="button" onClick={() => onNavigate?.('provider')}>
              打开 Provider 配置
            </button>
          ) : undefined}
        >
          <strong>{failureCopy.title}</strong>
          <p>{failureMessage}</p>
          {providerCode && <code>{providerCode}</code>}
        </InlineNotice>
      )}

      {providerCode === 'PROVIDER_AUTH_FAILED' && (
        <ProviderFailurePanel
          error={{
            code: providerCode,
            details:
              status?.last_error?.details || status?.failure_details || {},
          }}
          provider={status?.provider || runtime?.provider}
          model={status?.model || runtime?.model}
          source={status?.provider_source || runtime?.source}
          onOpenConfig={() => onNavigate?.('provider')}
          onRetry={() => onNavigate?.('provider')}
        />
      )}

      <section className="dc-progress-hero">
        <div className="dc-progress-ring" style={{ '--progress': `${metrics.percent}%` }}>
          <strong>{metrics.percent}%</strong>
          <span>完成</span>
        </div>
        <div className="dc-progress-copy">
          <span>当前生产状态</span>
          <h2>{statusLabel(status?.status || 'draft')}</h2>
          <p>
            第 {metrics.currentVolume || '—'} 卷 · 第 {metrics.currentChapter || '—'} 章 ·
            当前节 {metrics.currentSectionStatus || '未开始'}
          </p>
          <div className="dc-progress-track">
            <span style={{ width: `${metrics.percent}%` }} />
          </div>
        </div>
        <div className="dc-progress-totals">
          <div><strong>{metrics.completedChars.toLocaleString()}</strong><span>/ {metrics.targetChars.toLocaleString()} 字</span></div>
          <div><strong>{metrics.completedChapters}</strong><span>/ {metrics.totalChapters} 章</span></div>
        </div>
      </section>

      <section className="dc-production-metrics">
        <Metric label="JOB" value={String(status?.status || 'draft').toUpperCase()} />
        <Metric label="PROVIDER" value={runtime?.credential_present ? `${runtime.provider} · READY` : 'NOT READY'} />
        <Metric label="TOKENS" value={productionTokenTotal(status).toLocaleString()} />
        <Metric label="LATENCY" value={formatLatency(status)} />
        <Metric label="REPAIR" value={productionRepairTotal(status)} />
        <Metric label="LAST COMMIT" value={shortTime(status?.last_committed_at || status?.last_commit_at)} />
      </section>

      <section className="dc-production-actions">
        <header>
          <div>
            <span>CONTROL DESK</span>
            <h2>整书任务</h2>
          </div>
          <p>按钮严格跟随持久化 job 状态；同一作品不会创建第二个 active job。</p>
        </header>
        <div>
          {!hasOutline && (
            <button
              type="button"
              className="dc-btn"
              onClick={generateOutline}
              disabled={Boolean(actionBusy)}
            >
              {actionBusy === 'outline' ? '正在生成大纲…' : '生成整书大纲'}
            </button>
          )}
          <button
            type="button"
            className="dc-btn"
            onClick={() => perform('start', () => api.startProduction(novel.id, {
              expected_spec_revision: spec?.revision,
              expected_outline_revision: outline?.revision,
            }))}
            disabled={!actions.start || Boolean(actionBusy)}
          >
            {actionBusy === 'start' ? '启动中…' : '开始生产'}
          </button>
          <button
            type="button"
            className="dc-btn-ghost"
            onClick={() => perform('pause', () => api.pauseProduction(novel.id, {
              job_id: status?.id,
              expected_revision: status?.revision,
            }))}
            disabled={!actions.pause || Boolean(actionBusy)}
          >
            暂停
          </button>
          <button
            type="button"
            className="dc-btn-ghost"
            onClick={() => perform('resume', () => api.resumeProduction(novel.id, {
              job_id: status?.id,
              expected_revision: status?.revision,
            }))}
            disabled={!actions.resume || Boolean(actionBusy)}
          >
            恢复
          </button>
          <button
            type="button"
            className="dc-btn-ghost is-danger"
            onClick={() => perform('cancel', () => api.cancelProduction(novel.id, {
              job_id: status?.id,
              expected_revision: status?.revision,
            }))}
            disabled={!actions.cancel || Boolean(actionBusy)}
          >
            取消
          </button>
          <button
            type="button"
            className="dc-btn-ghost"
            onClick={() => perform('retry', () => api.retryFailedChapter(novel.id, {
              job_id: status?.id,
              expected_revision: status?.revision,
            }))}
            disabled={!actions.retry || Boolean(actionBusy)}
          >
            重试失败章节
          </button>
        </div>
      </section>

      <div className="dc-production-secondary">
        <button type="button" onClick={() => onNavigate?.('blueprint')}>
          <span>故事蓝图</span>
          <strong>
            {hasOutline
              ? `R${outline.revision || '—'}`
              : outline?.revision
                ? `R${outline.revision} · 未就绪`
                : '尚未生成'} →
          </strong>
        </button>
        <button type="button" onClick={() => setTransactionOpen((current) => !current)}>
          <span>当前事务</span><strong>{shortId(status?.active_transaction_id || status?.current_transaction_id || status?.transaction_id)} →</strong>
        </button>
        <button type="button" onClick={showManifest}>
          <span>脱敏 Context Manifest</span><strong>{manifestOpen ? '收起 ↑' : '查看 →'}</strong>
        </button>
      </div>

      {transactionOpen && (
        <section className="dc-production-detail">
          <span>CURRENT TRANSACTION</span>
          <pre>{JSON.stringify(safeTransaction(status), null, 2)}</pre>
        </section>
      )}
      {manifestOpen && (
        <section className="dc-production-detail">
          <span>CONTEXT MANIFEST · MASKED</span>
          {manifest
            ? <pre>{JSON.stringify(manifest, null, 2)}</pre>
            : <AsyncState compact title="正在读取 Context Manifest" />}
        </section>
      )}
    </div>
  )
}

function productionMetrics(spec, status, outline) {
  const targetChars = Number(spec?.target_total_chars || 0)
  const completedChars = Number(
    status?.completed_chars || status?.committed_chars || 0,
  )
  const totalChapters = Number(
    spec?.chapter_count || outline?.chapters?.length || 0,
  )
  const completedChapters = Number(
    status?.completed_chapters?.length ??
    status?.completed_chapter_ids?.length ??
    status?.completed_chapters ??
    0,
  )
  const percent = Math.max(
    0,
    Math.min(
      100,
      Math.round(
        Number(status?.progress_percent ?? (
          targetChars ? (completedChars / targetChars) * 100 : 0
        )),
      ),
    ),
  )
  return {
    targetChars,
    completedChars,
    totalChapters,
    completedChapters,
    percent,
    currentVolume: status?.current_volume || status?.current_volume_ordinal,
    currentChapter: status?.current_chapter || status?.current_chapter_ordinal,
    currentSectionStatus:
      status?.current_section_status ||
      status?.current_section_id ||
      status?.current_section ||
      '未开始',
  }
}

function Metric({ label, value }) {
  return <article><span>{label}</span><strong>{value ?? '—'}</strong></article>
}

export function productionTokenTotal(status) {
  if (
    status?.prompt_tokens_total != null ||
    status?.completion_tokens_total != null
  ) {
    return Number(status?.prompt_tokens_total || 0) +
      Number(status?.completion_tokens_total || 0)
  }
  return Number(status?.token_totals?.total_tokens || status?.total_tokens || 0)
}

export function productionRepairTotal(status) {
  return Number(
    status?.repair_total ??
    status?.repair_totals?.total ??
    status?.repair_count ??
    0,
  )
}

export function formatLatency(status) {
  const totalMs = status?.latency_total_ms
  if (totalMs != null) {
    const calls = Number(
      status?.provider_call_count ??
      status?.latency_sample_count ??
      0,
    )
    if (calls > 0) return `${(Number(totalMs) / calls / 1000).toFixed(2)}s avg`
    return `${(Number(totalMs) / 1000).toFixed(2)}s total`
  }
  const totalSeconds =
    status?.latency_totals?.total_seconds ??
    status?.latency_total_seconds ??
    0
  const calls =
    status?.latency_totals?.count ??
    status?.provider_call_count ??
    0
  return calls
    ? `${(Number(totalSeconds) / Number(calls)).toFixed(2)}s avg`
    : `${Number(totalSeconds).toFixed(2)}s total`
}

export function statusLabel(status) {
  const labels = {
    draft: '等待大纲',
    queued: '已排队',
    running: '正在生产',
    pausing: '将在安全边界暂停',
    paused: '已暂停',
    failed: '需要处理',
    cancelling: '正在安全取消',
    cancelled: '已取消',
    completed: '整书完成',
  }
  return labels[status] || String(status || 'draft')
}

function actionLabel(name) {
  return {
    start: '开始生产',
    pause: '暂停',
    resume: '恢复',
    cancel: '取消',
    retry: '重试',
    outline: '大纲生成',
  }[name] || name
}

function shortId(value) {
  if (!value) return '—'
  const text = String(value)
  return text.length > 14 ? `${text.slice(0, 12)}…` : text
}

function shortTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function safeTransaction(status) {
  return {
    transaction_id:
      status?.active_transaction_id ||
      status?.current_transaction_id ||
      status?.transaction_id ||
      null,
    chapter_id: status?.current_chapter_id || status?.failed_chapter_id || null,
    section_id: status?.current_section_id || null,
    story_bible_revision: status?.story_bible_revision || null,
    canonical_revision: status?.last_committed_canonical_revision || null,
    outline_revision: status?.requested_outline_revision || null,
    style_revision: status?.requested_style_revision || null,
    status: status?.current_section_status || status?.status || null,
  }
}
