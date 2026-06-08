import React, { useEffect, useState } from 'react'
import {
  getUserLLMConfig,
  getUserImageConfig,
  setUserLLMConfig,
  setUserImageConfig,
} from '../services/api'
import { showToast } from '../utils/toast'

// v2.27 — 系统设置全部走浏览器 localStorage. 服务端不再有兜底 API key.
//
// 两段:
//   1. 文本 LLM (随机种子/标题、未来 agent 调用)
//   2. 图片生成 (多模态第一阶段)
//
// 都用 schema 驱动的 PROVIDERS 表渲染 — 加一家新供应商只改这张表.

const TEXT_LLM_PROVIDERS = {
  deepseek: {
    label: 'DeepSeek',
    fields: [
      { name: 'api_key', label: 'API Key', type: 'password', placeholder: 'sk-...' },
      { name: 'base_url', label: 'Base URL', type: 'text', placeholder: 'https://api.deepseek.com' },
      { name: 'model', label: 'Model', type: 'text', placeholder: 'deepseek-chat' },
    ],
  },
  mimo: {
    label: 'MiMo (小米)',
    fields: [
      { name: 'api_key', label: 'API Key', type: 'password', placeholder: '' },
      { name: 'base_url', label: 'Base URL', type: 'text', placeholder: 'https://token-plan-cn.xiaomimimo.com/v1' },
      { name: 'model', label: 'Model', type: 'text', placeholder: 'mimo-v2.5-pro' },
    ],
  },
  custom: {
    label: '自定义 OpenAI 兼容',
    fields: [
      { name: 'api_key', label: 'API Key', type: 'password', placeholder: '' },
      { name: 'base_url', label: 'Base URL', type: 'text', placeholder: 'https://...' },
      { name: 'model', label: 'Model', type: 'text', placeholder: 'model-id' },
    ],
  },
}

const IMAGE_PROVIDERS = {
  xfyun: {
    label: '科大讯飞 (MaaS 图片生成)',
    docHref: 'https://www.xfyun.cn/doc/spark/%E5%9B%BE%E7%89%87%E7%94%9F%E6%88%90.html',
    fields: [
      { name: 'app_id', label: 'AppID', type: 'text', placeholder: '12345678' },
      { name: 'api_secret', label: 'APISecret', type: 'password', placeholder: '' },
      { name: 'api_key', label: 'APIKey', type: 'password', placeholder: '' },
      {
        name: 'model',
        label: 'ModelID (domain)',
        type: 'text',
        placeholder: '例如: xopqwentti20b / general',
      },
      {
        name: 'endpoint',
        label: 'API 端点 (可选)',
        type: 'text',
        placeholder:
          'https://maas-api.cn-huabei-1.xf-yun.com/v2.1/tti (默认) / xingchen-api... (Kolors)',
      },
    ],
  },
  openai: {
    label: 'OpenAI DALL·E',
    fields: [
      { name: 'api_key', label: 'API Key', type: 'password', placeholder: 'sk-...' },
      { name: 'base_url', label: 'Base URL', type: 'text', placeholder: 'https://api.openai.com/v1' },
      { name: 'model', label: 'Model', type: 'text', placeholder: 'dall-e-3' },
    ],
  },
  stability: {
    label: 'Stability AI',
    fields: [
      { name: 'api_key', label: 'API Key', type: 'password', placeholder: 'sk-...' },
    ],
  },
  custom: {
    label: '自定义 (OpenAI Images 兼容)',
    fields: [
      { name: 'api_key', label: 'API Key', type: 'password', placeholder: '' },
      { name: 'base_url', label: 'Base URL', type: 'text', placeholder: '' },
      { name: 'model', label: 'Model', type: 'text', placeholder: '' },
    ],
  },
}

export default function ConfigView() {
  return (
    <div style={{ maxWidth: 720, display: 'flex', flexDirection: 'column', gap: 24 }}>
      <h2 style={{ margin: 0, fontSize: 18, display: 'flex', alignItems: 'center', gap: 8 }}>
        <i className="fas fa-sliders-h" style={{ color: 'var(--accent-purple)' }}></i>
        系统设置
        <span
          style={{
            fontSize: 11,
            color: 'var(--text-muted)',
            fontWeight: 400,
            marginLeft: 4,
          }}
        >
          仅保存在您的浏览器本地
        </span>
      </h2>
      <TextLLMSection />
      <ImageProviderSection />
    </div>
  )
}

// ---------------------------------------------------------------------------
// 文本 LLM
// ---------------------------------------------------------------------------

