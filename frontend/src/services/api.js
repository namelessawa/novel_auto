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
    path === '/api/health'
  )
}

function _emit401() {
  try {
    window.dispatchEvent(new CustomEvent('auth:expired'))
  } catch {
    /* SSR-safe noop */
  }
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
  if (res.status === 401 && !_isPublicPath(path)) {
    setStoredToken('')
    _emit401()
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

export async function authSetPassword(password) {
  const res = await authedFetch('/api/auth/me/set-password', {
    method: 'POST',
    body: JSON.stringify({ password }),
  })
  return assertOk(res)
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
    await authedFetch('/api/auth/logout', { method: 'POST' })
  } catch {
    /* server-side noop; ignore failure */
  }
  setStoredToken('')
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

export function setUserLLMConfig({ api_key, base_url, model }) {
  try {
    localStorage.setItem(
      USER_LLM_STORAGE_KEY,
      JSON.stringify({ api_key, base_url, model }),
    )
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
    // 与 authedFetch 同步, 防止登录态过期后所有资产加载静默失败, 用户卡在"加载中…"
    setStoredToken('')
    _emit401()
    throw new Error('登录态已过期, 请重新登录')
  }
  if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${filename}`)
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

function _userLLMHeaders() {
  const c = getUserLLMConfig()
  const h = {}
  if (c.api_key) h['X-User-LLM-Key'] = c.api_key
  if (c.base_url) h['X-User-LLM-Base-Url'] = c.base_url
  if (c.model) h['X-User-LLM-Model'] = c.model
  return h
}

export async function randomSeed({ existing_title = '' } = {}) {
  const res = await authedFetch('/api/llm/random-seed', {
    method: 'POST',
    headers: _userLLMHeaders(),
    body: JSON.stringify({ existing_title }),
  })
  return assertOk(res) // { text }
}

export async function randomTitle({ existing_seed = '' } = {}) {
  const res = await authedFetch('/api/llm/random-title', {
    method: 'POST',
    headers: _userLLMHeaders(),
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
    headers: _userLLMHeaders(),
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
  return res.json()
}

export async function fetchSections() {
  const res = await authedFetch('/api/sections')
  return res.json()
}

export async function fetchGraph() {
  const res = await authedFetch('/api/graph')
  return res.json()
}

export async function fetchOutline() {
  const res = await authedFetch('/api/outline')
  return res.json()
}

export async function fetchMemory() {
  const res = await authedFetch('/api/memory')
  return res.json()
}

export async function fetchSnapshots() {
  const res = await authedFetch('/api/snapshots')
  return res.json()
}

export async function generateSection(outline = '') {
  const res = await authedFetch('/api/generate', {
    method: 'POST',
    body: JSON.stringify({ outline }),
  })
  return res.json()
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
        setStoredToken('')
        _emit401()
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
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
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
              } catch {
                /* ignore parse errors */
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
  return res.json()
}

export async function rollback(chapter) {
  const res = await authedFetch('/api/rollback', {
    method: 'POST',
    body: JSON.stringify({ chapter }),
  })
  return res.json()
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
  return res.json()
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
  return res.json()
}

export async function fetchEntityDetail(entityId) {
  const res = await authedFetch(
    `/api/graph/entities/${encodeURIComponent(entityId)}`,
  )
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function resetPipeline() {
  const res = await authedFetch('/api/reset', { method: 'POST' })
  return res.json()
}

export async function takeSnapshot() {
  const res = await authedFetch('/api/snapshots', { method: 'POST' })
  return res.json()
}

// ---------------------------------------------------------------------------
// LLM config (server-side fallback config; user's own key lives in localStorage)
// ---------------------------------------------------------------------------

export async function fetchLLMConfig() {
  const res = await authedFetch('/api/config/llm')
  return res.json()
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
  return res.json()
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
  return res.json()
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
  return res.json()
}

export async function addTickOpenLoop(loop) {
  const res = await authedFetch('/api/tick/open-loops', {
    method: 'POST',
    body: JSON.stringify(loop),
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const j = await res.json()
      if (typeof j?.detail === 'string') detail = j.detail
      else if (Array.isArray(j?.detail)) {
        detail = j.detail
          .map((d) => `${(d.loc || []).join('.')}: ${d.msg}`)
          .join('; ')
      }
    } catch {
      /* keep default */
    }
    throw new Error(detail)
  }
  return res.json()
}

export async function closeTickOpenLoop(loopId) {
  const res = await authedFetch(
    `/api/tick/open-loops/${encodeURIComponent(loopId)}`,
    { method: 'DELETE' },
  )
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const j = await res.json()
      if (typeof j?.detail === 'string') detail = j.detail
    } catch {
      /* keep default */
    }
    throw new Error(detail)
  }
  return res.json()
}

export async function fetchCharacterStates() {
  const res = await authedFetch('/api/tick/character-states')
  return res.json()
}

export async function fetchStyleAnchors(topK = 20) {
  const res = await authedFetch(`/api/tick/style-anchors?top_k=${topK}`)
  return res.json()
}

export async function fetchNoveltyWarnings() {
  const res = await authedFetch('/api/tick/novelty-warnings')
  return res.json()
}

export async function fetchEventStats(lastNTicks = 50) {
  const res = await authedFetch(
    `/api/tick/event-stats?last_n_ticks=${lastNTicks}`,
  )
  return res.json()
}

export async function fetchActionPatterns(lastNTicks = 100) {
  const res = await authedFetch(
    `/api/tick/action-patterns?last_n_ticks=${lastNTicks}`,
  )
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchHallucinationDiagnostic() {
  const res = await authedFetch('/api/tick/diagnostic/hallucination')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

// ---------------------------------------------------------------------------
// Agent registry
// ---------------------------------------------------------------------------

export async function fetchAgents() {
  const res = await authedFetch('/api/agents')
  return res.json()
}

export async function fetchAgentDetail(agentId) {
  const res = await authedFetch(`/api/agents/${encodeURIComponent(agentId)}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
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
        setStoredToken('')
        _emit401()
        if (typeof onError === 'function')
          onError(new Error('登录态已过期'))
        return
      }
      if (!response.ok) {
        const err = new Error(`HTTP ${response.status}`)
        if (typeof onError === 'function') onError(err)
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
        const lines = buffer.split('\n')
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
                  if (typeof onDone === 'function') onDone(snap)
                }
              } catch {
                /* skip */
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
      if (typeof onDone === 'function') onDone(null)
    })
    .catch((err) => {
      if (err.name === 'AbortError') return
      if (typeof onError === 'function') onError(err)
    })

  return controller
}
