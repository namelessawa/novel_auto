// In production (Vercel), VITE_API_BASE points to the backend server.
// In local dev, empty string lets the vite proxy handle /api requests.
const BASE = import.meta.env.VITE_API_BASE || ''

// ---------------------------------------------------------------------------
// v2.26 — Auth interceptor
// ---------------------------------------------------------------------------
// - Reads JWT from localStorage on every request
// - Attaches Authorization: Bearer <token>
// - On an explicit application-auth 401: clears token + dispatches
//   "auth:expired". Upstream Provider failures must never destroy the app session.
// - Skips /api/auth/* (login/register) and /api/health (public)

const TOKEN_STORAGE_KEY = 'novel_auto_jwt'

export function getStoredToken() {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

export function setStoredToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_STORAGE_KEY, token)
    else localStorage.removeItem(TOKEN_STORAGE_KEY)
  } catch {
    /* private mode etc — silent */
  }
}

function _isPublicPath(path) {
  return (
    path.startsWith('/api/auth/register/') ||
    path.startsWith('/api/auth/login/') ||
    path === '/api/health' ||
    // /api/presets 返回主题/风格元数据, 未登录页也用得着. 与后端保持一致即可。
    path === '/api/presets'
  )
}

function _emit401() {
  try {
    window.dispatchEvent(new CustomEvent('auth:expired'))
  } catch {
    /* SSR-safe noop */
  }
}

// 修复(17) — 共享的 401 处理: 清 token + 广播 auth:expired。
// authedFetch / 流式端点 / blob 资产下载统一走这里, 不再各自手工复刻。
function _handleUnauthorized() {
  setStoredToken('')
  _emit401()
}

function _detailFromPayload(body) {
  if (!body || typeof body !== 'object') return {}
  if (body.detail && typeof body.detail === 'object') return body.detail
  return body
}

function _isApplicationAuthCode(code) {
  const normalized = String(code || '').trim().toUpperCase()
  return normalized.startsWith('AUTH_TOKEN_') || normalized === 'AUTH_REQUIRED'
}

function _isProviderErrorCode(code) {
  return String(code || '').trim().toUpperCase().startsWith('PROVIDER_')
}

function _isLegacyApplicationAuthDetail(detail) {
  if (!detail || typeof detail !== 'object') return false
  if (_isProviderErrorCode(detail.code)) return false
  const message = String(
    detail.message ||
    (typeof detail.detail === 'string' ? detail.detail : ''),
  ).trim()
  if (!message) return false
  return (
    /未登录|登录态(?:无效|已过期|已撤销)|用户不存在|密码已更新.*重新登录/.test(message) ||
    /(?:invalid|expired|revoked|missing)\s+(?:authentication\s+)?token/i.test(message) ||
    /not authenticated/i.test(message)
  )
}

async function _responseErrorDetail(response) {
  try {
    const body = await response.clone().json()
    return _detailFromPayload(body)
  } catch {
    return {}
  }
}

// A raw 401 is not enough evidence that the Novel Auto JWT is invalid. Provider
// gateways occasionally leak a 401 despite the backend's 424 mapping. Fail safe:
// preserve the app session unless the backend explicitly identifies AUTH_*.
async function _handleUnauthorizedResponse(response, path) {
  if (response.status !== 401 || _isPublicPath(path)) return false
  const detail = await _responseErrorDetail(response)
  if (_isProviderErrorCode(detail.code)) return false
  if (
    !_isApplicationAuthCode(detail.code) &&
    !_isLegacyApplicationAuthDetail(detail)
  ) return false
  _handleUnauthorized()
  return true
}

