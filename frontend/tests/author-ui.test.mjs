import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import TestRenderer, { act } from 'react-test-renderer'
import { createServer } from 'vite'

globalThis.IS_REACT_ACT_ENVIRONMENT = true
globalThis.window = {
  addEventListener() {},
  removeEventListener() {},
  confirm: () => true,
  dispatchEvent() {},
  location: { hash: '' },
  history: { replaceState() {} },
  setTimeout,
  clearTimeout,
}
globalThis.document = { visibilityState: 'visible' }

const vite = await createServer({
  appType: 'custom',
  logLevel: 'error',
  server: { middlewareMode: true },
})

after(async () => {
  await vite.close()
})

async function load(path) {
  return vite.ssrLoadModule(path)
}

async function render(path, props) {
  const module = await load(path)
  return renderToStaticMarkup(React.createElement(module.default, props))
}

async function mount(path, props) {
  const module = await load(path)
  let renderer
  await act(async () => {
    renderer = TestRenderer.create(React.createElement(module.default, props))
    await flush()
  })
  return renderer
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve))
  await Promise.resolve()
}

function nodeText(node) {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  return (node?.children || []).map(nodeText).join('')
}

function findButton(renderer, text) {
  return renderer.root.findAllByType('button').find((node) => nodeText(node).includes(text))
}

function findLabeledControl(renderer, labelText) {
  const label = renderer.root
    .findAllByType('label')
    .find((node) => nodeText(node).includes(labelText))
  if (!label) return null
  return label.findAll(
    (node) => ['input', 'textarea', 'select'].includes(node.type),
  )[0]
}

function snapshotText(renderer) {
  return JSON.stringify(renderer.toJSON())
}

async function click(node) {
  await act(async () => {
    await node.props.onClick()
    await flush()
  })
}

async function change(node, value) {
  await act(async () => {
    node.props.onChange({ target: { value } })
    await flush()
  })
}

const exactSeed = '第一行  保留双空格\n第二行：保留换行。'
const storyBible = {
  revision: 2,
  title: '潮痕',
  source_seed: exactSeed,
  theme_key: 'mystery',
  positioning: '克制的现实主义悬疑',
  reference_preferences: ['参考节奏，不复制表达'],
  premise: '守灯人发现一封旧信。',
  theme: '记忆与责任',
  central_question: '沉默能保护谁？',
  genre: '现实主义悬疑',
  setting_summary: '没有超自然力量的近代港城。',
  immutable_world_rules: ['世界不存在超自然力量'],
  forbidden_deviations: ['不得改写为超能力对决'],
  protagonist_contracts: ['沈砚谨慎且重承诺'],
  main_conflicts: ['公开真相会伤害家族'],
  ending_direction: '真相公开并留下关系裂痕',
  style_contract: { tone: '克制', viewpoint: '第三人称限知' },
  field_provenance: { source_seed: 'user_input', theme_key: 'preset_derived' },
  migration: { needs_confirmation: false, source: 'user_input', inferred_fields: [], source_files: [] },
}

const canonicalState = {
  revision: 3,
  world_time: 8,
  world: { locations: [{ id: 'lighthouse', name: '旧灯塔' }] },
  characters: {
    shen_yan: {
      name: '沈砚',
      alive: true,
      location: 'lighthouse',
      inventory: ['sealed_letter'],
      emotional_state: '迟疑',
    },
  },
  items: {
    sealed_letter: { name: '旧信', owners: ['shen_yan'], status: '未拆封' },
  },
  character_knowledge: { shen_yan: ['旧信与港难有关'] },
  reader_knowledge: { letter: '旧信与港难有关' },
  canonical_facts: { harbor_disaster: '十二年前发生港难' },
  relationships: {},
  plot_position: { arc: 'opening' },
  last_scene_state: { location: 'lighthouse' },
}

function storyBibleApi(overrides = {}) {
  return {
    fetchStoryBible: async () => ({ story_bible: storyBible, migration: storyBible.migration }),
    saveStoryBible: async (_novelId, payload) => ({
      story_bible: { ...storyBible, ...payload, revision: payload.expected_revision + 1 },
    }),
    ...overrides,
  }
}

