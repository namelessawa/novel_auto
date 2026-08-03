import React, { useCallback, useEffect, useState } from 'react'
import {
  fetchLLMProviders,
  fetchLLMRuntime,
  getUserLLMConfigSummary,
  probeLLMConfig,
  setUserLLMConfig,
} from '../../services/api'
import ProviderConfigPanel, {
  normalizeProviderCatalog,
  providerDraftFrom,
} from '../components/ProviderConfigPanel'
import AsyncState, { InlineNotice } from '../components/AsyncState'
import { showToast } from '../../utils/toast'

const DEFAULT_API = {
  fetchLLMProviders,
  fetchLLMRuntime,
  probeLLMConfig,
  getUserLLMConfigSummary,
  setUserLLMConfig,
}

export default function ProviderConfigView({
  api = DEFAULT_API,
  notify = showToast,
}) {
  const [providers, setProviders] = useState([])
  const [runtime, setRuntime] = useState(null)
  const [draft, setDraft] = useState(() =>
    providerDraftFrom({ local: api.getUserLLMConfigSummary?.() || {} }),
  )
  const [persistence, setPersistence] = useState(
    api.getUserLLMConfigSummary?.().source === 'device' ? 'device' : 'session',
  )
  const [loading, setLoading] = useState(true)
  const [catalogError, setCatalogError] = useState('')
  const [probe, setProbe] = useState(null)
  const [probeBusy, setProbeBusy] = useState(false)
  const [saved, setSaved] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setCatalogError('')
    const [catalogResult, runtimeResult] = await Promise.allSettled([
      api.fetchLLMProviders(),
      api.fetchLLMRuntime(),
    ])
    const nextProviders = catalogResult.status === 'fulfilled'
      ? normalizeProviderCatalog(catalogResult.value)
      : []
    const nextRuntime = runtimeResult.status === 'fulfilled'
      ? runtimeResult.value
      : null
    setProviders(nextProviders)
    setRuntime(nextRuntime)
    if (catalogResult.status === 'rejected') {
      setCatalogError(catalogResult.reason?.message || '后端 catalog 不可用')
    }
    setDraft(providerDraftFrom({
      runtime: nextRuntime || {},
      local: api.getUserLLMConfigSummary?.() || {},
      providers: nextProviders,
    }))
    setLoading(false)
  }, [api])

  useEffect(() => {
    load()
  }, [load])

  async function runProbe() {
    setProbeBusy(true)
    setProbe(null)
    try {
      const result = await api.probeLLMConfig(draft)
      setProbe(result)
    } catch (error) {
      setProbe({
        success: false,
        code: error.code,
        message: error.message,
        details: error.details,
      })
    } finally {
      setProbeBusy(false)
    }
  }

  function save() {
    if (draft.credential_required && !draft.api_key?.trim()) {
      notify('Provider 或 Base URL 已改变，请先重新输入 API key', 'error')
      return
    }
    api.setUserLLMConfig(draft, { remember: persistence === 'device' })
    setSaved(true)
    notify(
      persistence === 'device'
        ? 'Provider 配置已保存在此设备'
        : 'Provider 配置仅在本次会话有效',
      'success',
    )
  }

  if (loading && !runtime && providers.length === 0) {
    return <AsyncState title="正在读取 Provider catalog" />
  }

  return (
    <div className="dc-view-switch dc-production-root">
      <header className="dc-product-masthead">
        <div>
          <span className="dc-product-eyebrow">PROVIDER · RUNTIME</span>
          <h1>Provider 配置</h1>
          <p>凭据按请求解析；catalog 始终来自后端，不在浏览器维护第二份列表。</p>
        </div>
        <button
          type="button"
          className="dc-btn"
          onClick={save}
          disabled={Boolean(draft.credential_required)}
        >
          保存配置
        </button>
      </header>

      {saved && (
        <InlineNotice kind="success">
          {persistence === 'device'
            ? '配置保存在当前浏览器设备；完整 key 不会重新显示。'
            : '配置只保存在当前页面会话；关闭页面后失效。'}
        </InlineNotice>
      )}

      <ProviderConfigPanel
        providers={providers}
        value={draft}
        onChange={(next) => {
          setDraft(next)
          setSaved(false)
          setProbe(null)
        }}
        persistence={persistence}
        onPersistenceChange={setPersistence}
        runtime={runtime}
        probe={probe}
        probeBusy={probeBusy}
        onProbe={runProbe}
        catalogLoading={loading}
        catalogError={catalogError}
      />

      <section className="dc-runtime-ledger">
        <header>
          <span>当前脱敏运行时</span>
          <button type="button" onClick={load}>刷新</button>
        </header>
        <dl>
          <RuntimeRow label="provider" value={runtime?.provider} />
          <RuntimeRow label="model" value={runtime?.model} />
          <RuntimeRow label="source" value={runtime?.source} />
          <RuntimeRow label="thinking" value={runtime?.thinking_mode} />
          <RuntimeRow label="timeout" value={runtime?.timeout} />
          <RuntimeRow label="retries" value={runtime?.retries} />
          <RuntimeRow
            label="credential"
            value={runtime?.credential_present ? runtime.key_fingerprint || 'present' : 'missing'}
          />
          <RuntimeRow label="fingerprint" value={runtime?.config_fingerprint} />
        </dl>
      </section>
    </div>
  )
}

function RuntimeRow({ label, value }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd title={String(value ?? '')}>{value ?? '—'}</dd>
    </div>
  )
}