function _shouldAttachLLMConfig(path) {
  const route = String(path || '').split(/[?#]/, 1)[0]
  return (
    route.startsWith('/api/llm/') ||
    route === '/api/config/llm/probe' ||
    route === '/api/generate' ||
    route === '/api/generate/stream' ||
    route === '/api/section/generate' ||
    route === '/api/tick/run' ||
    /\/api\/novels\/[^/]+\/(?:bootstrap-world|regenerate-style-anchors|outline\/generate|production\/(?:start|resume|retry-failed)|style-profiles\/[^/]+\/preview|sections\/generate)$/.test(route)
  )
}

function _attachUserLLMConfig(headers) {
  const llm = getUserLLMConfig()
  // A partial override is unsafe: the backend intentionally rejects any
  // Provider selector without its matching one-shot credential.  When the
  // browser has no key, send no Provider headers at all and let the server
  // resolve its configured fallback runtime.
  if (!llm.api_key) return
  if (!headers.has('X-User-LLM-Key')) {
    headers.set('X-User-LLM-Key', llm.api_key)
  }
  if (llm.base_url && !headers.has('X-User-LLM-Base-Url')) {
    headers.set('X-User-LLM-Base-Url', llm.base_url)
  }
  if (llm.model && !headers.has('X-User-LLM-Model')) {
    headers.set('X-User-LLM-Model', llm.model)
  }
  if (llm.provider && !headers.has('X-User-LLM-Provider')) {
    headers.set('X-User-LLM-Provider', llm.provider)
  }
  if (llm.thinking_mode && !headers.has('X-User-LLM-Thinking-Mode')) {
    headers.set('X-User-LLM-Thinking-Mode', llm.thinking_mode)
  }
  if (llm.timeout != null && !headers.has('X-User-LLM-Timeout')) {
    headers.set('X-User-LLM-Timeout', String(llm.timeout))
  }
  if (llm.max_retries != null && !headers.has('X-User-LLM-Max-Retries')) {
    headers.set('X-User-LLM-Max-Retries', String(llm.max_retries))
  }
}

export async function authedFetch(path, init = {}) {
  const { skipUserLLMConfig = false, ...requestInit } = init
  const headers = new Headers(requestInit.headers || {})
  if (
    !headers.has('Content-Type') &&
    requestInit.body &&
    typeof requestInit.body === 'string'
  ) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getStoredToken()
  if (token && !_isPublicPath(path)) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  // Only attach credentials to requests that may actually invoke a model.
  // This keeps secrets away from unrelated chapter/stat/export traffic.
  if (
    !skipUserLLMConfig &&
    !_isPublicPath(path) &&
    _shouldAttachLLMConfig(path)
  ) {
    _attachUserLLMConfig(headers)
  }
  const res = await fetch(`${BASE}${path}`, { ...requestInit, headers })
  // sliding refresh: 后端在距过期 < 1 天时通过 X-Refreshed-Token 响应头签新 token,
  // 浏览器 JS 仅在后端 expose_headers 显式列出时能读到 (main.py CORS 已配置).
  try {
    const fresh = res.headers.get('X-Refreshed-Token')
    if (fresh) setStoredToken(fresh)
  } catch {
    /* private mode / 跨域无 expose 等情况静默忽略 */
  }
  await _handleUnauthorizedResponse(res, path)
  return res
}

async function assertOk(res) {
  if (res.ok) {
    // 204 No Content
    if (res.status === 204) return null
    return res.json()
  }
  let detail = `HTTP ${res.status}`
  let code = ''
  let details = {}
  try {
    const body = await res.json()
    if (body && typeof body.detail === 'string') {
      detail = body.detail
    } else if (body?.detail && typeof body.detail === 'object') {
      detail = body.detail.message || detail
      code = body.detail.code || ''
      details = body.detail.details || {}
    } else if (body && typeof body.message === 'string') {
      detail = body.message
      code = body.code || ''
      details = body.details || {}
    } else if (body && Array.isArray(body.detail)) {
      detail = body.detail
        .map((d) => `${(d.loc || []).join('.')}: ${d.msg}`)
        .join('; ')
    }
  } catch {
    /* keep default */
  }
  const error = new Error(detail)
  error.code = code
  error.details = details
  error.status = res.status
  throw error
}

// ---------------------------------------------------------------------------
// v2.26 — Auth endpoints
// ---------------------------------------------------------------------------

export async function authRegisterSendOTP(email) {
  const res = await authedFetch('/api/auth/register/send-otp', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
  return assertOk(res)
}

export async function authRegisterVerify(email, otp) {
  const res = await authedFetch('/api/auth/register/verify', {
    method: 'POST',
    body: JSON.stringify({ email, otp }),
  })
  return assertOk(res) // { token, user }
}

export async function authLoginSendOTP(email) {
  const res = await authedFetch('/api/auth/login/send-otp', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
  return assertOk(res)
}

export async function authLoginVerifyOTP(email, otp) {
  const res = await authedFetch('/api/auth/login/verify-otp', {
    method: 'POST',
    body: JSON.stringify({ email, otp }),
  })
  return assertOk(res) // { token, user }
}

export async function authLoginPassword(email, password) {
  const res = await authedFetch('/api/auth/login/password', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  return assertOk(res) // { token, user }
}

export async function authMe() {
  const res = await authedFetch('/api/auth/me')
  return assertOk(res) // user
}

export async function authSetPassword({ password, current_password = '' } = {}) {
  // 改密后端会自增 password_version + 返回新 JWT, 前端立即替换 localStorage 让
  // 后续 fetch 用新 token (旧 token 被服务端 pv 校验拦截).
  const res = await authedFetch('/api/auth/me/set-password', {
    method: 'POST',
    body: JSON.stringify({ password, current_password }),
  })
  const data = await assertOk(res)
  if (data && data.token) setStoredToken(data.token)
  return data // { token, user }
}

export async function authUpdateSettings({ save_my_works }) {
  const res = await authedFetch('/api/auth/me/settings', {
    method: 'PUT',
    body: JSON.stringify({ save_my_works }),
  })
  return assertOk(res) // user
}

export async function authLogout() {
  try {
    // 必须先发请求 — 后端会把当前 token 的 jti 加入撤销表; 清完本地 token 就发不出去了
    await authedFetch('/api/auth/logout', { method: 'POST' })
  } catch {
    /* server-side noop on token error; 仍要清本地 */
  }
  setStoredToken('')
  _sessionLLMConfig = null
  // 用户登出时一并清掉他们的 LLM / image api key — 防共享设备下泄露给下个登录者.
  try {
    localStorage.removeItem(USER_LLM_STORAGE_KEY)
    localStorage.removeItem(USER_IMAGE_STORAGE_KEY)
  } catch {
    /* private mode etc — silent */
  }
}

// ---------------------------------------------------------------------------
// v2.26 — LLM random (uses user's API key from localStorage via headers)
// ---------------------------------------------------------------------------

const USER_LLM_STORAGE_KEY = 'novel_auto_user_llm'
const USER_IMAGE_STORAGE_KEY = 'novel_auto_user_image'
let _sessionLLMConfig = null

function _emptyLLMConfig() {
  return {
    api_key: '',
    base_url: '',
    model: '',
    provider: '',
    thinking_mode: 'disabled',
    timeout: 600,
    max_retries: 0,
  }
}

function _readDeviceLLMConfig() {
  try {
    const raw = localStorage.getItem(USER_LLM_STORAGE_KEY)
    if (!raw) return _emptyLLMConfig()
    return { ..._emptyLLMConfig(), ...JSON.parse(raw) }
  } catch {
    return _emptyLLMConfig()
  }
}

export function getUserLLMConfig() {
  return _sessionLLMConfig
    ? { ..._emptyLLMConfig(), ..._sessionLLMConfig }
    : _readDeviceLLMConfig()
}

export function getUserLLMConfigSummary() {
  const config = getUserLLMConfig()
  return {
    provider: config.provider || '',
    base_url: config.base_url || '',
    model: config.model || '',
    thinking_mode: config.thinking_mode || 'disabled',
    timeout: Number(config.timeout || 600),
    max_retries: Number(config.max_retries || 0),
    credential_present: Boolean(config.api_key),
    source: _sessionLLMConfig ? 'session' : config.api_key ? 'device' : 'none',
  }
}

export function setUserLLMConfig(config = {}, options = {}) {
  const remember = options.remember !== false
  const previous = getUserLLMConfig()
  const provider = String(config.provider ?? previous.provider ?? '').trim()
  const baseUrl = String(config.base_url ?? previous.base_url ?? '').trim()
  const sameIdentity = (
    provider.toLowerCase() === String(previous.provider || '').trim().toLowerCase() &&
    baseUrl.replace(/\/+$/, '') ===
      String(previous.base_url || '').trim().replace(/\/+$/, '')
  )
  const suppliedKey = String(config.api_key || '')
  const payload = {
    provider,
    base_url: baseUrl,
    model: String(config.model ?? previous.model ?? '').trim(),
    api_key:
      options.clearApiKey || !sameIdentity
        ? suppliedKey
        : suppliedKey || previous.api_key || '',
    thinking_mode:
      String(config.thinking_mode ?? previous.thinking_mode ?? 'disabled'),
    timeout: Number(config.timeout ?? previous.timeout ?? 600),
    max_retries: Number(config.max_retries ?? previous.max_retries ?? 0),
  }
  if (!remember) {
    _sessionLLMConfig = payload
    return
  }
  _sessionLLMConfig = null
  try {
    localStorage.setItem(USER_LLM_STORAGE_KEY, JSON.stringify(payload))
  } catch {
    /* silent */
  }
}

export function clearUserLLMConfig() {
  _sessionLLMConfig = null
  try {
    localStorage.removeItem(USER_LLM_STORAGE_KEY)
  } catch {
    /* private mode */
  }
}

// v2.27 — 图片生成多 provider 配置 (科大讯飞 / OpenAI DALL·E / Stability / 自定义).
// schema: { active: <provider-id>, providers: { <id>: {field: value, ...}, ... } }
// 各 provider 字段不同, 完全由 ConfigView 的 IMAGE_PROVIDERS 表驱动.
export function getUserImageConfig() {
  try {
    const raw = localStorage.getItem(USER_IMAGE_STORAGE_KEY)
    if (!raw) return { active: 'xfyun', providers: {} }
    const parsed = JSON.parse(raw)
    return {
      active: parsed.active || 'xfyun',
      providers: parsed.providers || {},
    }
  } catch {
    return { active: 'xfyun', providers: {} }
  }
}

export function setUserImageConfig({ active, providers }) {
  try {
    localStorage.setItem(
      USER_IMAGE_STORAGE_KEY,
      JSON.stringify({ active, providers }),
    )
  } catch {
    /* silent */
  }
}

// 取当前 active provider 的凭据 — 后续 image 调用要用
export function getActiveImageProviderConfig() {
  const { active, providers } = getUserImageConfig()
  return { active, config: providers[active] || {} }
}

// v2.32 — 文生图. header 一次性带凭据, 后端用完即丢.
export async function generateImage({
  prompt,
  width = 768,
  height = 768,
  negative_prompt = '',
}) {
  const { active, config } = getActiveImageProviderConfig()
  const headers = { 'X-Image-Provider': active }
  if (config.app_id) headers['X-Image-App-Id'] = config.app_id
  if (config.api_key) headers['X-Image-Api-Key'] = config.api_key
  if (config.api_secret) headers['X-Image-Api-Secret'] = config.api_secret
  if (config.model) headers['X-Image-Model'] = config.model // 讯飞 domain
  if (config.endpoint) headers['X-Image-Endpoint'] = config.endpoint
  const res = await authedFetch('/api/image/generate', {
    method: 'POST',
    headers,
    body: JSON.stringify({ prompt, width, height, negative_prompt }),
  })
  return assertOk(res) // { provider, image_base64, mime_type }
}

// ---------------------------------------------------------------------------
// v2.33 — 多模态: 分段 + 图 + TTS + 视频
// ---------------------------------------------------------------------------

function _imageCredsHeaders() {
  const { active, config } = getActiveImageProviderConfig()
  const h = { 'X-Image-Provider': active }
  if (config.app_id) h['X-Image-App-Id'] = config.app_id
  if (config.api_key) h['X-Image-Api-Key'] = config.api_key
  if (config.api_secret) h['X-Image-Api-Secret'] = config.api_secret
  if (config.model) h['X-Image-Model'] = config.model
  if (config.endpoint) h['X-Image-Endpoint'] = config.endpoint
  return h
}

export async function listTTSVoices() {
  const res = await authedFetch('/api/multimodal/voices')
  return assertOk(res) // { voices: [{id,label}], default: '...' }
}

export async function previewMultimodalSegments({ novel_id, chapter, section }) {
  const res = await authedFetch('/api/multimodal/segment-preview', {
    method: 'POST',
    body: JSON.stringify({ novel_id, chapter, section }),
  })
  return assertOk(res) // { source_chars, segments: [{index,text,char_count}] }
}

export async function generateMultimodal({
  novel_id,
  chapter,
  section,
  voice,
  image_width = 768,
  image_height = 768,
  image_prompt_suffix = '电影感画面, 写实细节, 高质量插画',
  negative_prompt = '低质量, 模糊, 水印, 字幕, 文字',
}) {
  const res = await authedFetch('/api/multimodal/generate', {
    method: 'POST',
    headers: _imageCredsHeaders(),
    body: JSON.stringify({
      novel_id,
      chapter,
      section,
      voice,
      image_width,
      image_height,
      image_prompt_suffix,
      negative_prompt,
    }),
  })
  return assertOk(res) // task snapshot
}

export async function getMultimodalManifest(novel_id, chapter, section) {
  const res = await authedFetch(
    `/api/multimodal/${encodeURIComponent(novel_id)}/${chapter}/${section}/manifest`,
  )
  return assertOk(res)
}

export async function listMultimodalSections(novel_id) {
  const res = await authedFetch(
    `/api/multimodal/${encodeURIComponent(novel_id)}/list`,
  )
  return assertOk(res) // { items: [{chapter, section, video_status, ...}] }
}

// 资产 (mp4/png/mp3) 需要 JWT, 不能直接 <video src=...>; 用 fetch 拿 blob.
// 不能复用 authedFetch — 它假设 JSON 响应, 这里要 .blob(). 手工复刻 401 处理逻辑.
export async function fetchMultimodalAssetBlobUrl(novel_id, chapter, section, filename) {
  const token = getStoredToken()
  const url = `${BASE}/api/multimodal/${encodeURIComponent(novel_id)}/${chapter}/${section}/asset/${encodeURIComponent(filename)}`
  const headers = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(url, { headers })
  if (res.status === 401) {
    const expired = await _handleUnauthorizedResponse(res, '/api/multimodal/asset')
    if (expired) throw new Error('登录态已过期, 请重新登录')
  }
  if (!res.ok) return assertOk(res)
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

// X-User-LLM-* headers 统一由 authedFetch 注入，但只发送给会实际调用模型的
// 明确 allowlist 路径，避免凭据进入状态、导出或正文读取请求。

export async function randomSeed({ existing_title = '' } = {}) {
  const res = await authedFetch('/api/llm/random-seed', {
    method: 'POST',
    body: JSON.stringify({ existing_title }),
  })
  return assertOk(res) // { text }
}

export async function randomTitle({ existing_seed = '' } = {}) {
  const res = await authedFetch('/api/llm/random-title', {
    method: 'POST',
    body: JSON.stringify({ existing_seed }),
  })
  return assertOk(res) // { text }
}

export async function randomPositioning({
  existing_title = '',
  existing_seed = '',
} = {}) {
  const res = await authedFetch('/api/llm/random-positioning', {
    method: 'POST',
    body: JSON.stringify({ existing_title, existing_seed }),
  })
  return assertOk(res) // { text }
}

export async function regenerateStyleAnchors(novelId, payload = {}) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/regenerate-style-anchors`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
  return assertOk(res) // { novel_id, style_anchors_count, message, scene_types }
}

// ---------------------------------------------------------------------------
// Legacy section pipeline (now JWT-gated by backend)
// ---------------------------------------------------------------------------

export async function fetchStats() {
  const res = await authedFetch('/api/stats')
  return assertOk(res)
}

export async function fetchSections() {
  const res = await authedFetch('/api/sections')
  return assertOk(res)
}

export async function fetchGraph() {
  const res = await authedFetch('/api/graph')
  return assertOk(res)
}

export async function fetchOutline() {
  const res = await authedFetch('/api/outline')
  return assertOk(res)
}

export async function fetchMemory() {
  const res = await authedFetch('/api/memory')
  return assertOk(res)
}

export async function fetchSnapshots() {
  const res = await authedFetch('/api/snapshots')
  return assertOk(res)
}

export async function generateSection(outline = '') {
  const res = await authedFetch('/api/generate', {
    method: 'POST',
    body: JSON.stringify({ outline }),
  })
  return assertOk(res)
}

export function generateSectionStream(outline = '', onEvent, onText, onDone, onError) {
  const controller = new AbortController()
  const reportError = (err) => {
    if (typeof onError === 'function') onError(err)
    else onDone()
  }

  const token = getStoredToken()
  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (token) headers.set('Authorization', `Bearer ${token}`)
  _attachUserLLMConfig(headers)

  fetch(`${BASE}/api/generate/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ outline }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (response.status === 401) {
        const expired = await _handleUnauthorizedResponse(response, '/api/generate/stream')
        if (expired) {
          reportError(new Error('登录态已过期, 请重新登录'))
          return
        }
      }
      if (!response.ok) {
        let detail = `HTTP ${response.status}`
        try {
          const body = await response.json()
          if (typeof body?.detail === 'string') detail = body.detail
        } catch {
          /* keep default */
        }
        reportError(new Error(detail))
        return
      }
      // 修复(sse-6) — body 在某些代理/Service Worker 介入下可能为 null
      if (!response.body) {
        reportError(new Error('Streaming not supported by this transport'))
        return
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        // 修复(sse-1) — 用 \r?\n 正则切, nginx/cloudflare 把流换行规范化为 \r\n 时不再丢事件
        const lines = buffer.split(/\r?\n/)
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
            continue
          }
          if (line.startsWith('data: ')) {
            const data = line.slice(6)

            if (currentEvent === 'done') {
              onDone()
              return
            }

            if (currentEvent === 'pipeline') {
              try {
                onEvent(JSON.parse(data))
              } catch (err) {
                // 修复(15) — 不再静默吞: 留观测线索, 方便定位后端 SSE 格式回归
                console.warn('SSE parse error (pipeline event)', err, data)
              }
            } else if (currentEvent === 'text') {
              if (data) onText(data)
            }

            currentEvent = ''
            continue
          }

          if (line.trim() === '') {
            currentEvent = ''
          }
        }
      }
      onDone()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        console.error('Stream error:', err)
        reportError(err)
      }
    })

  return controller
}