function authorApi(overrides = {}) {
  return {
    fetchStoryBible: async () => ({ story_bible: storyBible }),
    fetchCanonicalState: async () => ({ canonical_state: canonicalState }),
    fetchStoryThreads: async () => ({
      threads: { harbor: { id: 'harbor', description: '调查港难', status: 'open' } },
    }),
    fetchGenerationMode: async () => ({ mode: 'author', revision: 4 }),
    listTickSections: async () => ({ sections: [] }),
    updateGenerationMode: async (_novelId, revision, mode) => ({ mode, revision: revision + 1 }),
    generateAuthorSection: async () => ({ id: 'task-1', status: 'queued' }),
    fetchAuthorSectionStatus: async () => ({
      task: { id: 'task-1', status: 'completed', committed: true },
      transaction: { id: 'tx-1', phase: 'committed', committed: true },
      section: { id: 'section-1' },
    }),
    fetchContextManifest: async () => ({
      contract_hash: 'abc123456789',
      execution_spec_hash: 'def987654321',
      selected_memory_ids: ['memory-promise'],
      memory_selections: [{
        memory_id: 'memory-promise',
        selection_reason: 'target_thread_match',
      }],
      active_thread_ids: ['harbor'],
      total_chars: 7200,
      max_context_chars: 24000,
      total_token_estimate: 3600,
      max_context_token_estimate: 12000,
      budget_utilization: 0.3,
      rejected_reason: '',
      slots: [{ name: 'story_bible', char_count: 1200, token_estimate: 600, truncated: false }],
    }),
    fetchAuthorMemories: async () => ({
      revision: 5,
      selected_memory_ids: ['memory-promise'],
      records: [{
        id: 'memory-promise',
        type: 'promise',
        summary: '沈砚承诺在天亮前交付旧信。',
        importance: 8,
        canon_status: 'confirmed',
        created_at_revision: 3,
        selected: true,
      }],
    }),
    fetchAuthorTransactions: async () => ({ transactions: [], total: 0 }),
    resumeAuthorRecovery: async () => ({
      status: 'clean',
      pending_before: [],
      recovered_transaction_ids: [],
      pending_after: [],
    }),
    downloadAuthorManuscript: async () => ({
      blob: null,
      filename: 'manuscript.md',
      sha256: 'a'.repeat(64),
    }),
    downloadAuthorEvidence: async () => ({
      blob: null,
      filename: 'evidence.json',
      sha256: 'b'.repeat(64),
    }),
    previewAuthorNarrativeContract: async () => ({
      narrative_contract: {
        required_events: [{ id: 'open', action: '打开旧信', description: '沈砚打开旧信' }],
        required_end_state: [{ id: 'truth', path: '/items/letter/holder', expected: '调查员' }],
        forbidden_additions: ['未授权的亲属关系'],
        time_constraints: [{ id: 'dawn', description: '必须在天亮前交信' }],
        allowed_entities: { characters: [{ id: 'shen_yan', name: '沈砚' }] },
        length_constraint: { min_chars: 900, max_chars: 1200 },
      },
      event_execution_plan: {
        ordered_events: [{ id: 'open', order: 1, actor: 'shen_yan', action: '打开旧信', description: '沈砚打开旧信' }],
      },
      section_writing_plan: {
        target_chars: 900,
        min_chars: 900,
        max_chars: 1100,
        structure: [
          { part: 'opening', target_chars: 180, purpose: '建立场景' },
          { part: 'development', target_chars: 250, purpose: '推进既有动作' },
          { part: 'conflict', target_chars: 250, purpose: '完成冲突' },
          { part: 'resolution', target_chars: 220, purpose: '落实终态' },
        ],
        style_adaptation: {
          allowed_expansion: ['existing action detail'],
          forbidden_expansion: ['new event'],
        },
      },
      section_budget_plan: {
        target_chars: 1000,
        min_chars: 900,
        max_chars: 1100,
        segments: [
          { name: 'opening', budget: 180, max_chars: 230 },
          { name: 'development', budget: 300, max_chars: 350 },
          { name: 'conflict', budget: 300, max_chars: 350 },
          { name: 'resolution', budget: 220, max_chars: 270 },
        ],
        stop_conditions: [
          'required_events_completed',
          'end_state_reached',
          'minimum_length_reached',
        ],
        style_balance_contract: {
          limits: ['description serves event'],
          forbidden: ['post-resolution expansion'],
        },
      },
    }),
    fetchAuthorLongRunStatus: async () => ({
      run_id: 'run-1',
      completed_sections: 3,
      contract_pass_rate: 1,
      repair_rate: 0.25,
      hard_reject_count: 0,
      canonical_revision: 4,
      total_tokens: 1234,
      average_latency_seconds: 2.5,
      restart_recovery_count: 1,
    }),
    ...overrides,
  }
}

test('sidebar presents the whole-book workflow in its required order', async () => {
  const html = await render('/src/dashboard/Sidebar.jsx', {
    novels: [],
    activeNovelId: null,
    view: 'production',
    tasks: [],
  })
  const orderedLabels = [
    '生产中心',
    '故事蓝图',
    '风格工作室',
    '章节',
    '当前事实',
    '故事线与记忆',
    '生成管线',
    'Provider 配置',
    '导出',
    '实验室',
  ]
  let previous = -1
  for (const label of orderedLabels) {
    const current = html.indexOf(label)
    assert.ok(current > previous, `${label} should follow the prior route`)
    previous = current
  }
  assert.match(html, /OPT-IN/)
  assert.doesNotMatch(html, /Tick 调度 · 实验/)
})

test('new novel dialog is a five-step author-production wizard', async () => {
  const html = await render('/src/dashboard/modals/NewNovelModal.jsx', {})
  for (const step of ['故事', '篇幅', '风格', '模型', '确认']) {
    assert.match(html, new RegExp(step))
  }
  assert.match(html, /原始 seed/)
  assert.match(html, /NEW AUTHOR PROJECT/)
  assert.doesNotMatch(html, /aria-checked=/)
  assert.doesNotMatch(html, /启用世界模拟/)
})

test('hash routing keeps production as default and legacy diagnostics in lab', async () => {
  const {
    hashForView,
    mainNavigationView,
    normalizeView,
    viewFromHash,
  } = await load('/src/dashboard/routing.js')
  assert.equal(viewFromHash(''), 'production')
  assert.equal(viewFromHash('#/outline'), 'blueprint')
  assert.equal(viewFromHash('#/bible'), 'blueprint')
  assert.equal(viewFromHash('#/blueprint'), 'blueprint')
  assert.equal(normalizeView('author'), 'production')
  assert.equal(normalizeView('tick'), 'lab-tick')
  assert.equal(mainNavigationView('lab-agent'), 'lab')
  assert.equal(hashForView('styles'), '#/styles')
  assert.equal(viewFromHash('#/unknown'), 'production')
})

test('wizard persists the exact seed before planning the book outline', async () => {
  let savedBible
  let savedSpec
  let activatedStyle
  let createdResult
  const api = {
    getUserLLMConfigSummary: () => ({}),
    setUserLLMConfig() {},
    fetchPresets: async () => ({
      styles: [{ key: 'restrained', label: '克制现实主义' }],
    }),
    fetchLLMProviders: async () => ({
      providers: [{
        provider: 'custom',
        label: 'Custom',
        default_base_url: 'https://gateway.example/v1',
        default_model: 'writer-v1',
      }],
    }),
    fetchLLMRuntime: async () => ({
      provider: 'custom',
      model: 'writer-v1',
      credential_present: true,
      key_fingerprint: 'sk-…42',
    }),
    probeLLMConfig: async () => ({ success: true }),
    createNovel: async () => ({ id: 'novel-1' }),
    fetchStoryBible: async () => ({
      story_bible: {
        revision: 0,
        style_contract: {},
        immutable_world_rules: [],
        forbidden_deviations: [],
        protagonist_contracts: [],
        main_conflicts: [],
      },
    }),
    saveStoryBible: async (_id, payload) => {
      savedBible = payload
      return { story_bible: { ...payload, revision: 1 } }
    },
    createStyleProfile: async () => {
      throw new Error('built-in style must not create a custom profile')
    },
    saveProductionSpec: async (_id, payload) => {
      savedSpec = payload
      return { production_spec: { ...payload, revision: 1 } }
    },
    fetchStyleProfiles: async () => ({
      profiles: {},
      active_style: {
        revision: 4,
        style_profile_id: 'preset_literary',
      },
    }),
    activateStyleProfile: async (novelId, styleId, payload) => {
      activatedStyle = { novelId, styleId, payload }
      return {
        active_style: {
          revision: 5,
          style_profile_id: styleId,
          applies_from_chapter_ordinal: 1,
        },
        production_spec: { ...savedSpec, revision: 2 },
      }
    },
    generateBookOutline: async () => ({
      book_outline: { revision: 1, volumes: [], chapters: [] },
    }),
  }
  const renderer = await mount('/src/dashboard/modals/NewNovelModal.jsx', {
    api,
    notify() {},
    onCreated: (...args) => { createdResult = args },
    onClose() {},
  })

  await change(findLabeledControl(renderer, '小说名'), '潮汐尽头的灯')
  await change(findLabeledControl(renderer, '一句话设想'), '守灯人发现旧信。')
  await change(findLabeledControl(renderer, '题材'), '现实主义悬疑')
  await change(findLabeledControl(renderer, '主题'), '记忆与责任')
  await change(findLabeledControl(renderer, '原始 seed'), exactSeed)
  await click(findButton(renderer, '继续'))
  await click(findButton(renderer, '继续'))
  await click(findButton(renderer, '继续'))
  assert.match(snapshotText(renderer), /writer-v1/)
  await click(findButton(renderer, '继续'))
  await click(findButton(renderer, '创建作品并生成大纲'))

  assert.equal(savedBible.source_seed, exactSeed)
  assert.equal(savedBible.expected_revision, 0)
  assert.equal(savedSpec.target_total_chars, 300000)
  assert.equal(savedSpec.accepted_chapter_min_chars, 2800)
  assert.equal(savedSpec.accepted_chapter_max_chars, 3900)
  assert.deepEqual(activatedStyle, {
    novelId: 'novel-1',
    styleId: 'preset_literary',
    payload: {
      expected_revision: 4,
      expected_spec_revision: 1,
    },
  })
  assert.equal(createdResult[0], 'novel-1')
  assert.equal(createdResult[1], 'author')
  renderer.unmount()
})

