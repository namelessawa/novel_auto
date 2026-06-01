// In production (Vercel), VITE_API_BASE points to the backend server.
// In local dev, empty string lets the vite proxy handle /api requests.
const BASE = import.meta.env.VITE_API_BASE || ''

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
  }).then(async (response) => {
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
            } catch { /* ignore parse errors */ }
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
  }).catch((err) => {
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

export async function fetchLLMConfig() {
  const res = await fetch(`${BASE}/api/config/llm`)
  return res.json()
}

export async function updateLLMConfig({ api_key, base_url, model }) {
  const body = {}
  if (api_key !== undefined) body.api_key = api_key
  if (base_url !== undefined) body.base_url = base_url
  if (model !== undefined) body.model = model
  const res = await fetch(`${BASE}/api/config/llm`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return res.json()
}

// -- Novel Management -------------------------------------------------------

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
  const res = await fetch(`${BASE}/api/novels/${encodeURIComponent(novelId)}/switch`, {
    method: 'POST',
  })
  return res.json()
}