export async function advanceChapter() {
  const res = await authedFetch('/api/chapter/advance', { method: 'POST' })
  return assertOk(res)
}

export async function rollback(chapter) {
  const res = await authedFetch('/api/rollback', {
    method: 'POST',
    body: JSON.stringify({ chapter }),
  })
  return assertOk(res)
}

export async function createEntity(entity) {
  const res = await authedFetch('/api/graph/entities', {
    method: 'POST',
    body: JSON.stringify(entity),
  })
  return assertOk(res)
}

export async function createRelation(relation) {
  const res = await authedFetch('/api/graph/relations', {
    method: 'POST',
    body: JSON.stringify(relation),
  })
  return assertOk(res)
}

export async function deleteEntity(entityId) {
  const res = await authedFetch(
    `/api/graph/entities/${encodeURIComponent(entityId)}`,
    { method: 'DELETE' },
  )
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return assertOk(res)
}

export async function deleteRelation(sourceId, targetId) {
  const params = new URLSearchParams({
    source_id: sourceId,
    target_id: targetId,
  })
  const res = await authedFetch(
    `/api/graph/relations?${params.toString()}`,
    { method: 'DELETE' },
  )
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return assertOk(res)
}

export async function fetchEntityDetail(entityId) {
  const res = await authedFetch(
    `/api/graph/entities/${encodeURIComponent(entityId)}`,
  )
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return assertOk(res)
}