test('provider catalog is normalized only from backend descriptors', async () => {
  const {
    normalizeProviderCatalog,
    providerDraftFrom,
  } = await load('/src/dashboard/components/ProviderConfigPanel.jsx')
  const providers = normalizeProviderCatalog({
    providers: [
      {
        provider: 'alpha',
        label: 'Alpha Gateway',
        default_base_url: 'https://alpha.example/v1',
        default_model: 'alpha-writer',
      },
      {
        provider: 'beta',
        label: 'Beta Gateway',
        default_base_url: 'https://beta.example/v1',
        default_model: 'beta-writer',
      },
    ],
  })
  assert.deepEqual(providers.map((item) => item.key), ['alpha', 'beta'])
  assert.equal(providers[0].defaultModel, 'alpha-writer')
  assert.equal(
    providerDraftFrom({ runtime: { provider: 'beta' }, providers }).model,
    'beta-writer',
  )
  const serverFallback = providerDraftFrom({
    runtime: {
      provider: 'beta',
      model: 'beta-runtime-writer',
      credential_present: true,
      thinking_mode: 'disabled',
    },
    local: {
      provider: 'alpha',
      model: 'stale-local-model',
      credential_present: false,
    },
    providers,
  })
  assert.equal(serverFallback.provider, 'beta')
  assert.equal(serverFallback.model, 'beta-runtime-writer')
  assert.equal(serverFallback.base_url, '')
  assert.equal(serverFallback.credential_present, true)
  assert.deepEqual(normalizeProviderCatalog({ providers: null }), [])
})

test('production controls follow persisted job state and SSE commits', async () => {
  const {
    applyProductionEvent,
    deriveProductionActions,
    formatLatency,
    isProductionReadyOutline,
    productionFailureCopy,
    productionRepairTotal,
    productionTokenTotal,
    safeTransaction,
    statusLabel,
  } = await load('/src/dashboard/views/ProductionCenterView.jsx')
  assert.deepEqual(deriveProductionActions({ status: 'draft' }, true), {
    start: true,
    pause: false,
    resume: false,
    cancel: false,
    retry: false,
  })
  assert.equal(deriveProductionActions({ status: 'running' }, true).start, false)
  assert.equal(deriveProductionActions({ status: 'running' }, true).pause, true)
  assert.equal(deriveProductionActions({ status: 'pausing' }, true).start, false)
  assert.equal(deriveProductionActions({ status: 'pausing' }, true).cancel, true)
  assert.equal(deriveProductionActions({ status: 'paused' }, true).resume, true)
  assert.equal(deriveProductionActions({ status: 'failed' }, true).resume, false)
  assert.equal(deriveProductionActions({ status: 'cancelling' }, true).start, false)
  assert.equal(deriveProductionActions({ status: 'cancelling' }, true).cancel, false)
  assert.equal(statusLabel('pausing'), '将在安全边界暂停')
  assert.equal(statusLabel('cancelling'), '正在安全取消')
  assert.equal(
    isProductionReadyOutline({ status: 'ready', chapters: [{}] }),
    true,
  )
  assert.equal(
    isProductionReadyOutline({ status: 'locked', chapters: [{}] }),
    true,
  )
  assert.equal(
    isProductionReadyOutline({ status: 'draft', chapters: [{}] }),
    false,
  )
  assert.equal(
    productionFailureCopy('PROVIDER_RATE_LIMITED').title,
    'Provider 请求受限',
  )
  assert.equal(
    productionFailureCopy('PROVIDER_OUTPUT_INVALID').title,
    'Provider 输出无法解析',
  )
  assert.equal(
    deriveProductionActions({
      status: 'failed',
      failed_chapter_id: 'chapter-7',
    }, true).retry,
    true,
  )
  assert.equal(
    deriveProductionActions({
      status: 'failed',
      failed_chapter_id: 'chapter-7',
    }, true).start,
    false,
  )
  const committed = applyProductionEvent(
    { completed_chapters: 3, status: 'running' },
    { type: 'chapter_committed', data: { transaction_id: 'tx-4' } },
  )
  assert.equal(committed.completed_chapters, 4)
  assert.equal(committed.transaction_id, 'tx-4')
  assert.equal(
    applyProductionEvent(
      { status: 'running' },
      { type: 'pausing', data: {} },
    ).status,
    'pausing',
  )
  const persistedJob = {
    prompt_tokens_total: 120,
    completion_tokens_total: 80,
    latency_total_ms: 2500,
    repair_total: 3,
    active_transaction_id: 'tx-live',
  }
  assert.equal(productionTokenTotal(persistedJob), 200)
  assert.equal(productionRepairTotal(persistedJob), 3)
  assert.equal(formatLatency(persistedJob), '2.50s total')
  assert.equal(safeTransaction(persistedJob).transaction_id, 'tx-live')
})

