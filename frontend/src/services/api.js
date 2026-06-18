// In production (Vercel), VITE_API_BASE points to the backend server.
// In local dev, empty string lets the vite proxy handle /api requests.
const BASE = import.meta.env.VITE_API_BASE || ''

// ---------------------------------------------------------------------------
// v2.26 — Auth interceptor
// ---------------------------------------------------------------------------
// - Reads JWT from localStorage on every request
// - Attaches Authorization: Bearer <token>
// - On 401: clears token + dispatches "auth:expired" event so AuthContext logs out
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

async function authedFetch(path, init = {}) {
  const headers = new Headers(init.headers || {})
  if (!headers.has('Content-Type') && init.body && typeof init.body === 'string') {
    headers.set('Content-Type', 'application/json')
  }
  const token = getStoredToken()
  if (token && !_isPublicPath(path)) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  // v2.28 — 总是带上用户的 LLM 凭据 header. 后端 middleware 写入 ContextVar,
  // 让所有 LLM 调用 (主创作链 / 随机种子 / 续写) 都用用户的 key 而非 config.json.
  // 公开路径 (登录/注册) 不发, 减少 noise.
  if (!_isPublicPath(path)) {
    const llm = getUserLLMConfig()
    if (llm.api_key && !headers.has('X-User-LLM-Key')) {
      headers.set('X-User-LLM-Key', llm.api_key)
      if (llm.base_url) headers.set('X-User-LLM-Base-Url', llm.base_url)
      if (llm.model) headers.set('X-User-LLM-Model', llm.model)
    }
  }
  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  // sliding refresh: 后端在距过期 < 1 天时通过 X-Refreshed-Token 响应头签新 token,
  // 浏览器 JS 仅在后端 expose_headers 显式列出时能读到 (main.py CORS 已配置).
  try {
    const fresh = res.headers.get('X-Refreshed-Token')
    if (fresh) setStoredToken(fresh)
  } catch {
    /* private mode / 跨域无 expose 等情况静默忽略 */
  }
  if (res.status === 401 && !_isPublicPath(path)) {
    _handleUnauthorized()
  }
  return res
}

async function assertOk(res) {
  if (res.ok) {
    // 204 No Content
    if (res.status === 204) return null
    return res.json()
  }
  let detail = `HTTP ${res.status}`
  try {
    const body = await res.json()
    if (body && typeof body.detail === 'string') {
      detail = body.detail
    } else if (body && Array.isArray(body.detail)) {
      detail = body.detail
        .map((d) => `${(d.loc || []).join('.')}: ${d.msg}`)
        .join('; ')
    }
  } catch {
    /* keep default */
  }
  throw new Error(detail)
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

export function getUserLLMConfig() {
  try {
    const raw = localStorage.getItem(USER_LLM_STORAGE_KEY)
    if (!raw) return { api_key: '', base_url: '', model: '' }
    return JSON.parse(raw)
  } catch {
    return { api_key: '', base_url: '', model: '' }
  }
}

export function setUserLLMConfig({ api_key, base_url, model, provider }) {
  try {
    const payload = { api_key, base_url, model }
    // 修复(11) — 持久化 provider id, ConfigView 读取时优先用它而非 base_url 推断。
    // 旧调用方不传 provider 时不写该字段, 读取方退回推断 — 向后兼容。
    if (provider) payload.provider = provider
    localStorage.setItem(USER_LLM_STORAGE_KEY, JSON.stringify(payload))
  } catch {
    /* silent */
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
    // 修复(17) — 复用共享 401 处理, 与 authedFetch 行为永远同步,
    // 防止登录态过期后所有资产加载静默失败, 用户卡在"加载中…"
    _handleUnauthorized()
    throw new Error('登录态已过期, 请重新登录')
  }
  if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${filename}`)
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

// 修复(16) — X-User-LLM-* headers 统一由 authedFetch 注入 (它对所有非公开
// 路径在 api_key 存在时自动加), 调用点不再手工重复 (原 _userLLMHeaders 已删)。

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
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  fetch(`${BASE}/api/generate/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ outline }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (response.status === 401) {
        _handleUnauthorized()
        reportError(new Error('登录态已过期, 请重新登录'))
        return
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

export async function createNovel(title = '未命名小说') {
  const res = await authedFetch('/api/novels', {
    method: 'POST',
    body: JSON.stringify({ title }),
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
export async function fetchTickNarratives({ startTick = 0, endTick = 0, limit = 500 } = {}) {
  const params = new URLSearchParams({
    start_tick: String(startTick),
    end_tick: String(endTick),
    limit: String(limit),
  })
  const res = await authedFetch(`/api/tick/narratives?${params.toString()}`)
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
        _handleUnauthorized()
        if (typeof onError === 'function')
          onError(new Error('登录态已过期'))
        return
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