export async function resetPipeline() {
  const res = await authedFetch('/api/reset', { method: 'POST' })
  return assertOk(res)
}

export async function takeSnapshot() {
  const res = await authedFetch('/api/snapshots', { method: 'POST' })
  return assertOk(res)
}

// ---------------------------------------------------------------------------
// LLM config (server-side fallback config; user's own key lives in localStorage)
// ---------------------------------------------------------------------------

export async function fetchLLMConfig() {
  const res = await authedFetch('/api/config/llm')
  return assertOk(res)
}

export async function fetchLLMProviders() {
  const res = await authedFetch('/api/config/llm/providers')
  return assertOk(res)
}

export async function fetchLLMRuntime() {
  const res = await authedFetch('/api/config/llm/runtime')
  return assertOk(res)
}

function _explicitProviderHeaders(config = {}) {
  // Keep the request override atomic.  Empty-key drafts are UI metadata, not
  // permission to shadow a valid server-side Provider runtime.
  if (!config.api_key) return {}
  const headers = {}
  headers['X-User-LLM-Key'] = config.api_key
  if (config.base_url) headers['X-User-LLM-Base-Url'] = config.base_url
  if (config.model) headers['X-User-LLM-Model'] = config.model
  if (config.provider) headers['X-User-LLM-Provider'] = config.provider
  if (config.thinking_mode) {
    headers['X-User-LLM-Thinking-Mode'] = config.thinking_mode
  }
  if (config.timeout != null) {
    headers['X-User-LLM-Timeout'] = String(config.timeout)
  }
  if (config.max_retries != null) {
    headers['X-User-LLM-Max-Retries'] = String(config.max_retries)
  }
  return headers
}

