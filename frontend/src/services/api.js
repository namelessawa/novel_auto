// In production (Vercel), VITE_API_BASE points to the backend server.
// In local dev, empty string lets the vite proxy handle /api requests.
const BASE = import.meta.env.VITE_API_BASE || ''

// ---------------------------------------------------------------------------
// Legacy section pipeline
// ---------------------------------------------------------------------------

export async function fetchStats() {
  const res = await fetch(`${BASE}/api/stats`)
  return res.json()
}

export async function fetchSections() {
  const res = await fetch(`${BASE}/api/sections`)
  return res.json()
}

export async function fetchGraph() {
  const res = await fetch(`${BASE}/api/graph`)
  return res.json()
}

export async function fetchOutline() {
  const res = await fetch(`${BASE}/api/outline`)
  return res.json()
}

export async function fetchMemory() {
  const res = await fetch(`${BASE}/api/memory`)
  return res.json()
}

export async function fetchSnapshots() {
  const res = await fetch(`${BASE}/api/snapshots`)
  return res.json()
}

export async function generateSection(outline = '') {
  const res = await fetch(`${BASE}/api/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ outline }),
  })
  return res.json()
}

export function generateSectionStream(outline = '', onEvent, onText, onDone) {
  const controller = new AbortController()

  fetch(`${BASE}/api/generate/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ outline }),
    signal: controller.signal,
  })
    .then(async (response) => {
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
        onDone()
      }
    })

  return controller
}

export async function advanceChapter() {
  const res = await fetch(`${BASE}/api/chapter/advance`, { method: 'POST' })
  return res.json()
}

export async function rollback(chapter) {
  const res = await fetch(`${BASE}/api/rollback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chapter }),
  })
  return res.json()
}

export async function createEntity(entity) {
  const res = await fetch(`${BASE}/api/graph/entities`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entity),
  })
  return res.json()
}

export async function createRelation(relation) {
  const res = await fetch(`${BASE}/api/graph/relations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(relation),
  })
  return res.json()
}

export async function resetPipeline() {
  const res = await fetch(`${BASE}/api/reset`, { method: 'POST' })
  return res.json()
}

export async function takeSnapshot() {
  const res = await fetch(`${BASE}/api/snapshots`, { method: 'POST' })
  return res.json()
}

// ---------------------------------------------------------------------------
// LLM config
// ---------------------------------------------------------------------------

export async function fetchLLMConfig() {
  const res = await fetch(`${BASE}/api/config/llm`)
  return res.json()
}

