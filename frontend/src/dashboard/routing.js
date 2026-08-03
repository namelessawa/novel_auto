export const DEFAULT_VIEW = 'production'

export const MAIN_VIEWS = new Set([
  'production',
  'outline',
  'chapters',
  'styles',
  'bible',
  'state',
  'memory',
  'provider',
  'export',
  'lab',
])

export const LAB_VIEWS = new Set([
  'lab-manual',
  'lab-overview',
  'lab-tick',
  'lab-agent',
  'lab-kg',
  'lab-multimodal',
])

const LEGACY_ALIASES = {
  author: 'production',
  chapter: 'chapters',
  threads: 'memory',
  config: 'provider',
  overview: 'lab-overview',
  tick: 'lab-tick',
  agent: 'lab-agent',
  kg: 'lab-kg',
  multimodal: 'lab-multimodal',
}

export function normalizeView(value) {
  const candidate = String(value || '')
    .replace(/^#\/?/, '')
    .replace(/^\/+/, '')
    .split(/[/?]/, 1)[0]
    .trim()
  const resolved = LEGACY_ALIASES[candidate] || candidate
  return MAIN_VIEWS.has(resolved) || LAB_VIEWS.has(resolved)
    ? resolved
    : DEFAULT_VIEW
}

export function viewFromHash(hash) {
  return normalizeView(hash)
}

export function hashForView(view) {
  return `#/${normalizeView(view)}`
}

export function mainNavigationView(view) {
  return LAB_VIEWS.has(view) ? 'lab' : normalizeView(view)
}