export async function probeLLMConfig(config = {}) {
  const res = await authedFetch('/api/config/llm/probe', {
    method: 'POST',
    headers: _explicitProviderHeaders(config),
    body: JSON.stringify({}),
    // The explicit draft is authoritative for a probe.  In particular, an
    // empty-key draft must not silently reuse a credential from another saved
    // browser identity; it intentionally probes the server fallback instead.
    skipUserLLMConfig: true,
  })
  return assertOk(res)
}

export async function updateLLMConfig({ api_key, base_url, model, provider }) {
  const body = {}
  if (api_key !== undefined) body.api_key = api_key
  if (base_url !== undefined) body.base_url = base_url
  if (model !== undefined) body.model = model
  if (provider !== undefined) body.provider = provider
  const res = await authedFetch('/api/config/llm', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  return assertOk(res)
}

// ---------------------------------------------------------------------------
// Novel management
// ---------------------------------------------------------------------------

export async function fetchNovels() {
  const res = await authedFetch('/api/novels')
  return assertOk(res)
}

export async function createNovel(title = '未命名小说', generationMode = 'author') {
  if (title && typeof title === 'object') {
    const payload = title
    const res = await authedFetch('/api/novels', {
      method: 'POST',
      body: JSON.stringify({
        ...payload,
        generation_mode: payload.generation_mode || 'author',
      }),
    })
    return assertOk(res)
  }
  const res = await authedFetch('/api/novels', {
    method: 'POST',
    body: JSON.stringify({ title, generation_mode: generationMode }),
  })
  return assertOk(res)
}

export async function updateNovelTitle(novelId, title) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}`, {
    method: 'PUT',
    body: JSON.stringify({ title }),
  })
  return assertOk(res)
}

export async function deleteNovel(novelId) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}`, {
    method: 'DELETE',
  })
  return assertOk(res)
}

export async function switchNovel(novelId) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/switch`,
    { method: 'POST' },
  )
  return assertOk(res)
}

// ---------------------------------------------------------------------------
// Whole-book author production
// ---------------------------------------------------------------------------

function _novelPath(novelId, suffix) {
  return `/api/novels/${encodeURIComponent(novelId)}${suffix}`
}

export async function fetchProductionSpec(novelId) {
  const res = await authedFetch(_novelPath(novelId, '/production-spec'))
  return assertOk(res)
}

export async function saveProductionSpec(novelId, payload) {
  const res = await authedFetch(_novelPath(novelId, '/production-spec'), {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return assertOk(res)
}

export async function generateBookOutline(novelId, payload = {}) {
  const res = await authedFetch(_novelPath(novelId, '/outline/generate'), {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return assertOk(res)
}

export async function fetchBookOutline(novelId) {
  const res = await authedFetch(_novelPath(novelId, '/outline'))
  return assertOk(res)
}

export async function saveBookOutline(novelId, payload) {
  const res = await authedFetch(_novelPath(novelId, '/outline'), {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return assertOk(res)
}

export async function fetchStyleProfiles(novelId) {
  const res = await authedFetch(_novelPath(novelId, '/style-profiles'))
  return assertOk(res)
}

export async function createStyleProfile(novelId, payload) {
  const res = await authedFetch(_novelPath(novelId, '/style-profiles'), {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return assertOk(res)
}

export async function saveStyleProfile(novelId, styleId, payload) {
  const res = await authedFetch(
    _novelPath(novelId, `/style-profiles/${encodeURIComponent(styleId)}`),
    { method: 'PUT', body: JSON.stringify(payload) },
  )
  return assertOk(res)
}

export async function deleteStyleProfile(novelId, styleId, expectedRevision = null) {
  const params = expectedRevision == null
    ? ''
    : `?expected_revision=${encodeURIComponent(expectedRevision)}`
  const res = await authedFetch(
    _novelPath(
      novelId,
      `/style-profiles/${encodeURIComponent(styleId)}${params}`,
    ),
    { method: 'DELETE' },
  )
  return assertOk(res)
}

export async function previewStyleProfile(novelId, styleId, payload = {}) {
  const res = await authedFetch(
    _novelPath(
      novelId,
      `/style-profiles/${encodeURIComponent(styleId)}/preview`,
    ),
    { method: 'POST', body: JSON.stringify(payload) },
  )
  return assertOk(res)
}

export async function activateStyleProfile(novelId, styleId, payload = {}) {
  const res = await authedFetch(
    _novelPath(
      novelId,
      `/style-profiles/${encodeURIComponent(styleId)}/activate`,
    ),
    { method: 'POST', body: JSON.stringify(payload) },
  )
  return assertOk(res)
}

async function _productionAction(novelId, action, payload = {}) {
  const res = await authedFetch(_novelPath(novelId, `/production/${action}`), {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return assertOk(res)
}

export function startProduction(novelId, payload = {}) {
  return _productionAction(novelId, 'start', payload)
}

export function pauseProduction(novelId, payload = {}) {
  return _productionAction(novelId, 'pause', payload)
}

export function resumeProduction(novelId, payload = {}) {
  return _productionAction(novelId, 'resume', payload)
}

export function cancelProduction(novelId, payload = {}) {
  return _productionAction(novelId, 'cancel', payload)
}

export function retryFailedChapter(novelId, payload = {}) {
  return _productionAction(novelId, 'retry-failed', payload)
}

export async function fetchProductionStatus(novelId) {
  const res = await authedFetch(_novelPath(novelId, '/production/status'))
  return assertOk(res)
}

export async function fetchCommittedChapters(novelId) {
  const res = await authedFetch(_novelPath(novelId, '/chapters'))
  return assertOk(res)
}

export async function fetchCommittedChapter(novelId, chapterId) {
  const res = await authedFetch(
    _novelPath(novelId, `/chapters/${encodeURIComponent(chapterId)}`),
  )
  return assertOk(res)
}

export function watchProductionEvents(
  novelId,
  { jobId, afterSequence = 0, onEvent, onError, onOpen } = {},
) {
  const query = new URLSearchParams()
  if (jobId) query.set('job_id', jobId)
  if (Number(afterSequence) > 0) {
    query.set('after_sequence', String(Number(afterSequence)))
  }
  const suffix = query.toString()
  const path = `${_novelPath(novelId, '/production/events')}${
    suffix ? `?${suffix}` : ''
  }`
  const controller = new AbortController()
  const token = getStoredToken()
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`

  fetch(`${BASE}${path}`, { headers, signal: controller.signal })
    .then(async (response) => {
      if (response.status === 401) {
        const expired = await _handleUnauthorizedResponse(response, path)
        if (expired) {
          onError?.(Object.assign(new Error('登录态已过期'), {
            code: 'AUTH_TOKEN_EXPIRED',
          }))
          return
        }
      }
      if (!response.ok) {
        try {
          await assertOk(response)
        } catch (error) {
          onError?.(error)
        }
        return
      }
      onOpen?.()
      if (!response.body) {
        onError?.(new Error('当前连接不支持生产事件流'))
        return
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let eventName = 'message'
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split(/\r?\n/)
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventName = line.slice(6).trim() || 'message'
          } else if (line.startsWith('data:')) {
            const raw = line.slice(5).trim()
            try {
              onEvent?.({ type: eventName, data: JSON.parse(raw) })
            } catch {
              onEvent?.({ type: eventName, data: raw })
            }
            eventName = 'message'
          } else if (!line.trim()) {
            eventName = 'message'
          }
        }
      }
    })
    .catch((error) => {
      if (error.name !== 'AbortError') onError?.(error)
    })

  return controller
}

