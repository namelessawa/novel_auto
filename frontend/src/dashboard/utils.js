// v2.47 — Dashboard 共享工具.

export function formatNum(n) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—'
  return n.toLocaleString()
}

export function formatTick(n) {
  if (typeof n !== 'number') return '—'
  return n.toLocaleString()
}

// ms → human "26d 14h" / "5h 12m" / "33m"
export function formatRuntime(ms) {
  if (typeof ms !== 'number' || ms <= 0) return '—'
  const sec = Math.floor(ms / 1000)
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  if (d > 0) return `${d}d ${h}h`
  const m = Math.floor((sec % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

export function clamp(n, lo, hi) {
  return Math.max(lo, Math.min(hi, n))
}

// "百分比 like" — Math.round + bounded 0..100
export function pct(num, denom) {
  if (!denom || typeof num !== 'number' || typeof denom !== 'number') return null
  return clamp(Math.round((num / denom) * 100), 0, 100)
}

// 把后端 narratives[].tick (绝对) 映射为 "tick N · 共 M 字"
export function formatNarrMeta(item) {
  if (!item) return null
  const tick = typeof item.tick === 'number' ? item.tick.toLocaleString() : '—'
  const cc = typeof item.char_count === 'number' ? item.char_count.toLocaleString() : null
  return cc ? `tick ${tick} · ${cc} 字` : `tick ${tick}`
}

// OpenLoop 数据规范化 — 后端 schema 在不同版本里命名不同, 这里兜底.
export function classifyLoop(loop = {}) {
  const title =
    loop.title || loop.summary || loop.description || loop.text || loop.label ||
    '未命名伏笔'
  const body =
    loop.detail || loop.body || loop.note || loop.context || loop.summary_long || ''
  const importance =
    typeof loop.importance === 'number' ? loop.importance : null
  const priority = String(
    loop.priority ||
      (importance !== null && importance >= 7 ? 'high' : 'medium'),
  ).toLowerCase()
  const age = loop.age_ticks ?? loop.tick_age ?? loop.age ?? null
  const origin = loop.origin || loop.source || loop.event_id || null
  const refs = loop.refs ?? loop.ref_count ?? loop.refs_count ?? null
  const protectedFlag = Boolean(loop.protected || loop.is_protected)
  return { title, body, priority, age, origin, refs, protectedFlag }
}

export function safeEmail(user) {
  if (!user) return ''
  return user.email || user.username || ''
}

// 用 email 第一个字母做 Avatar (大写, 兜底 Z)
export function avatarLetter(user) {
  const e = safeEmail(user)
  return e ? e[0].toUpperCase() : 'Z'
}

// 12 plain bars values [0..1] 推断 height class
export function classifyBar(v, isNow = false) {
  if (isNow) return 'is-now'
  if (v >= 0.8) return 'is-peak'
  if (v >= 0.55) return 'is-high'
  if (v >= 0.3) return 'is-mid'
  return ''
}
