import React, { useEffect, useState } from 'react'
import {
  fetchLLMConfig,
  getUserLLMConfig,
  setUserLLMConfig,
  updateLLMConfig,
} from '../../services/api'
import { useTheme } from '../ThemeContext'
import { showToast } from '../../utils/toast'

// v2.47 — § 配置 view (1:1 移植 Novel Auto Dashboard.dc.html 的 6 段配置).
//   1. LLM 提供方 (chips + model / base / key / temp / max / timeout)
//   2. 调度参数 (tick 间隔 / max_tokens 预算 / 最少伏笔 / auto_degrade / KG 同步)
//   3. 外观 (light/dark + accent picker)
//   4. 部署 / 关于

// 23 provider catalog 与后端 core/config.py / LoginGate 同步.
const PROVIDERS = [
  { key: 'deepseek',    label: 'DeepSeek',    base: 'https://api.deepseek.com/v1', model: 'deepseek-chat',                    grp: '国内' },
  { key: 'mimo',        label: 'MiMo · 小米',  base: 'https://token-plan-cn.xiaomimimo.com/v1', model: 'mimo-chat',           grp: '国内' },
  { key: 'qwen',        label: '通义千问',     base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus', grp: '国内' },
  { key: 'zhipu',       label: '智谱 GLM',     base: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-plus',             grp: '国内' },
  { key: 'moonshot',    label: 'Moonshot Kimi', base: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-32k',                 grp: '国内' },
  { key: 'baidu',       label: '百度千帆',     base: 'https://qianfan.baidubce.com/v2', model: 'ernie-4.0-turbo-128k',        grp: '国内' },
  { key: 'ark',         label: '火山方舟',     base: 'https://ark.cn-beijing.volces.com/api/v3', model: 'doubao-pro-32k',     grp: '国内' },
  { key: 'siliconflow', label: 'SiliconFlow',  base: 'https://api.siliconflow.cn/v1', model: 'Qwen/Qwen2.5-72B-Instruct',     grp: '国内' },
  { key: 'stepfun',     label: '阶跃星辰',     base: 'https://api.stepfun.com/v1', model: 'step-1-256k',                      grp: '国内' },
  { key: 'minimax',     label: 'MiniMax',      base: 'https://api.minimax.chat/v1', model: 'abab6.5-chat',                    grp: '国内' },
  { key: 'baichuan',    label: '百川',         base: 'https://api.baichuan-ai.com/v1', model: 'Baichuan4-Turbo',              grp: '国内' },
  { key: 'lingyiwanwu', label: '零一万物',     base: 'https://api.lingyiwanwu.com/v1', model: 'yi-large',                     grp: '国内' },
  { key: 'ai360',       label: '360 智脑',     base: 'https://api.360.cn/v1', model: '360gpt-pro',                            grp: '国内' },
  { key: 'openai',      label: 'OpenAI',       base: 'https://api.openai.com/v1', model: 'gpt-4o-mini',                       grp: '海外' },
  { key: 'xai',         label: 'xAI Grok',     base: 'https://api.x.ai/v1', model: 'grok-2-latest',                          grp: '海外' },
  { key: 'groq',        label: 'Groq',         base: 'https://api.groq.com/openai/v1', model: 'llama-3.3-70b-versatile',     grp: '海外' },
  { key: 'openrouter',  label: 'OpenRouter',   base: 'https://openrouter.ai/api/v1', model: 'openai/gpt-4o-mini',            grp: '海外' },
  { key: 'together',    label: 'Together AI',  base: 'https://api.together.xyz/v1', model: 'meta-llama/Llama-3.3-70B-Instruct-Turbo', grp: '海外' },
  { key: 'fireworks',   label: 'Fireworks AI', base: 'https://api.fireworks.ai/inference/v1', model: 'accounts/fireworks/models/llama-v3p3-70b-instruct', grp: '海外' },
  { key: 'mistral',     label: 'Mistral',      base: 'https://api.mistral.ai/v1', model: 'mistral-large-latest',              grp: '海外' },
  { key: 'novita',      label: 'Novita AI',    base: 'https://api.novita.ai/v3/openai', model: 'meta-llama/llama-3.3-70b-instruct', grp: '海外' },
  { key: 'gemini_oai',  label: 'Gemini',       base: 'https://generativelanguage.googleapis.com/v1beta/openai', model: 'gemini-1.5-flash', grp: '海外' },
  { key: 'custom',      label: '自定义',       base: '', model: '',                                                            grp: '自定义' },
]

export default function ConfigView() {
  const { theme, setTheme, accent, setAccent, accentSwatches } = useTheme()
  const [accentOpen, setAccentOpen] = useState(false)

  const [provider, setProvider] = useState('deepseek')
  const [model, setModel] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [temperature, setTemperature] = useState(0.7)
  const [maxTokens, setMaxTokens] = useState(4096)
  const [timeout, setTimeout_] = useState(600)
  const [dirty, setDirty] = useState(false)
  const [serverCfg, setServerCfg] = useState(null)

  // —— 加载本地 + 服务端 LLM 配置 ——
  useEffect(() => {
    const local = getUserLLMConfig()
    if (local.api_key) setApiKey(local.api_key)
    if (local.base_url) setBaseUrl(local.base_url)
    if (local.model) setModel(local.model)
    if (local.provider) setProvider(local.provider)
    // 服务端 fallback 配置
    let cancelled = false
    async function load() {
      try {
        const r = await fetchLLMConfig()
        if (cancelled) return
        setServerCfg(r)
        // 仅当本地没填时, 用 server 填上.
        if (!local.api_key && r?.api_key) setApiKey(r.api_key)
        if (!local.base_url && r?.base_url) setBaseUrl(r.base_url)
        if (!local.model && r?.model) setModel(r.model)
      } catch {
        /* */
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  function pickProvider(p) {
    setProvider(p.key)
    if (!model || PROVIDERS.find((x) => x.model === model)) setModel(p.model)
    setBaseUrl(p.base)
    setDirty(true)
  }

  async function save() {
    try {
      setUserLLMConfig({ api_key: apiKey, base_url: baseUrl, model, provider })
      // 同步给后端 fallback config (用户没填本地凭据时 LLM 调用走这里)
      await updateLLMConfig({ api_key: apiKey, base_url: baseUrl, model, provider })
      setDirty(false)
      showToast('已写入 .env / localStorage', 'success')
    } catch (err) {
      showToast(err.message || '保存失败', 'error')
    }
  }

  return (
    <div className="dc-view-switch dc-cf-root">
      <div className="dc-sec-head">
        <span className="dc-sec-num">§ 06</span>
        <h2 className="dc-sec-title">配置</h2>
        <span className="dc-sec-sub">runtime · LLM · 外观 · 部署</span>
        <button
          type="button"
          className="dc-sec-meta"
          onClick={save}
          style={{
            marginLeft: 'auto',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: dirty ? 'var(--accent)' : 'var(--text3)',
          }}
        >
          {dirty ? '写入 .env →' : '已同步'}
        </button>
      </div>

      <div className="dc-cf-grid">
        {/* —— LLM 提供方 —— */}
        <div className="dc-cf-col">
          <div className="dc-cf-col-head">
            <span className="dc-cf-col-kicker">LLM 提供方</span>
            <span className="dc-cf-col-aux">23 OpenAI 兼容 · catalog v2.45</span>
          </div>
          <div className="dc-cf-card-flat">
            <div className="dc-cf-prov-scroll">
              {PROVIDERS.map((p) => (
                <span
                  key={p.key}
                  className={`dc-cf-prov-chip ${provider === p.key ? 'is-active' : ''}`}
                  onClick={() => pickProvider(p)}
                >
                  {p.label}
                </span>
              ))}
            </div>
            <CfgRow
              label="model"
              right={
                <input
                  className="dc-input-inline"
                  value={model}
                  onChange={(e) => {
                    setModel(e.target.value)
                    setDirty(true)
                  }}
                  placeholder="model id"
                />
              }
            />
            <CfgRow
              label="base_url"
              right={
                <input
                  className="dc-input-inline"
                  value={baseUrl}
                  onChange={(e) => {
                    setBaseUrl(e.target.value)
                    setDirty(true)
                  }}
                  placeholder="https://…/v1"
                  title={baseUrl}
                  style={{ width: 340, maxWidth: '64%', textAlign: 'left' }}
                />
              }
            />
            <CfgRow
              label="API key"
              right={
                <input
                  className="dc-input-inline"
                  type="password"
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value)
                    setDirty(true)
                  }}
                  placeholder="sk-…"
                />
              }
            />
            <CfgRow
              label="temperature"
              right={
                <input
                  className="dc-input-inline"
                  type="number"
                  step="0.05"
                  min="0"
                  max="2"
                  value={temperature}
                  onChange={(e) => {
                    setTemperature(parseFloat(e.target.value))
                    setDirty(true)
                  }}
                />
              }
            />
            <CfgRow
              label="max_tokens"
              right={
                <input
                  className="dc-input-inline"
                  type="number"
                  step="256"
                  min="256"
                  value={maxTokens}
                  onChange={(e) => {
                    setMaxTokens(parseInt(e.target.value, 10))
                    setDirty(true)
                  }}
                />
              }
            />
            <CfgRow
              label="timeout · s"
              right={
                <input
                  className="dc-input-inline"
                  type="number"
                  step="10"
                  min="10"
                  value={timeout}
                  onChange={(e) => {
                    setTimeout_(parseInt(e.target.value, 10))
                    setDirty(true)
                  }}
                />
              }
            />
          </div>
        </div>

        {/* —— 调度与生成 —— */}
        <div className="dc-cf-col">
          <span className="dc-cf-col-kicker">调度与生成</span>
          <div className="dc-cf-card">
            <CfgRow
              label="tick 间隔 · s"
              sub="自动推进节流"
              right={
                <input
                  className="dc-input-inline"
                  type="number"
                  step="0.1"
                  min="0.5"
                  defaultValue={4.2}
                  style={{ width: 96 }}
                />
              }
            />
            <CfgRow
              label="max_tokens 预算"
              sub="每 tick 上限"
              right={
                <input
                  className="dc-input-inline"
                  type="number"
                  step="500"
                  min="500"
                  defaultValue={16000}
                  style={{ width: 110 }}
                />
              }
            />
            <CfgRow
              label="最少开放伏笔"
              sub="Showrunner 维护"
              right={
                <input
                  className="dc-input-inline"
                  type="number"
                  step="1"
                  min="0"
                  defaultValue={3}
                  style={{ width: 72 }}
                />
              }
            />
            <CfgRow
              label="auto_degrade"
              sub="超预算降级 critic"
              right={<TogglePill defaultOn />}
            />
            <CfgRow
              label="KG 同步"
              sub="tick 末尾纯 Python"
              right={<TogglePill defaultOn />}
            />
          </div>
        </div>

        {/* —— 外观 —— */}
        <div className="dc-cf-col">
          <span className="dc-cf-col-kicker">外观</span>
          <div className="dc-cf-card-flat dc-cf-appear">
            <div className="dc-cf-row" style={{ borderTop: 'none' }}>
              <div className="dc-cf-row-body">
                <span className="dc-cf-row-name">主题</span>
                <span className="dc-cf-row-sub">日间 / 夜间 · 与登录同步</span>
              </div>
              <div className="dc-cf-theme-toggle">
                <button
                  type="button"
                  className={theme === 'light' ? 'is-active' : ''}
                  onClick={() => setTheme('light')}
                >
                  日间
                </button>
                <button
                  type="button"
                  className={theme === 'dark' ? 'is-active' : ''}
                  onClick={() => setTheme('dark')}
                >
                  夜间
                </button>
              </div>
            </div>
            <div className="dc-cf-row">
              <div className="dc-cf-row-body">
                <span className="dc-cf-row-name">强调色</span>
                <span className="dc-cf-row-sub">accent · 点击自定义</span>
              </div>
              <div style={{ position: 'relative' }}>
                <div
                  className="dc-cf-accent-swatch-row"
                  onClick={() => setAccentOpen((v) => !v)}
                >
                  <span className="dc-cf-accent-swatch" />
                  <span className="dc-cf-accent-hex">{accent}</span>
                  <svg width="9" height="9" viewBox="0 0 10 10" fill="none">
                    <path
                      d="M2 4 L5 7 L8 4"
                      stroke="var(--text3)"
                      strokeWidth="1.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
                {accentOpen && (
                  <div className="dc-cf-accent-pop">
                    <span className="dc-cf-accent-pop-lbl">调色盘 · ACCENT</span>
                    <div className="dc-cf-accent-swatches">
                      {accentSwatches.map((sw) => (
                        <span
                          key={sw}
                          className={`dc-cf-accent-sw ${accent === sw ? 'is-active' : ''}`}
                          style={{ background: sw }}
                          onClick={() => {
                            setAccent(sw)
                            setAccentOpen(false)
                          }}
                        />
                      ))}
                    </div>
                    <label className="dc-cf-color-row">
                      <span>自定义颜色</span>
                      <input
                        className="dc-cf-color-input"
                        type="color"
                        value={accent}
                        onInput={(e) => setAccent(e.target.value)}
                      />
                    </label>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* —— 部署 / 关于 —— */}
        <div className="dc-cf-col">
          <span className="dc-cf-col-kicker">部署 / 关于</span>
          <div className="dc-cf-card">
            <AboutRow name="后端" val="FastAPI · :8762" />
            <AboutRow name="前端" val="Vite 6 · SPA" />
            <AboutRow
              name="LLM provider"
              val={`${serverCfg?.provider || provider} · ${model || '—'}`}
            />
            <AboutRow name="版本" val="v2.47 · 2026-06-20" />
          </div>
        </div>
      </div>
    </div>
  )
}

function CfgRow({ label, sub, right }) {
  return (
    <div className="dc-cf-row">
      <div className="dc-cf-row-body">
        <span className="dc-cf-row-name">{label}</span>
        {sub && <span className="dc-cf-row-sub">{sub}</span>}
      </div>
      {right}
    </div>
  )
}

function AboutRow({ name, val }) {
  return (
    <div className="dc-cf-about-row">
      <span className="dc-cf-about-name">{name}</span>
      <span className="dc-cf-about-val">{val}</span>
    </div>
  )
}

function TogglePill({ defaultOn }) {
  const [on, setOn] = useState(defaultOn)
  return (
    <span className={`dc-tk-toggle ${on ? 'is-on' : ''}`} onClick={() => setOn((v) => !v)}>
      <span className="dc-tk-toggle-knob" />
    </span>
  )
}