// ---------------------------------------------------------------------------
// Author-mode authorities and transactional section generation
// ---------------------------------------------------------------------------

export async function fetchStoryBible(novelId) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/story-bible`,
  )
  return assertOk(res)
}

export async function saveStoryBible(novelId, payload) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/story-bible`,
    { method: 'PUT', body: JSON.stringify(payload) },
  )
  return assertOk(res)
}

export async function fetchCanonicalState(novelId) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/canonical-state`,
  )
  return assertOk(res)
}

export async function fetchStoryThreads(novelId) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/story-threads`,
  )
  return assertOk(res)
}

export async function fetchGenerationMode(novelId) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/generation-mode`,
  )
  return assertOk(res)
}

export async function updateGenerationMode(novelId, expectedRevision, mode) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/generation-mode`,
    {
      method: 'PUT',
      body: JSON.stringify({ expected_revision: expectedRevision, mode }),
    },
  )
  return assertOk(res)
}

export async function generateAuthorSection(novelId, goal) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/sections/generate`,
    { method: 'POST', body: JSON.stringify(goal) },
  )
  return assertOk(res)
}

export async function previewAuthorNarrativeContract(novelId, goal) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/sections/contract-preview`,
    { method: 'POST', body: JSON.stringify(goal) },
  )
  return assertOk(res)
}

export async function fetchAuthorSectionStatus(novelId, taskOrSectionId) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/sections/${encodeURIComponent(taskOrSectionId)}/status`,
  )
  return assertOk(res)
}

export async function fetchContextManifest(novelId) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/context-manifest`,
  )
  return assertOk(res)
}

export async function fetchAuthorLongRunStatus(novelId) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/long-run/status`,
  )
  return assertOk(res)
}

export async function fetchAuthorMemories(novelId, limit = 100) {
  const params = new URLSearchParams({ limit: String(limit) })
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/memories?${params}`,
  )
  return assertOk(res)
}

export async function fetchAuthorTransactions(novelId, limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) })
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/transactions?${params}`,
  )
  return assertOk(res)
}

export async function resumeAuthorRecovery(novelId) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/recovery/resume`,
    { method: 'POST' },
  )
  return assertOk(res)
}