function TextLLMSection() {
  const [provider, setProvider] = useState('deepseek')
  const [values, setValues] = useState({})

  useEffect(() => {
    const stored = getUserLLMConfig()
    const detected = inferProvider(stored.base_url)
    setProvider(detected)
    setValues({
      api_key: stored.api_key || '',
      base_url: stored.base_url || '',
      model: stored.model || '',
    })
  }, [])

  const def = TEXT_LLM_PROVIDERS[provider] || TEXT_LLM_PROVIDERS.deepseek

  const onProviderChange = (next) => {
    setProvider(next)
    const nextDef = TEXT_LLM_PROVIDERS[next]
    // 切 provider 时 base_url / model 替换为默认占位, api_key 清空
    const nextValues = { api_key: '', base_url: '', model: '' }
    nextDef.fields.forEach((f) => {
      if (f.name === 'base_url' && f.placeholder) nextValues.base_url = f.placeholder
      if (f.name === 'model' && f.placeholder) nextValues.model = f.placeholder
    })
    setValues(nextValues)
  }

  const handleSave = () => {
    setUserLLMConfig({
      api_key: (values.api_key || '').trim(),
      base_url: (values.base_url || '').trim(),
      model: (values.model || '').trim(),
    })
    showToast('已保存', 'success')
  }

  return (
    <Section
      icon="fa-comment-dots"
      title="文本 LLM"
      hint="随机种子 / 标题 / 后续 Agent 调用. 未填则相关功能不可用."
    >
      <Field label="提供商">
        <select
          className="input-field"
          value={provider}
          onChange={(e) => onProviderChange(e.target.value)}
        >
          {Object.entries(TEXT_LLM_PROVIDERS).map(([k, p]) => (
            <option key={k} value={k}>
              {p.label}
            </option>
          ))}
        </select>
      </Field>
      {def.fields.map((f) => (
        <Field key={f.name} label={f.label}>
          <input
            type={f.type}
            className="input-field"
            value={values[f.name] || ''}
            placeholder={f.placeholder}
            onChange={(e) =>
              setValues((prev) => ({ ...prev, [f.name]: e.target.value }))
            }
          />
        </Field>
      ))}
      <button className="btn btn-primary" onClick={handleSave}>
        保存
      </button>
    </Section>
  )
}

function inferProvider(baseUrl) {
  if (!baseUrl) return 'deepseek'
  if (baseUrl.includes('deepseek')) return 'deepseek'
  if (baseUrl.includes('xiaomimimo') || baseUrl.includes('mimo')) return 'mimo'
  return 'custom'
}

// ---------------------------------------------------------------------------
// 图片生成
// ---------------------------------------------------------------------------

function ImageProviderSection() {
  const [active, setActive] = useState('xfyun')
  const [providers, setProviders] = useState({})

  useEffect(() => {
    const stored = getUserImageConfig()
    setActive(stored.active || 'xfyun')
    setProviders(stored.providers || {})
  }, [])

  const def = IMAGE_PROVIDERS[active] || IMAGE_PROVIDERS.xfyun
  const current = providers[active] || {}

  const handleField = (name, value) => {
    setProviders((prev) => ({
      ...prev,
      [active]: { ...(prev[active] || {}), [name]: value },
    }))
  }

  const handleSave = () => {
    // 每个 provider 各存各的; active 决定调用时用哪家
    const cleaned = {}
    for (const [k, v] of Object.entries(providers)) {
      const trimmed = {}
      for (const [fk, fv] of Object.entries(v || {})) {
        trimmed[fk] = typeof fv === 'string' ? fv.trim() : fv
      }
      cleaned[k] = trimmed
    }
    setUserImageConfig({ active, providers: cleaned })
    showToast('已保存', 'success')
  }

  return (
    <Section
      icon="fa-image"
      title="图片生成"
      hint="未来章节插图 / 封面生成会用这里的凭据."
    >
      <Field label="提供商">
        <select
          className="input-field"
          value={active}
          onChange={(e) => setActive(e.target.value)}
        >
          {Object.entries(IMAGE_PROVIDERS).map(([k, p]) => (
            <option key={k} value={k}>
              {p.label}
            </option>
          ))}
        </select>
        {def.docHref && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
            <a
              href={def.docHref}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: 'var(--accent-cyan)' }}
            >
              查看 {def.label} 官方文档 →
            </a>
          </div>
        )}
      </Field>
      {def.fields.map((f) => (
        <Field key={f.name} label={f.label}>
          <input
            type={f.type}
            className="input-field"
            value={current[f.name] || ''}
            placeholder={f.placeholder}
            onChange={(e) => handleField(f.name, e.target.value)}
          />
        </Field>
      ))}
      <button className="btn btn-primary" onClick={handleSave}>
        保存
      </button>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// shared
// ---------------------------------------------------------------------------

function Section({ icon, title, hint, children }) {
  return (
    <div
      style={{
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid var(--border-subtle, rgba(255,255,255,0.06))',
        borderRadius: 10,
        padding: 20,
      }}
    >
      <div
        style={{
          fontSize: 14,
          fontWeight: 600,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 4,
        }}
      >
        <i className={`fas ${icon}`} style={{ color: 'var(--accent-purple)' }}></i>
        {title}
      </div>
      {hint && (
        <div
          style={{
            fontSize: 11,
            color: 'var(--text-muted)',
            marginBottom: 16,
            lineHeight: 1.6,
          }}
        >
          {hint}
        </div>
      )}
      {children}
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <label
        style={{
          display: 'block',
          fontSize: 11,
          color: 'var(--text-muted)',
          marginBottom: 4,
        }}
      >
        {label}
      </label>
      {children}
    </div>
  )
}
