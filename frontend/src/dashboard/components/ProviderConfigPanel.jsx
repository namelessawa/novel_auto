import React from 'react'

export function normalizeProviderCatalog(payload) {
  const raw = payload?.providers || payload?.items || payload || []
  if (!Array.isArray(raw)) return []
  return raw
    .map((item) => ({
      key: item.provider || item.key || item.id || '',
      label: item.label || item.name || item.provider || item.key || '',
      defaultBaseUrl:
        item.default_base_url || item.base_url || item.base || '',
      defaultModel: item.default_model || item.model || '',
    }))
    .filter((item) => item.key)
}

export function providerDraftFrom({
  runtime = {},
  local = {},
  providers = [],
} = {}) {
  const useServerRuntime = Boolean(
    !local.credential_present && runtime.credential_present,
  )
  const source = useServerRuntime ? runtime : local
  const provider =
    source.provider || runtime.provider || local.provider || providers[0]?.key || ''
  const descriptor = providers.find((item) => item.key === provider)
  return {
    provider,
    model:
      source.model || runtime.model || local.model || descriptor?.defaultModel || '',
    base_url: useServerRuntime
      ? ''
      : local.base_url || descriptor?.defaultBaseUrl || '',
    api_key: '',
    thinking_mode:
      source.thinking_mode || runtime.thinking_mode || 'disabled',
    timeout: Number(source.timeout || runtime.timeout || 600),
    max_retries: Number(
      source.max_retries ?? runtime.retries ?? runtime.max_retries ?? 0,
    ),
    credential_present: Boolean(
      local.credential_present || runtime.credential_present,
    ),
    credential_required: false,
  }
}