async function downloadAuthorArtifact(novelId, kind) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/exports/${kind}`,
  )
  if (!res.ok) {
    return assertOk(res)
  }
  const disposition = res.headers.get('content-disposition') || ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const basic = disposition.match(/filename="([^"]+)"/i)?.[1]
  return {
    blob: await res.blob(),
    filename: encoded ? decodeURIComponent(encoded) : basic || `${kind}.txt`,
    sha256: res.headers.get('x-artifact-sha256') || '',
  }
}

export async function downloadAuthorManuscript(novelId) {
  return downloadAuthorArtifact(novelId, 'manuscript')
}

export async function downloadAuthorEvidence(novelId) {
  return downloadAuthorArtifact(novelId, 'evidence')
}

// ---------------------------------------------------------------------------
// Tick architecture
// ---------------------------------------------------------------------------

export async function fetchTickStatus() {
  const res = await authedFetch('/api/tick/status')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return assertOk(res)
}

export async function runOneTick() {
  const res = await authedFetch('/api/tick/run', { method: 'POST' })
  return assertOk(res)
}

export async function pauseTick() {
  const res = await authedFetch('/api/tick/pause', { method: 'POST' })
  return assertOk(res)
}

export async function resumeTick() {
  const res = await authedFetch('/api/tick/resume', { method: 'POST' })
  return assertOk(res)
}

export async function injectTickEvent(payload) {
  const res = await authedFetch('/api/tick/inject-event', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return assertOk(res)
}

export async function fetchTickHistory(lastN = 20) {
  const res = await authedFetch(`/api/tick/history?last_n=${lastN}`)
  return assertOk(res)
}

export async function fetchTickOpenLoops(topK = 30) {
  const res = await authedFetch(`/api/tick/open-loops?top_k=${topK}`)
  return assertOk(res)
}

export async function addTickOpenLoop(loop) {
  // assertOk 已统一处理 detail / 422 array — 不再手抄解析逻辑
  const res = await authedFetch('/api/tick/open-loops', {
    method: 'POST',
    body: JSON.stringify(loop),
  })
  return assertOk(res)
}

export async function closeTickOpenLoop(loopId) {
  const res = await authedFetch(
    `/api/tick/open-loops/${encodeURIComponent(loopId)}`,
    { method: 'DELETE' },
  )
  return assertOk(res)
}

export async function fetchCharacterStates() {
  const res = await authedFetch('/api/tick/character-states')
  return assertOk(res)
}

export async function fetchStyleAnchors(topK = 20) {
  const res = await authedFetch(`/api/tick/style-anchors?top_k=${topK}`)
  return assertOk(res)
}

export async function fetchNoveltyWarnings() {
  const res = await authedFetch('/api/tick/novelty-warnings')
  return assertOk(res)
}

export async function fetchEventStats(lastNTicks = 50) {
  const res = await authedFetch(
    `/api/tick/event-stats?last_n_ticks=${lastNTicks}`,
  )
  return assertOk(res)
}

export async function fetchActionPatterns(lastNTicks = 100) {
  const res = await authedFetch(
    `/api/tick/action-patterns?last_n_ticks=${lastNTicks}`,
  )
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return assertOk(res)
}

export async function fetchHallucinationDiagnostic() {
  const res = await authedFetch('/api/tick/diagnostic/hallucination')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return assertOk(res)
}

// Phase 6-C iter#7 + iter#B — critic decision aggregated stats (per-novel).
// Backend: GET /api/tick/critic-log/stats?start_tick=&end_tick=&window=
// Returns: { action_distribution, top_codes, ticks_scanned,
//            empty_decision_ticks, window }
// iter#B `window=N`: only the most-recent N ticks after range filter (0=all).
export async function fetchCriticLogStats({
  startTick = 0,
  endTick = 0,
  window = 0,
} = {}) {
  const params = new URLSearchParams()
  if (startTick > 0) params.set('start_tick', String(startTick))
  if (endTick > 0) params.set('end_tick', String(endTick))
  if (window > 0) params.set('window', String(window))
  const qs = params.toString()
  const url = qs ? `/api/tick/critic-log/stats?${qs}` : '/api/tick/critic-log/stats'
  const res = await authedFetch(url)
  return assertOk(res)
}

// Phase 6-C iter#6 — raw critic log rows (per-novel drill-down).
export async function fetchCriticLogRows({
  startTick = 0,
  endTick = 0,
  limit = 500,
} = {}) {
  const params = new URLSearchParams()
  if (startTick > 0) params.set('start_tick', String(startTick))
  if (endTick > 0) params.set('end_tick', String(endTick))
  if (limit) params.set('limit', String(limit))
  const res = await authedFetch(`/api/tick/critic-log?${params.toString()}`)
  return assertOk(res)
}

// ---------------------------------------------------------------------------
// Agent registry
// ---------------------------------------------------------------------------

export async function fetchAgents() {
  const res = await authedFetch('/api/agents')
  return assertOk(res)
}

export async function fetchAgentDetail(agentId) {
  const res = await authedFetch(`/api/agents/${encodeURIComponent(agentId)}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return assertOk(res)
}

// ---------------------------------------------------------------------------
// v2.24 — tick 驱动节 + 任务队列
// ---------------------------------------------------------------------------