test('production starts an SSE subscription only after the first job exists', async () => {
  let jobExists = false
  let streamAborts = 0
  const streamCalls = []
  const job = { id: 'job-1', revision: 1, status: 'queued' }
  const api = {
    fetchProductionSpec: async () => ({
      production_spec: { revision: 1, target_total_chars: 3_000 },
    }),
    fetchBookOutline: async () => ({
      book_outline: {
        revision: 2,
        status: 'ready',
        chapters: [{ id: 'chapter-1' }],
      },
    }),
    fetchProductionStatus: async () => {
      if (!jobExists) {
        const error = new Error('no production job')
        error.status = 404
        throw error
      }
      return { job }
    },
    fetchLLMRuntime: async () => ({
      provider: 'custom',
      credential_present: true,
    }),
    startProduction: async () => {
      jobExists = true
      return { job }
    },
    watchProductionEvents: (novelId, options) => {
      streamCalls.push({ novelId, jobId: options.jobId })
      options.onOpen?.()
      return { abort: () => { streamAborts += 1 } }
    },
  }
  const renderer = await mount(
    '/src/dashboard/views/ProductionCenterView.jsx',
    { novel: { id: 'novel-1' }, api, notify() {} },
  )
  assert.equal(streamCalls.length, 0)
  await click(findButton(renderer, '开始生产'))
  assert.deepEqual(streamCalls, [{ novelId: 'novel-1', jobId: 'job-1' }])
  assert.match(snapshotText(renderer), /LIVE EVENTS/)
  await act(async () => {
    renderer.unmount()
    await flush()
  })
  assert.equal(streamAborts, 1)
})

test('production renders the durable failure reason with code-specific copy', async () => {
  const api = {
    fetchProductionSpec: async () => ({
      production_spec: { revision: 1, target_total_chars: 3_000 },
    }),
    fetchBookOutline: async () => ({
      book_outline: {
        revision: 2,
        status: 'ready',
        chapters: [{ id: 'chapter-1' }],
      },
    }),
    fetchProductionStatus: async () => ({
      job: {
        id: 'job-failed',
        revision: 4,
        status: 'failed',
        failed_chapter_id: 'chapter-1',
        failure_code: 'PROVIDER_OUTPUT_INVALID',
        failure_message: '结构化输出在一次修复后仍未通过。',
      },
    }),
    fetchLLMRuntime: async () => ({
      provider: 'custom',
      credential_present: true,
    }),
    watchProductionEvents: () => ({ abort() {} }),
  }
  const renderer = await mount(
    '/src/dashboard/views/ProductionCenterView.jsx',
    { novel: { id: 'novel-1' }, api, notify() {} },
  )
  const snapshot = snapshotText(renderer)
  assert.match(snapshot, /Provider 输出无法解析/)
  assert.match(snapshot, /结构化输出在一次修复后仍未通过/)
  assert.doesNotMatch(snapshot, /模型服务认证失败/)
  renderer.unmount()
})

test('committed chapter filter excludes every non-final transaction state', async () => {
  const {
    chapterContent,
    chapterMetadata,
    isCommittedChapter,
    isCommittedSection,
  } = await load(
    '/src/dashboard/views/CommittedChaptersView.jsx',
  )
  assert.equal(isCommittedChapter({ status: 'committed' }), true)
  assert.equal(isCommittedChapter({ committed: true }), true)
  for (const status of [
    'generating',
    'rejected',
    'failed',
    'staged',
    'candidate',
    'validating',
    'pausing',
    'cancelling',
  ]) {
    assert.equal(isCommittedChapter({ status }), false)
  }
  assert.equal(isCommittedChapter({}), false)
  assert.equal(isCommittedChapter({ status: 'committed', committed: false }), false)
  const committedSection = {
    content: '正式正文',
    transaction_id: 'tx-1',
    validation_passed: true,
    committed_at: '2026-07-30T00:00:00Z',
  }
  assert.equal(isCommittedSection(committedSection), true)
  assert.equal(isCommittedSection({ content: '候选正文' }), false)
  assert.equal(
    chapterContent({
      sections: [
        committedSection,
        { status: 'rejected', content: '不得展示的正文' },
        { content: '无提交证据的正文' },
      ],
    }),
    '正式正文',
  )
  assert.deepEqual(
    chapterMetadata({
      transaction_ids: ['tx-1', 'tx-2'],
      story_bible_revision_start: 4,
      story_bible_revision_end: 5,
      canonical_revision_start: 8,
      canonical_revision_end: 10,
      repair_total: 1,
    }),
    {
      transactionIds: ['tx-1', 'tx-2'],
      transactionLabel: '2 个 · tx-2',
      storyBibleRevision: '4→5',
      canonicalRevision: '8→10',
      repairPerformed: true,
    },
  )
})

test('Provider 401 preserves login while structured and legacy JWT 401 expire it', async () => {
  const api = await load('/src/services/api.js')
  const previousFetch = globalThis.fetch
  const previousStorage = globalThis.localStorage
  const previousCustomEvent = globalThis.CustomEvent
  const storage = new Map()
  let expiredEvents = 0
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key),
  }
  globalThis.CustomEvent = class CustomEvent {
    constructor(type) { this.type = type }
  }
  globalThis.window.dispatchEvent = (event) => {
    if (event.type === 'auth:expired') expiredEvents += 1
  }
  try {
    api.setStoredToken('app-session')
    globalThis.fetch = async () => new Response(JSON.stringify({
      detail: {
        code: 'PROVIDER_AUTH_FAILED',
        message: 'upstream rejected key',
      },
    }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    })
    await api.authedFetch('/api/config/llm/probe')
    assert.equal(api.getStoredToken(), 'app-session')
    assert.equal(expiredEvents, 0)

    globalThis.fetch = async () => new Response(JSON.stringify({
      detail: 'upstream provider rejected credentials',
    }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    })
    await api.authedFetch('/api/config/llm/probe')
    assert.equal(api.getStoredToken(), 'app-session')
    assert.equal(expiredEvents, 0)

    globalThis.fetch = async () => new Response(JSON.stringify({
      detail: '登录态无效或已过期',
    }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    })
    await api.authedFetch('/api/novels')
    assert.equal(api.getStoredToken(), '')
    assert.equal(expiredEvents, 1)

    api.setStoredToken('renewed-app-session')
    globalThis.fetch = async () => new Response(JSON.stringify({
      detail: {
        code: 'AUTH_TOKEN_EXPIRED',
        message: 'session expired',
      },
    }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    })
    await api.authedFetch('/api/novels')
    assert.equal(api.getStoredToken(), '')
    assert.equal(expiredEvents, 2)
  } finally {
    api.clearUserLLMConfig()
    globalThis.fetch = previousFetch
    globalThis.localStorage = previousStorage
    globalThis.CustomEvent = previousCustomEvent
    globalThis.window.dispatchEvent = () => {}
  }
})