export async function updateLLMConfig({ api_key, base_url, model, provider }) {
  // v2.20 — provider 是 active provider 切换 (deepseek/mimo/custom), 后端
  // 写 os.environ['LLM_PROVIDER']; 不传时保持当前值不变。
  // api_key/base_url/model 写入 config.json.llm 兜底段, 与 provider 切换正交。
  const body = {}
  if (api_key !== undefined) body.api_key = api_key
  if (base_url !== undefined) body.base_url = base_url
  if (model !== undefined) body.model = model
  if (provider !== undefined) body.provider = provider
  const res = await fetch(`${BASE}/api/config/llm`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
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

// ---------------------------------------------------------------------------
// Novel management
// ---------------------------------------------------------------------------

export async function fetchNovels() {
  const res = await fetch(`${BASE}/api/novels`)
  return res.json()
}

export async function createNovel(title = '未命名小说') {
  const res = await fetch(`${BASE}/api/novels`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return res.json()
}

export async function updateNovelTitle(novelId, title) {
  const res = await fetch(`${BASE}/api/novels/${encodeURIComponent(novelId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return res.json()
}

export async function deleteNovel(novelId) {
  const res = await fetch(`${BASE}/api/novels/${encodeURIComponent(novelId)}`, {
    method: 'DELETE',
  })
  return res.json()
}

export async function switchNovel(novelId) {
  const res = await fetch(
    `${BASE}/api/novels/${encodeURIComponent(novelId)}/switch`,
    { method: 'POST' }
  )
  return res.json()
}

// ---------------------------------------------------------------------------
// Tick architecture
// ---------------------------------------------------------------------------

export async function fetchTickStatus() {
  const res = await fetch(`${BASE}/api/tick/status`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function runOneTick() {
  const res = await fetch(`${BASE}/api/tick/run`, { method: 'POST' })
  return res.json()
}

export async function pauseTick() {
  const res = await fetch(`${BASE}/api/tick/pause`, { method: 'POST' })
  return res.json()
}

export async function resumeTick() {
  const res = await fetch(`${BASE}/api/tick/resume`, { method: 'POST' })
  return res.json()
}

export async function injectTickEvent(payload) {
  const res = await fetch(`${BASE}/api/tick/inject-event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  // v2.19.1 — 后端在 422 (非法 type / 空 location + all_in_location) 或 409
  // (重复 id) 时返回 JSON 错误体, 但 res.json() 自身不会抛, 调用方原本会拿到
  // {detail: ...} 然后访问 .event?.tick → undefined, toast 仍显示"成功 (tick
  // undefined)"。这里把非 2xx 显式翻成 Error, 让调用方 catch 分支真正生效。
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body && typeof body.detail === 'string') {
        detail = body.detail
      } else if (body && Array.isArray(body.detail)) {
        // FastAPI 422 详细列表 — 拼接 loc + msg
        detail = body.detail
          .map((d) => `${(d.loc || []).join('.')}: ${d.msg}`)
          .join('; ')
      }
    } catch {
      /* 非 JSON 错误体保持 HTTP ${status} 默认值 */
    }
    throw new Error(detail)
  }
  return res.json()
}

export async function fetchTickHistory(lastN = 20) {
  const res = await fetch(`${BASE}/api/tick/history?last_n=${lastN}`)
  return res.json()
}

export async function fetchTickOpenLoops(topK = 30) {
  const res = await fetch(`${BASE}/api/tick/open-loops?top_k=${topK}`)
  return res.json()
}

// v2.20 — OpenLoop CRUD wrappers
// 后端 POST 在 dup-id 时返 409 (v2.19.3), DELETE 在不存在时静默 200。
// 两个 wrapper 都把非 2xx 翻成 Error, 让调用方 catch 显示真实原因。

export async function addTickOpenLoop(loop) {
  const res = await fetch(`${BASE}/api/tick/open-loops`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
  const res = await fetch(
    `${BASE}/api/tick/open-loops/${encodeURIComponent(loopId)}`,
    { method: 'DELETE' }
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
  const res = await fetch(`${BASE}/api/tick/character-states`)
  return res.json()
}

export async function fetchStyleAnchors(topK = 20) {
  const res = await fetch(`${BASE}/api/tick/style-anchors?top_k=${topK}`)
  return res.json()
}

export async function fetchNoveltyWarnings() {
  const res = await fetch(`${BASE}/api/tick/novelty-warnings`)
  return res.json()
}

export async function fetchEventStats(lastNTicks = 50) {
  const res = await fetch(
    `${BASE}/api/tick/event-stats?last_n_ticks=${lastNTicks}`
  )
  return res.json()
}

// v2.20 — Tick diagnostics wrappers (后端 v2.16 / v2.18 Phase 9 已上, 前端缺)

export async function fetchActionPatterns(lastNTicks = 100) {
  const res = await fetch(
    `${BASE}/api/tick/action-patterns?last_n_ticks=${lastNTicks}`
  )
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchHallucinationDiagnostic() {
  const res = await fetch(`${BASE}/api/tick/diagnostic/hallucination`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

// ---------------------------------------------------------------------------
// Agent registry (9 v2 tick agents + ActionResolver)
// ---------------------------------------------------------------------------

export async function fetchAgents() {
  const res = await fetch(`${BASE}/api/agents`)
  return res.json()
}

export async function fetchAgentDetail(agentId) {
  const res = await fetch(
    `${BASE}/api/agents/${encodeURIComponent(agentId)}`
  )
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