export async function bootstrapWorld(novelId, payload) {
  const res = await authedFetch(
    `/api/novels/${encodeURIComponent(novelId)}/bootstrap-world`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
  return assertOk(res)
}

/**
 * Phase 5+ — 从后端拉 theme + style preset 注册表 (公开元数据, 无 auth 需要).
 *
 * Phase 5-D follow-up: 响应里现在还带 ``recommendations.by_theme`` (208-cell
 * matrix bench retro judge 数据), 让选了主题之后能给风格 select 加 ⭐ 排序.
 *
 * @returns {Promise<{
 *   themes: Array<{ key: string, label: string, category: string, seed: string }>,
 *   styles: Array<{ key: string, label: string, description: string }>,
 *   available: boolean,
 *   recommendations?: {
 *     available: boolean,
 *     version: number,
 *     by_theme: Record<string, Array<{
 *       style: string, mean: number, rank: number, is_top: boolean
 *     }>>,
 *     perfect_pairs: Array<{ theme: string, style: string, mean: number }>,
 *     avoid_pairs: Array<{
 *       theme: string, style: string, mean: number, low_dimensions: string[]
 *     }>,
 *     style_universal_avg: Record<string, number>,
 *   },
 * }>}
 */
export async function fetchPresets() {
  const res = await authedFetch('/api/presets')
  return assertOk(res)
}

/**
 * Phase 6-B reader API — pull narrative bodies for tick range.
 *
 * @param {object} opts
 * @param {number} [opts.startTick=0]
 * @param {number} [opts.endTick=0]  0 means up to current tick
 * @param {number} [opts.limit=500]  hard cap (server max 2000)
 * @returns {Promise<{
 *   count: number,
 *   narratives: Array<{ tick: number, text: string, char_count: number }>,
 *   start_tick: number,
 *   end_tick: number,
 *   current_tick: number,
 *   truncated?: boolean,
 * }>}
 */
export async function fetchTickNarratives({
  startTick = 0,
  endTick = 0,
  limit = 500,
  page = 1,
  perPage = 0,
} = {}) {
  // Phase 6-B iter#L — page/perPage 可选, perPage=0 → 老行为 (拿全部)
  const params = new URLSearchParams({
    start_tick: String(startTick),
    end_tick: String(endTick),
    limit: String(limit),
  })
  if (page > 1) params.set('page', String(page))
  if (perPage > 0) params.set('per_page', String(perPage))
  const res = await authedFetch(`/api/tick/narratives?${params.toString()}`)
  return assertOk(res)
}

// Phase 6 iter#AAA — narratives keyword search.
// Backend: GET /api/tick/narratives/search?q=...&start_tick=&end_tick=&limit=
// Returns: { count, results: [{tick, char_count, snippet, viewpoint_character_id}], q, truncated }
export async function searchTickNarratives({
  q,
  startTick = 0,
  endTick = 0,
  limit = 50,
} = {}) {
  if (!q) throw new Error('q required')
  const params = new URLSearchParams({ q, limit: String(limit) })
  if (startTick > 0) params.set('start_tick', String(startTick))
  if (endTick > 0) params.set('end_tick', String(endTick))
  const res = await authedFetch(`/api/tick/narratives/search?${params.toString()}`)
  return assertOk(res)
}

export async function createSectionTask(novelId = null) {
  const body = novelId ? { novel_id: novelId } : {}
  const res = await authedFetch('/api/section/generate', {
    method: 'POST',
    body: JSON.stringify(body),
  })
  return assertOk(res)
}

export async function listTickSections(novelId = null) {
  const url = novelId
    ? `/api/section/list/${encodeURIComponent(novelId)}`
    : '/api/section/list'
  const res = await authedFetch(url)
  return assertOk(res)
}

export async function listTasks(novelId = null) {
  const url = novelId
    ? `/api/tasks?novel_id=${encodeURIComponent(novelId)}`
    : '/api/tasks'
  const res = await authedFetch(url)
  return assertOk(res)
}

export async function fetchTask(taskId) {
  const res = await authedFetch(`/api/tasks/${encodeURIComponent(taskId)}`)
  return assertOk(res)
}

export async function cancelTask(taskId) {
  const res = await authedFetch(
    `/api/tasks/${encodeURIComponent(taskId)}/cancel`,
    { method: 'POST' },
  )
  return assertOk(res)
}

export function watchTaskStream(taskId, { onSnapshot, onDone, onError }) {
  const controller = new AbortController()
  const token = getStoredToken()
  const headers = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  fetch(`${BASE}/api/tasks/${encodeURIComponent(taskId)}/stream`, {
    headers,
    signal: controller.signal,
  })
    .then(async (response) => {
      if (response.status === 401) {
        const expired = await _handleUnauthorizedResponse(response, '/api/tasks/stream')
        if (expired) {
          if (typeof onError === 'function')
            onError(new Error('登录态已过期'))
          return
        }
      }
      if (!response.ok) {
        const err = new Error(`HTTP ${response.status}`)
        if (typeof onError === 'function') onError(err)
        return
      }
      // 修复(sse-6) — null body 防护
      if (!response.body) {
        if (typeof onError === 'function')
          onError(new Error('Streaming not supported by this transport'))
        return
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''
      // 修复(sse-5) — 防双触发 onDone (终态 snapshot + while 退出后兜底 onDone(null))
      let doneFired = false
      const fireDone = (snap) => {
        if (doneFired) return
        doneFired = true
        if (typeof onDone === 'function') onDone(snap)
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        // 修复(sse-1) — \r?\n 正则切, 兼容代理换行规范化
        const lines = buffer.split(/\r?\n/)
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
            continue
          }
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (currentEvent === 'snapshot') {
              try {
                const snap = JSON.parse(data)
                onSnapshot(snap)
                if (
                  snap.status === 'completed' ||
                  snap.status === 'failed' ||
                  snap.status === 'cancelled'
                ) {
                  fireDone(snap)
                }
              } catch (err) {
                // 修复(15) 同类 — 保留原"吞掉继续读流"语义, 仅补观测线索
                console.warn('SSE parse error (task snapshot)', err, data)
              }
            } else if (currentEvent === 'error') {
              if (typeof onError === 'function') onError(new Error(data))
            }
            currentEvent = ''
            continue
          }
          if (line.trim() === '') currentEvent = ''
        }
      }
      fireDone(null)
    })
    .catch((err) => {
      if (err.name === 'AbortError') return
      if (typeof onError === 'function') onError(err)
    })

  return controller
}

// ---------------------------------------------------------------------------
// Stateful Pipeline API (v2.50+)
// ---------------------------------------------------------------------------

export async function fetchPipelineSynopses(novelId) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/synopsis`)
  return assertOk(res)
}

export async function fetchPipelineSynopsis(novelId, chapter) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/synopsis/${chapter}`)
  return assertOk(res)
}

export async function updatePipelineSynopsis(novelId, chapter, payload) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/synopsis/${chapter}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return assertOk(res)
}

export async function generatePipelineSynopses(novelId) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/synopsis/generate`, {
    method: 'POST',
  })
  return assertOk(res)
}

export async function fetchPipelineSchema(novelId) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/schema`)
  return assertOk(res)
}

export async function updatePipelineSchema(novelId, fields) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/schema`, {
    method: 'PUT',
    body: JSON.stringify({ fields }),
  })
  return assertOk(res)
}

export async function generatePipelineSchema(novelId) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/schema/generate`, {
    method: 'POST',
  })
  return assertOk(res)
}

export async function fetchPipelineForeshadows(novelId) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/foreshadows`)
  return assertOk(res)
}

export async function fetchPipelineForeshadowState(novelId) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/foreshadows/state`)
  return assertOk(res)
}

export async function fetchPipelineStatus(novelId, chapter) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/status/${chapter}`)
  return assertOk(res)
}

export async function fetchPipelineCurrentStatus(novelId) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/status`)
  return assertOk(res)
}

export async function confirmPipelineChapter(novelId, chapter, options = {}) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/confirm`, {
    method: 'POST',
    body: JSON.stringify({
      chapter,
      foreshadow_mode: options.foreshadowMode || 'random',
      foreshadow_count: options.foreshadowCount || 0,
    }),
  })
  return assertOk(res)
}

export async function generatePipelineChapter(novelId, chapter) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/generate/${chapter}`, {
    method: 'POST',
  })
  return assertOk(res)
}

export async function fetchPipelineChromaStatus(novelId) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/chroma/status`)
  return assertOk(res)
}

export async function rebuildPipelineChroma(novelId) {
  const res = await authedFetch(`/api/novels/${encodeURIComponent(novelId)}/pipeline/chroma/rebuild`, {
    method: 'POST',
  })
  return assertOk(res)
}