test('LLM credentials attach only to model-call routes', async () => {
  const api = await load('/src/services/api.js')
  const previousFetch = globalThis.fetch
  const captures = []
  try {
    api.setUserLLMConfig({
      provider: 'custom',
      model: 'writer-v1',
      base_url: 'https://gateway.example/v1',
      api_key: 'secret-key',
      thinking_mode: 'enabled',
      timeout: 120,
      max_retries: 2,
    }, { remember: false })
    globalThis.fetch = async (path, init) => {
      captures.push({ path, headers: init.headers })
      return new Response('{}', {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    await api.authedFetch('/api/novels')
    await api.authedFetch('/api/novels/n1/outline/generate', {
      method: 'POST',
      body: '{}',
    })
    assert.equal(captures[0].headers.get('X-User-LLM-Key'), null)
    assert.equal(captures[1].headers.get('X-User-LLM-Key'), 'secret-key')
    assert.equal(captures[1].headers.get('X-User-LLM-Provider'), 'custom')
    assert.equal(captures[1].headers.get('X-User-LLM-Thinking-Mode'), 'enabled')
    assert.equal(captures[1].headers.get('X-User-LLM-Max-Retries'), '2')
  } finally {
    api.clearUserLLMConfig()
    globalThis.fetch = previousFetch
  }
})

test('provider identity changes clear prior credentials and require re-entry', async () => {
  const api = await load('/src/services/api.js')
  const previousFetch = globalThis.fetch
  const captures = []
  try {
    api.clearUserLLMConfig()
    api.setUserLLMConfig({
      provider: 'alpha',
      base_url: 'https://alpha.invalid/v1',
      model: 'alpha-model',
      api_key: 'test-credential-alpha',
    }, { remember: false })
    api.setUserLLMConfig({
      provider: 'beta',
      base_url: 'https://beta.invalid/v1',
      model: 'beta-model',
      api_key: '',
    }, { remember: false })
    assert.equal(api.getUserLLMConfig().api_key, '')

    globalThis.fetch = async (_path, init) => {
      captures.push(init.headers)
      return new Response('{}', {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    await api.authedFetch('/api/novels/n1/outline/generate', {
      method: 'POST',
      body: '{}',
    })
    assert.equal(captures[0].get('X-User-LLM-Key'), null)
    for (const header of [
      'X-User-LLM-Provider',
      'X-User-LLM-Base-Url',
      'X-User-LLM-Model',
      'X-User-LLM-Thinking-Mode',
      'X-User-LLM-Timeout',
      'X-User-LLM-Max-Retries',
    ]) {
      assert.equal(captures[0].get(header), null)
    }
  } finally {
    api.clearUserLLMConfig()
    globalThis.fetch = previousFetch
  }

  const providers = [
    {
      key: 'alpha',
      label: 'Alpha',
      defaultBaseUrl: 'https://alpha.invalid/v1',
      defaultModel: 'alpha-model',
    },
    {
      key: 'beta',
      label: 'Beta',
      defaultBaseUrl: 'https://beta.invalid/v1',
      defaultModel: 'beta-model',
    },
  ]
  let changed
  const renderer = await mount(
    '/src/dashboard/components/ProviderConfigPanel.jsx',
    {
      providers,
      value: {
        provider: 'alpha',
        base_url: 'https://alpha.invalid/v1',
        model: 'alpha-model',
        api_key: '',
        thinking_mode: 'disabled',
        timeout: 600,
        max_retries: 0,
        credential_present: true,
        credential_required: false,
      },
      onChange: (value) => { changed = value },
      onProbe() {},
    },
  )
  await click(findButton(renderer, 'Beta'))
  assert.equal(changed.provider, 'beta')
  assert.equal(changed.api_key, '')
  assert.equal(changed.credential_required, true)
  renderer.unmount()
})

test('empty-key model calls and probes use the server Provider fallback', async () => {
  const api = await load('/src/services/api.js')
  const previousFetch = globalThis.fetch
  const captures = []
  try {
    api.clearUserLLMConfig()
    api.setUserLLMConfig({
      provider: 'custom',
      base_url: 'https://browser-draft.invalid/v1',
      model: 'browser-draft-model',
      api_key: '',
      thinking_mode: 'enabled',
      timeout: 120,
      max_retries: 2,
    }, { remember: false })
    globalThis.fetch = async (path, init) => {
      captures.push({ path, headers: init.headers })
      return new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    await api.authedFetch('/api/novels/n1/outline/generate', {
      method: 'POST',
      body: '{}',
    })
    api.setUserLLMConfig({
      provider: 'stale-browser-provider',
      model: 'stale-browser-model',
      api_key: 'stale-browser-key',
    }, { remember: false })
    await api.probeLLMConfig({
      provider: 'custom',
      model: 'another-browser-draft',
      api_key: '',
    })
    const providerHeaders = [
      'X-User-LLM-Key',
      'X-User-LLM-Provider',
      'X-User-LLM-Base-Url',
      'X-User-LLM-Model',
      'X-User-LLM-Thinking-Mode',
      'X-User-LLM-Timeout',
      'X-User-LLM-Max-Retries',
    ]
    assert.equal(captures.length, 2)
    for (const capture of captures) {
      for (const header of providerHeaders) {
        assert.equal(capture.headers.get(header), null)
      }
    }
  } finally {
    api.clearUserLLMConfig()
    globalThis.fetch = previousFetch
  }
})

test('style activation uses active binding revision from active_style response', async () => {
  const baseStyle = {
    revision: 1,
    description: '',
    read_only: false,
    prompt_hash: 'a'.repeat(64),
  }
  let activation
  const api = {
    fetchStyleProfiles: async () => ({
      profiles: {
        preset_literary: {
          ...baseStyle,
          id: 'preset_literary',
          name: '默认风格',
          read_only: true,
        },
        style_target: {
          ...baseStyle,
          id: 'style_target',
          name: '目标风格',
        },
      },
      active_style: {
        revision: 7,
        style_profile_id: 'preset_literary',
        applies_from_chapter_ordinal: 1,
      },
    }),
    fetchProductionSpec: async () => ({
      production_spec: { revision: 11 },
    }),
    fetchCommittedChapters: async () => ({ chapters: [] }),
    activateStyleProfile: async (novelId, styleId, payload) => {
      activation = { novelId, styleId, payload }
      return {
        active_style: {
          revision: 8,
          style_profile_id: styleId,
          applies_from_chapter_ordinal: 4,
        },
        production_spec: { revision: 12 },
      }
    },
  }
  const renderer = await mount('/src/dashboard/views/StyleStudioView.jsx', {
    novel: { id: 'novel-style' },
    api,
    notify() {},
  })
  await click(findButton(renderer, '目标风格'))
  await click(findButton(renderer, '应用到下一章'))
  assert.deepEqual(activation, {
    novelId: 'novel-style',
    styleId: 'style_target',
    payload: {
      expected_revision: 7,
      expected_spec_revision: 11,
    },
  })
  assert.match(snapshotText(renderer), /第 4 章/)
  renderer.unmount()
})

test('author authorities have safe empty states without a selected novel', async () => {
  const bible = await render('/src/dashboard/views/StoryBibleView.jsx', {})
  const state = await render('/src/dashboard/views/CanonicalStateView.jsx', {})
  const threads = await render('/src/dashboard/views/StoryThreadsView.jsx', {})
  const studio = await render('/src/dashboard/views/AuthorStudioView.jsx', {})
  for (const html of [bible, state, threads, studio]) {
    assert.match(html, /请先选择作品/)
  }
})

test('StoryBible loads, edits, and saves exact seed with revision', async () => {
  let saved
  const api = storyBibleApi({
    saveStoryBible: async (_novelId, payload) => {
      saved = payload
      return { story_bible: { ...storyBible, ...payload, revision: 3 } }
    },
  })
  const renderer = await mount('/src/dashboard/views/StoryBibleView.jsx', {
    novel: { id: 'n1' }, api, notify() {},
  })
  assert.match(snapshotText(renderer), /第一行  保留双空格/)
  await click(findButton(renderer, '编辑圣经'))
  const premise = renderer.root.findAllByType('textarea').find((node) => node.props.value === storyBible.premise)
  await change(premise, '守灯人拆开旧信并承担代价。')
  await click(findButton(renderer, '保存并提升 revision'))
  assert.equal(saved.expected_revision, 2)
  assert.equal(saved.source_seed, exactSeed)
  assert.equal(saved.premise, '守灯人拆开旧信并承担代价。')
  assert.match(nodeText(renderer.toJSON()), /REV 003/)
  renderer.unmount()
})

test('StoryBible exposes revision conflict and legacy inferred provenance', async () => {
  const legacyBible = {
    ...storyBible,
    migration: {
      needs_confirmation: true,
      source: 'legacy_inferred',
      inferred_fields: ['premise'],
      source_files: ['tick_state.json'],
    },
  }
  const api = storyBibleApi({
    fetchStoryBible: async () => ({ story_bible: legacyBible, migration: legacyBible.migration }),
    saveStoryBible: async () => {
      const error = new Error('conflict')
      error.code = 'REVISION_CONFLICT'
      throw error
    },
  })
  const renderer = await mount('/src/dashboard/views/StoryBibleView.jsx', {
    novel: { id: 'n1' }, api, notify() {},
  })
  assert.match(snapshotText(renderer), /由旧数据推断，需要确认/)
  await click(findButton(renderer, '编辑圣经'))
  await click(findButton(renderer, '保存并提升 revision'))
  assert.match(snapshotText(renderer), /另一个会话已更新创作圣经/)
  renderer.unmount()
})

test('experiment lab owns simulation opt-in and preserves author mode on failure', async () => {
  let switched
  const success = await mount('/src/dashboard/views/ExperimentLabView.jsx', {
    novel: { id: 'n1' },
    api: {
      fetchGenerationMode: async () => ({ mode: 'author', revision: 4 }),
      updateGenerationMode: async (_novelId, revision, mode) => {
        switched = { revision, mode }
        return { mode, revision: revision + 1 }
      },
    },
    notify() {},
  })
  await click(findButton(success, '启用世界模拟'))
  assert.deepEqual(switched, { revision: 4, mode: 'simulation' })
  assert.match(snapshotText(success), /SIMULATION LIVE/)
  success.unmount()

  const failed = await mount('/src/dashboard/views/ExperimentLabView.jsx', {
    novel: { id: 'n1' },
    api: {
      fetchGenerationMode: async () => ({ mode: 'author', revision: 4 }),
      updateGenerationMode: async () => { throw new Error('网络失败') },
    },
    notify() {},
  })
  await click(findButton(failed, '启用世界模拟'))
  assert.match(snapshotText(failed), /网络失败/)
  assert.match(snapshotText(failed), /AUTHOR PRODUCTION SAFE/)
  failed.unmount()
})

test('author goal submission polls transaction and displays global manifest budget', async () => {
  let submitted
  const api = authorApi({
    generateAuthorSection: async (_novelId, payload) => {
      submitted = payload
      return { id: 'task-1', status: 'queued' }
    },
  })
  const renderer = await mount('/src/dashboard/views/AuthorStudioView.jsx', {
    novel: { id: 'n1' }, api, notify() {},
  })
  const objective = renderer.root.findAllByType('textarea').find((node) => node.props.rows === 6)
  await change(objective, '让沈砚拆开旧信，并承受关系代价。')
  await click(findButton(renderer, '生成并验证下一节'))
  assert.equal(submitted.objective, '让沈砚拆开旧信，并承受关系代价。')
  assert.match(snapshotText(renderer), /正文与权威状态已提交|原子提交/)
  await click(findButton(renderer, '查看脱敏 Context Manifest'))
  const text = nodeText(renderer.toJSON())
  assert.match(text, /7200 \/ 24000 chars/)
  assert.match(text, /~3600 \/ 12000 tokens/)
  assert.match(text, /30%/)
  renderer.unmount()
})

test('author studio previews a folded narrative contract before generation', async () => {
  let previewPayload
  const api = authorApi({
    previewAuthorNarrativeContract: async (_novelId, payload) => {
      previewPayload = payload
      return authorApi().previewAuthorNarrativeContract()
    },
  })
  const renderer = await mount('/src/dashboard/views/AuthorStudioView.jsx', {
    novel: { id: 'n1' }, api, notify() {},
  })
  assert.doesNotMatch(snapshotText(renderer), /沈砚打开旧信/)
  await click(findButton(renderer, '查看本节正文契约'))
  const text = nodeText(renderer.toJSON())
  assert.equal(previewPayload.objective, storyBible.main_conflicts[0])
  assert.match(text, /必须发生/)
  assert.match(text, /执行顺序/)
  assert.match(text, /1\. 沈砚打开旧信/)
  assert.match(text, /沈砚打开旧信/)
  assert.match(text, /最终必须达到/)
  assert.match(text, /不得新增/)
  assert.match(text, /天亮前交信/)
  assert.match(text, /SectionBudget 分段/)
  assert.match(text, /opening · 约 180 字 · 最多 230 字/)
  assert.match(text, /停止条件/)
  assert.match(text, /服务端长度目标/)
  assert.match(text, /1000 字 · 接受区间 900—1100 字/)
  assert.doesNotMatch(text, /system prompt|user prompt|思考过程/i)
  renderer.unmount()
})

test('author studio surfaces validator rejection details', async () => {
  const api = authorApi({
    fetchAuthorSectionStatus: async () => ({
      task: { id: 'task-1', status: 'failed' },
      transaction: {
        id: 'tx-1',
        phase: 'rejected',
        repair_performed: true,
        validation_report: {
          accepted: false,
          severity: 'high',
          violations: [{
            code: 'DELTA_EVIDENCE_MISSING',
            path: '/characters/shen_yan/location',
            message: '状态变化缺少可定位正文证据',
          }],
        },
      },
    }),
  })
  const renderer = await mount('/src/dashboard/views/AuthorStudioView.jsx', {
    novel: { id: 'n1' }, api, notify() {},
  })
  await click(findButton(renderer, '生成并验证下一节'))
  const text = nodeText(renderer.toJSON())
  assert.match(text, /校验未通过/)
  assert.match(text, /DELTA_EVIDENCE_MISSING/)
  assert.match(text, /状态变化缺少可定位正文证据/)
  renderer.unmount()
})

test('author validation separates narrative state and style and shows repair result', async () => {
  const api = authorApi({
    fetchAuthorSectionStatus: async () => ({
      task: { id: 'task-1', status: 'failed' },
      transaction: {
        id: 'tx-1',
        phase: 'rejected',
        repair_performed: true,
        narrative_validation_history: [
          { accepted: false, violations: [] },
          { accepted: false, violations: [] },
        ],
        narrative_validation_report: {
          accepted: false,
          severity: 'high',
          contract_coverage: 0.75,
          missing_required_events: ['evt_handover'],
          event_results: [{ event_id: 'evt_handover', status: 'started', evidence: '沈砚准备交信' }],
          end_state_results: [{ id: 'holder', path: '/items/letter/holder', expected: 'lin_qiu', reached: false, violation_code: 'END_STATE_NOT_REACHED' }],
          violations: [{ code: 'END_STATE_NOT_REACHED', message: '信没有实际交付' }],
        },
        validation_report: {
          accepted: true,
          severity: 'medium',
          violations: [{ code: 'THREAD_ADVANCE_UNKNOWN', message: '故事线提案已移除' }],
          dropped_delta_count: 1,
          dropped_thread_change_count: 1,
        },
        event_execution_plan: {
          ordered_events: [{ id: 'evt_handover', order: 1, description: '沈砚完成交信' }],
        },
        repair_plan: {
          missing_events: [],
          incomplete_events: [{ event_id: 'evt_handover' }],
          wrong_actor_events: [],
          wrong_target_events: [],
          wrong_end_states: [{ state_id: 'holder' }],
          unsupported_additions: [],
          must_preserve_spans: [],
          must_preserve_facts: [],
        },
        repair_patches: {
          patches: [
            { patch_type: 'insert', patch_text: '沈砚完成交信。' },
          ],
        },
        repair_patch_report: {
          accepted: false,
          char_delta: 8,
          violations: [{ code: 'PATCH_END_STATE_EVIDENCE_INCOMPLETE' }],
        },
        repair_audit_codes: ['PATCH_END_STATE_EVIDENCE_INCOMPLETE'],
        initial_length_report: {
          phase: 'initial', chars: 720, target: 900, ratio: 0.8, accepted: false,
        },
        final_length_report: {
          phase: 'repaired', chars: 820, target: 900, ratio: 0.9111,
          accepted: false, violation_code: 'NARRATIVE_TOO_SHORT',
        },
        initial_ending_report: {
          phase: 'initial', accepted: false, post_resolution_chars: 80,
          violation_code: 'POST_RESOLUTION_EXPANSION',
        },
        final_ending_report: {
          phase: 'repaired', accepted: true, post_resolution_chars: 10,
          violation_code: '',
        },
        final_balance_report: {
          phase: 'repaired', event_pass: false, end_state_pass: false,
          length_pass: false, ending_pass: true, accepted: false,
        },
        style_validation_report: {
          evaluated: true,
          passed: true,
          findings: [],
        },
      },
    }),
  })
  const renderer = await mount('/src/dashboard/views/AuthorStudioView.jsx', {
    novel: { id: 'n1' }, api, notify() {},
  })
  await click(findButton(renderer, '生成并验证下一节'))
  const text = nodeText(renderer.toJSON())
  assert.match(text, /正文契约/)
  assert.match(text, /事件完成状态/)
  assert.match(text, /started/)
  assert.match(text, /最终状态/)
  assert.match(text, /状态变更/)
  assert.match(text, /故事线提案/)
  assert.match(text, /RepairPlan 摘要/)
  assert.match(text, /PATCH MODE/)
  assert.match(text, /PATCH BLOCKED1 local patch/)
  assert.match(text, /PATCH_END_STATE_EVIDENCE_INCOMPLETE/)
  assert.match(text, /DROPPED1/)
  assert.match(text, /风格检查/)
  assert.match(text, /evt_handover/)
  assert.match(text, /END_STATE_NOT_REACHED/)
  assert.match(text, /修复前 未通过 → 修复后 未通过/)
  assert.match(text, /INITIAL720\/900 字 · ratio 0\.8/)
  assert.match(text, /REPAIRED820\/900 字 · ratio 0\.9111 · NARRATIVE_TOO_SHORT/)
  assert.match(text, /Ending Gate/)
  assert.match(text, /联合门禁/)
  assert.match(text, /Event FAIL · EndState FAIL · Length FAIL · Ending PASS/)
  renderer.unmount()
})

test('author diagnostics show budget warning and long-run status', async () => {
  const api = authorApi({
    fetchContextManifest: async () => ({
      total_chars: 21600,
      max_context_chars: 24000,
      total_token_estimate: 10800,
      max_context_token_estimate: 12000,
      budget_utilization: 0.9,
      rejected_reason: '',
      slots: [{ name: 'narrative_contract', char_count: 3000, token_estimate: 1500, truncated: false }],
    }),
  })
  const renderer = await mount('/src/dashboard/views/AuthorStudioView.jsx', {
    novel: { id: 'n1' }, api, notify() {},
  })
  await click(findButton(renderer, '生成并验证下一节'))
  await click(findButton(renderer, '查看脱敏 Context Manifest'))
  const text = nodeText(renderer.toJSON())
  assert.match(text, /Context 已使用 90%/)
  assert.match(text, /LONG-RUN STATUS/)
  assert.match(text, /已完成章节/)
  assert.match(text, /合同通过率/)
  assert.match(text, /重启恢复/)
  assert.match(text, /run-1/)
  renderer.unmount()
})

test('test_frontend_displays_stale_context_message', async () => {
  const api = authorApi({
    fetchAuthorSectionStatus: async () => ({
      task: { id: 'task-1', status: 'failed', committed: false },
      transaction: {
        id: 'tx-1',
        phase: 'stale_context',
        committed: false,
        error_code: 'STORY_BIBLE_REVISION_STALE',
      },
    }),
  })
  const renderer = await mount('/src/dashboard/views/AuthorStudioView.jsx', {
    novel: { id: 'n1' }, api, notify() {},
  })
  await click(findButton(renderer, '生成并验证下一节'))
  const text = snapshotText(renderer)
  assert.match(text, /创作圣经在生成期间发生了变化/)
  assert.match(text, /本次候选基于旧版本，未提交/)
  renderer.unmount()
})

test('author evidence ledger shows revisions, memory, threads, receipts, recovery and exports', async () => {
  let recoveryCalls = 0
  let manuscriptExports = 0
  let evidenceExports = 0
  const api = authorApi({
    fetchAuthorTransactions: async () => ({
      total: 1,
      transactions: [{
        id: 'tx-rejected-1',
        phase: 'rejected',
        story_bible_revision: 2,
        canonical_state_revision: 3,
        target_canonical_revision: 4,
        writer_calls: 1,
        planner_calls: 0,
        repair_performed: true,
        initial_preflight_report: { accepted: false },
        final_preflight_report: { accepted: false },
        repair_patch_report: { char_delta: 18 },
        usage: { total_tokens: 456 },
        error_code: 'END_STATE_NOT_REACHED',
        error: '最终状态未达到，事务未提交',
        created_at: '2026-07-28T00:00:00Z',
        updated_at: '2026-07-28T00:00:02.500Z',
      }],
    }),
    resumeAuthorRecovery: async () => {
      recoveryCalls += 1
      return {
        status: 'recovered',
        pending_before: ['tx-pending'],
        recovered_transaction_ids: ['tx-pending'],
        pending_after: [],
      }
    },
    downloadAuthorManuscript: async () => {
      manuscriptExports += 1
      return { blob: null, filename: 'novel.md', sha256: 'a'.repeat(64) }
    },
    downloadAuthorEvidence: async () => {
      evidenceExports += 1
      return { blob: null, filename: 'evidence.json', sha256: 'b'.repeat(64) }
    },
  })
  const renderer = await mount('/src/dashboard/views/AuthorStudioView.jsx', {
    novel: { id: 'n1' }, api, notify() {},
  })
  const initial = nodeText(renderer.toJSON())
  assert.match(initial, /EVIDENCE LEDGER/)
  assert.match(initial, /MEMORY LEDGERR5/)
  assert.match(initial, /abc1234567…/)
  assert.match(initial, /沈砚承诺在天亮前交付旧信/)
  assert.match(initial, /调查港难/)
  assert.match(initial, /tx-rejected-1/)
  assert.match(initial, /INITIAL FAIL/)
  assert.match(initial, /REPAIR Δ18/)
  assert.match(initial, /FINAL FAIL/)
  assert.match(initial, /456 tokens/)
  assert.match(initial, /END_STATE_NOT_REACHED/)

  await click(findButton(renderer, '恢复待提交事务'))
  assert.equal(recoveryCalls, 1)
  assert.match(nodeText(renderer.toJSON()), /RECOVERED恢复 1 · 尚待处理 0/)

  await click(findButton(renderer, '导出正式稿件'))
  await click(findButton(renderer, '导出审计证据'))
  assert.equal(manuscriptExports, 1)
  assert.equal(evidenceExports, 1)
  renderer.unmount()
})

test('author export failure is visible and leaves the studio recoverable', async () => {
  const api = authorApi({
    downloadAuthorEvidence: async () => {
      throw new Error('证据导出暂时不可用')
    },
  })
  const renderer = await mount('/src/dashboard/views/AuthorStudioView.jsx', {
    novel: { id: 'n1' }, api, notify() {},
  })
  await click(findButton(renderer, '导出审计证据'))
  const text = snapshotText(renderer)
  assert.match(text, /证据导出暂时不可用/)
  assert.match(text, /恢复待提交事务/)
  renderer.unmount()
})

test('canonical state UI shows characters, item ownership, and knowledge boundaries', async () => {
  const api = {
    fetchCanonicalState: async () => ({ canonical_state: canonicalState, migration: {} }),
    fetchStoryThreads: async () => ({ threads: {} }),
  }
  const renderer = await mount('/src/dashboard/views/CanonicalStateView.jsx', {
    novel: { id: 'n1' }, api,
  })
  const text = snapshotText(renderer)
  assert.match(text, /沈砚/)
  assert.match(text, /旧信/)
  assert.match(text, /旧信与港难有关/)
  assert.match(text, /读者已知边界/)
  renderer.unmount()
})

test('Shell tick polling gate keeps author and simulation runtimes isolated', async () => {
  const { shouldFetchTickStatus } = await load('/src/dashboard/Shell.jsx')
  assert.equal(shouldFetchTickStatus('author'), false)
  assert.equal(shouldFetchTickStatus('simulation'), true)
  assert.equal(shouldFetchTickStatus('author', true), true)
})
