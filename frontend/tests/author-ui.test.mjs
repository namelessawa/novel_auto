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
      total_chars: 7200,
      max_context_chars: 24000,
      total_token_estimate: 3600,
      max_context_token_estimate: 12000,
      budget_utilization: 0.3,
      rejected_reason: '',
      slots: [{ name: 'story_bible', char_count: 1200, token_estimate: 600, truncated: false }],
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

test('sidebar presents author workflow before experimental diagnostics', async () => {
  const html = await render('/src/dashboard/Sidebar.jsx', {
    novels: [],
    activeNovelId: null,
    view: 'author',
    tasks: [],
  })
  assert.ok(html.indexOf('章节创作') < html.indexOf('Tick 调度 · 实验'))
  assert.match(html, /创作圣经/)
  assert.match(html, /当前故事状态/)
  assert.match(html, /知识图谱 · 派生/)
})

test('new novel dialog defaults to author mode and labels simulation experimental', async () => {
  const html = await render('/src/dashboard/modals/NewNovelModal.jsx', {})
  assert.match(html, /aria-checked="true"/)
  assert.match(html, /作者模式/)
  assert.match(html, /EXPERIMENTAL/)
  assert.match(html, /世界模拟/)
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

test('author mode switch succeeds, while failed switch preserves current mode', async () => {
  let switched
  const success = await mount('/src/dashboard/views/AuthorStudioView.jsx', {
    novel: { id: 'n1' },
    api: authorApi({
      updateGenerationMode: async (_novelId, revision, mode) => {
        switched = { revision, mode }
        return { mode, revision: revision + 1 }
      },
    }),
    notify() {},
  })
  await click(findButton(success, '世界模拟模式'))
  assert.deepEqual(switched, { revision: 4, mode: 'simulation' })
  assert.match(snapshotText(success), /当前作品由世界模拟推进/)
  success.unmount()

  const failed = await mount('/src/dashboard/views/AuthorStudioView.jsx', {
    novel: { id: 'n1' },
    api: authorApi({ updateGenerationMode: async () => { throw new Error('网络失败') } }),
    notify() {},
  })
  await click(findButton(failed, '世界模拟模式'))
  assert.match(snapshotText(failed), /网络失败/)
  assert.match(snapshotText(failed), /这一节必须完成什么/)
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
