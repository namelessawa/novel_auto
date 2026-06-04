import React, { useEffect, useState } from 'react'
import { fetchLLMConfig, updateLLMConfig } from '../services/api'
import { showToast } from '../utils/toast'

const PROVIDERS = {
  deepseek: {
    label: 'DeepSeek (官方)',
    defaultBaseUrl: 'https://api.deepseek.com',
    defaultModel: 'deepseek-chat',
    keyHint: '以 sk- 开头,长度 ≥ 20',
    keyPlaceholder: 'sk-xxxxxxxxxxxxxxxx',
  },
  mimo: {
    label: 'MiMo (小米)',
    defaultBaseUrl: 'https://token-plan-cn.xiaomimimo.com/v1',
    defaultModel: 'mimo-chat',
    keyHint: '在小米 MiMo 平台申请',
    keyPlaceholder: 'mimo-api-key',
  },
  custom: {
    label: '自定义 (OpenAI 兼容)',
    defaultBaseUrl: '',
    defaultModel: '',
    keyHint: '任意 OpenAI Chat Completions 兼容端点',
    keyPlaceholder: 'api-key',
  },
}

export default function ConfigView() {
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [provider, setProvider] = useState('deepseek')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [maskedHint, setMaskedHint] = useState('')
  const [source, setSource] = useState('')

  useEffect(() => {
    loadConfig()
  }, [])

  const loadConfig = async () => {
    try {
      const cfg = await fetchLLMConfig()
      setProvider(cfg.provider || 'deepseek')
      setBaseUrl(cfg.base_url || '')
      setModel(cfg.model || '')
      setApiKey('')
      setMaskedHint(cfg.api_key_masked || '')
      setSource(cfg.source || '')
    } catch (err) {
      showToast('加载 LLM 配置失败:' + err.message, 'error')
    } finally {
      setLoaded(true)
    }
  }

  const onProviderChange = (next) => {
    setProvider(next)
    const preset = PROVIDERS[next]
    if (preset) {
      // 切换 provider 一律重置 baseUrl / model 到该 provider 的默认值
      // 用户手填的值不会被复用到另一家 provider — 避免把 deepseek 的 URL
      // 留给 mimo 这种事。
      setBaseUrl(preset.defaultBaseUrl)
      setModel(preset.defaultModel)
      setApiKey('')  // 不同 provider 用不同 key
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const body = {
        // v2.20 — provider 一起发, 后端会切 os.environ['LLM_PROVIDER'] 让
        // llm_client.reload() 真正路由到新 provider; 之前下拉只在前端
        // useState, 保存时被丢弃, 实际 active provider 仍由 .env 决定。
        provider,
        base_url: baseUrl,
        model: model,
      }
      if (apiKey) body.api_key = apiKey
      const result = await updateLLMConfig(body)
      setProvider(result.provider || provider)
      setBaseUrl(result.base_url || baseUrl)
      setModel(result.model || model)
      setMaskedHint(result.api_key_masked || '')
      setSource(result.source || '')
      setApiKey('')
      showToast('LLM 配置已保存', 'success')
    } catch (err) {
      showToast('保存失败:' + err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = () => loadConfig()

  if (!loaded) {
    return (
      <div className="card">
        <div className="generating-indicator">
          <span className="loading-spinner"></span>
          <span>读取配置中…</span>
        </div>
      </div>
    )
  }

  const preset = PROVIDERS[provider] || PROVIDERS.custom
  const sourceLabel =
    source === 'main_env'
      ? '.env (LLM_PROVIDER 优先)'
      : source === 'config.json'
        ? 'config.json (兜底)'
        : source || '未知'

  return (
    <div style={{ maxWidth: 720 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <h2
          style={{
            margin: 0,
            fontSize: 18,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <i
            className="fas fa-sliders-h"
            style={{ color: 'var(--accent-purple)' }}
          ></i>
          系统设置
        </h2>
        <span className="badge badge-purple" style={{ marginLeft: 8 }}>
          来源: {sourceLabel}
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button className="btn btn-secondary btn-sm" onClick={handleReset}>
            <i className="fas fa-sync"></i> 刷新
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleSave}
            disabled={saving}
          >
            <i className="fas fa-save"></i> {saving ? '保存中…' : '保存'}
          </button>
        </div>
      </div>

      {/* Provider */}
      <div className="config-section">
        <div
          className="config-section-title"
          style={{ color: 'var(--accent-blue)' }}
        >
          <i className="fas fa-cloud"></i> LLM 提供商
        </div>
        <div className="card">
          <div style={{ marginBottom: 14 }}>
            <label className="input-label">当前提供商</label>
            <select
              className="input-field"
              value={provider}
              onChange={(e) => onProviderChange(e.target.value)}
            >
              {Object.entries(PROVIDERS).map(([key, p]) => (
                <option key={key} value={key}>
                  {p.label}
                </option>
              ))}
            </select>
            <p className="input-hint">
              <i className="fas fa-info-circle" style={{ marginRight: 4 }}></i>
              切换 provider 立即生效 (作用于本进程 <code style={{ color: 'var(--accent-purple)', margin: '0 4px' }}>os.environ['LLM_PROVIDER']</code>);
              重启后回退到 <code style={{ color: 'var(--accent-purple)', margin: '0 4px' }}>.env</code> 静态值。下方 api_key / base_url / model 写入
              <code style={{ color: 'var(--accent-purple)', margin: '0 4px' }}>config.json</code> 的 llm 段作为兜底。
            </p>
          </div>

          <div style={{ marginBottom: 12 }}>
            <label className="input-label">
              {preset.label} API Key{' '}
              <span style={{ color: 'var(--accent-rose)' }}>*</span>
            </label>
            <input
              type="password"
              className="input-field"
              value={apiKey}
              placeholder={
                maskedHint ? `当前: ${maskedHint} (留空保留)` : preset.keyPlaceholder
              }
              onChange={(e) => setApiKey(e.target.value)}
            />
            <p className="input-hint">
              <i className="fas fa-lock" style={{ marginRight: 4 }}></i>
              {preset.keyHint}
            </p>
          </div>

          <div className="grid-2">
            <div>
              <label className="input-label">Base URL</label>
              <input
                type="text"
                className="input-field"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={preset.defaultBaseUrl || 'https://...'}
              />
            </div>
            <div>
              <label className="input-label">Model</label>
              <input
                type="text"
                className="input-field"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={preset.defaultModel || 'model-id'}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="config-section">
        <div
          className="config-section-title"
          style={{ color: 'var(--accent-amber)' }}
        >
          <i className="fas fa-info-circle"></i> 说明
        </div>
        <div className="card" style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          <p>
            <strong>active provider</strong> 来源优先级: <code style={{ color: 'var(--accent-purple)' }}>os.environ['LLM_PROVIDER']</code> (本页面切换写入)
            → 进程启动时 <code style={{ color: 'var(--accent-purple)' }}>.env</code> 的 <code style={{ color: 'var(--accent-purple)' }}>LLM_PROVIDER</code>。
            保存后 <code style={{ color: 'var(--accent-purple)' }}>llm_client.reload()</code> 立即重建 OpenAI 客户端, 无需重启进程。
          </p>
          <p style={{ marginTop: 8 }}>
            <strong>api_key / base_url / model</strong> 写入 <code style={{ color: 'var(--accent-purple)' }}>config.json</code> 的 llm 段, 作为 .env 不可用时的兜底。
            如要让切换在重启后仍保留, 请同时编辑 <code style={{ color: 'var(--accent-purple)' }}>.env</code> 的{' '}
            <code style={{ color: 'var(--accent-purple)' }}>LLM_PROVIDER</code>。
          </p>
        </div>
      </div>
    </div>
  )
}