export default function ProviderConfigPanel({
  providers = [],
  value,
  onChange,
  persistence = 'session',
  onPersistenceChange,
  runtime,
  probe,
  probeBusy,
  onProbe,
  catalogLoading,
  catalogError,
  compact = false,
}) {
  const selected = providers.find((item) => item.key === value.provider)
  const update = (patch) => onChange?.({ ...value, ...patch })

  function selectProvider(key) {
    const descriptor = providers.find((item) => item.key === key)
    const nextBaseUrl = descriptor?.defaultBaseUrl || value.base_url
    const identityChanged = (
      key !== value.provider ||
      nextBaseUrl.replace(/\/+$/, '') !==
        String(value.base_url || '').replace(/\/+$/, '')
    )
    update({
      provider: key,
      model: descriptor?.defaultModel || value.model,
      base_url: nextBaseUrl,
      api_key: identityChanged ? '' : value.api_key,
      credential_required:
        identityChanged &&
        Boolean(
          value.api_key ||
          value.credential_present ||
          value.credential_required,
        ),
    })
  }

  return (
    <section
      className={`dc-provider-panel ${compact ? 'is-compact' : ''}`}
      data-testid="provider-config-panel"
    >
      <header className="dc-provider-panel-head">
        <div>
          <span className="dc-card-kicker">MODEL RUNTIME</span>
          <h3>模型与凭据</h3>
        </div>
        <RuntimeBadge runtime={runtime} probe={probe} />
      </header>

      {catalogLoading && (
        <p className="dc-provider-catalog-state">正在从后端读取 Provider…</p>
      )}
      {catalogError && (
        <p className="dc-provider-catalog-state is-error">
          Provider 列表读取失败：{catalogError}
        </p>
      )}
      {!catalogLoading && !catalogError && providers.length === 0 && (
        <p className="dc-provider-catalog-state is-error">
          后端没有返回可用 Provider。前端不会使用硬编码回退列表。
        </p>
      )}

      <div className="dc-provider-catalog" role="list" aria-label="Provider 列表">
        {providers.map((item) => (
          <button
            type="button"
            role="listitem"
            key={item.key}
            className={value.provider === item.key ? 'is-active' : ''}
            onClick={() => selectProvider(item.key)}
          >
            <strong>{item.label}</strong>
            <span>{item.defaultModel || '自定义模型'}</span>
          </button>
        ))}
      </div>

      <div className="dc-provider-fields">
        <label>
          <span>model</span>
          <input
            value={value.model}
            onChange={(event) => update({ model: event.target.value })}
            placeholder={selected?.defaultModel || 'model id'}
            autoComplete="off"
          />
        </label>
        <label>
          <span>Base URL</span>
          <input
            value={value.base_url}
            onChange={(event) => {
              const nextBaseUrl = event.target.value
              const identityChanged = (
                nextBaseUrl.replace(/\/+$/, '') !==
                String(value.base_url || '').replace(/\/+$/, '')
              )
              update({
                base_url: nextBaseUrl,
                api_key: identityChanged ? '' : value.api_key,
                credential_required:
                  identityChanged &&
                  Boolean(
                    value.api_key ||
                    value.credential_present ||
                    value.credential_required,
                  ),
              })
            }}
            placeholder={selected?.defaultBaseUrl || 'https://…/v1'}
            autoComplete="off"
          />
        </label>
        <label>
          <span>API key</span>
          <input
            type="password"
            value={value.api_key}
            onChange={(event) => update({
              api_key: event.target.value,
              credential_required:
                value.credential_required && !event.target.value.trim(),
            })}
            placeholder={
              runtime?.credential_present
                ? `已配置 · ${runtime.key_fingerprint || '凭据不回显'}`
                : '输入新凭据'
            }
            autoComplete="new-password"
          />
          <small>已保存的完整 key 永不回填到输入框。</small>
          {value.credential_required && (
            <small role="alert">
              Provider 或 Base URL 已改变，请重新输入该服务的 API key。
            </small>
          )}
        </label>
        <label>
          <span>thinking mode</span>
          <select
            value={value.thinking_mode}
            onChange={(event) => update({ thinking_mode: event.target.value })}
          >
            <option value="disabled">disabled</option>
            <option value="enabled">enabled</option>
            <option value="auto">auto</option>
          </select>
        </label>
        <label>
          <span>timeout · 秒</span>
          <input
            type="number"
            min="10"
            max="3600"
            value={value.timeout}
            onChange={(event) => update({ timeout: Number(event.target.value) })}
          />
        </label>
        <label>
          <span>SDK retries</span>
          <input
            type="number"
            min="0"
            max="8"
            value={value.max_retries}
            onChange={(event) =>
              update({ max_retries: Number(event.target.value) })
            }
          />
        </label>
      </div>

      <div className="dc-provider-foot">
        <div className="dc-provider-persistence" role="radiogroup" aria-label="凭据保存范围">
          <button
            type="button"
            role="radio"
            aria-checked={persistence === 'session'}
            className={persistence === 'session' ? 'is-active' : ''}
            onClick={() => onPersistenceChange?.('session')}
          >
            仅本次会话
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={persistence === 'device'}
            className={persistence === 'device' ? 'is-active' : ''}
            onClick={() => onPersistenceChange?.('device')}
          >
            记住在此设备
          </button>
        </div>
        <button
          type="button"
          className="dc-btn"
          onClick={onProbe}
          disabled={
            probeBusy ||
            !value.provider ||
            catalogLoading ||
            Boolean(value.credential_required)
          }
        >
          {probeBusy ? '正在测试…' : '测试连接'}
        </button>
      </div>

      {probe && <ProbeResult result={probe} />}
    </section>
  )
}

function RuntimeBadge({ runtime, probe }) {
  const success = probe?.success
  const label = success
    ? 'PROBE OK'
    : runtime?.credential_present
      ? 'CREDENTIAL READY'
      : 'NOT TESTED'
  return (
    <span
      className={`dc-provider-runtime ${
        success ? 'is-ok' : runtime?.credential_present ? 'is-ready' : ''
      }`}
    >
      {label}
    </span>
  )
}

function ProbeResult({ result }) {
  if (result.success) {
    return (
      <div className="dc-provider-probe is-ok" role="status">
        <strong>连接成功</strong>
        <span>{result.provider} · {result.model}</span>
        <span>{Number(result.latency_ms || 0).toLocaleString()} ms</span>
        <span>
          {(result.prompt_tokens || 0) + (result.completion_tokens || 0)} tokens
        </span>
        <span>thinking {result.thinking_mode || '—'}</span>
      </div>
    )
  }
  return (
    <div className="dc-provider-probe is-error" role="alert">
      <strong>模型服务测试失败</strong>
      <span>{result.code || 'PROVIDER_UNAVAILABLE'}</span>
      <span>{result.message || '请检查凭据后重试。'}</span>
    </div>
  )
}
