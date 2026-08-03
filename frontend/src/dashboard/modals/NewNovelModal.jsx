import React, { useEffect, useMemo, useState } from 'react'
import {
  activateStyleProfile,
  createNovel,
  createStyleProfile,
  fetchLLMProviders,
  fetchLLMRuntime,
  fetchPresets,
  fetchProductionSpec,
  fetchStoryBible,
  fetchStyleProfiles,
  generateBookOutline,
  getUserLLMConfigSummary,
  probeLLMConfig,
  saveProductionSpec,
  saveStoryBible,
  setUserLLMConfig,
} from '../../services/api'
import ProviderConfigPanel, {
  normalizeProviderCatalog,
  providerDraftFrom,
} from '../components/ProviderConfigPanel'
import { InlineNotice } from '../components/AsyncState'
import { showToast } from '../../utils/toast'

const STEPS = ['故事', '篇幅', '风格', '模型', '确认']
const LENGTH_PRESETS = [
  { label: '短篇', chars: 20000, volumes: 1, chapters: 8 },
  { label: '中篇', chars: 80000, volumes: 2, chapters: 24 },
  { label: '长篇', chars: 300000, volumes: 4, chapters: 90 },
  { label: '超长篇', chars: 1000000, volumes: 10, chapters: 280 },
]

const DEFAULT_API = {
  activateStyleProfile,
  createNovel,
  createStyleProfile,
  fetchLLMProviders,
  fetchLLMRuntime,
  fetchPresets,
  fetchProductionSpec,
  fetchStoryBible,
  fetchStyleProfiles,
  generateBookOutline,
  getUserLLMConfigSummary,
  probeLLMConfig,
  saveProductionSpec,
  saveStoryBible,
  setUserLLMConfig,
}

function initialDraft() {
  return {
    story: {
      title: '',
      premise: '',
      genre: '',
      theme: '',
      central_question: '',
      ending_direction: '',
      source_seed: '',
    },
    length: {
      target_total_chars: 300000,
      volume_count: 4,
      chapter_count: 90,
      target_chapter_chars: 3300,
      section_target_chars: 1100,
      accepted_chapter_min_chars: 2800,
      accepted_chapter_max_chars: 3900,
      generation_language: 'zh-CN',
    },
    style: {
      custom: false,
      base_preset_key: 'literary',
      style_profile_id: 'preset_literary',
      name: '文学叙事',
      description: '',
      narrative_voice: '第三人称限知',
      viewpoint: '单一视角',
      tense: '过去时',
      sentence_length_tendency: '中等',
      paragraph_density: '适中',
      dialogue_ratio: 35,
      description_ratio: 35,
      pacing: '张弛交替',
      emotional_intensity: 4,
      humor_level: 1,
      imagery_preference: '',
      vocabulary_preference: '',
      rhythm_instructions: '',
      chapter_opening_preference: '',
      chapter_ending_preference: '',
      must_do_rules: '',
      forbidden_rules: '',
      avoided_phrases: '',
      user_sample: '',
    },
  }
}

export default function NewNovelModal({
  onClose,
  onCreated,
  api = DEFAULT_API,
  notify = showToast,
}) {
  const [step, setStep] = useState(0)
  const [draft, setDraft] = useState(initialDraft)
  const [presets, setPresets] = useState([])
  const [providers, setProviders] = useState([])
  const [runtime, setRuntime] = useState(null)
  const [providerDraft, setProviderDraft] = useState(() =>
    providerDraftFrom({ local: api.getUserLLMConfigSummary?.() || {} }),
  )
  const [persistence, setPersistence] = useState('session')
  const [providerLoading, setProviderLoading] = useState(true)
  const [providerError, setProviderError] = useState('')
  const [probe, setProbe] = useState(null)
  const [probeBusy, setProbeBusy] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    Promise.allSettled([
      api.fetchPresets(),
      api.fetchLLMProviders(),
      api.fetchLLMRuntime(),
    ]).then(([presetResult, providerResult, runtimeResult]) => {
      if (cancelled) return
      if (presetResult.status === 'fulfilled') {
        const rows =
          presetResult.value?.styles ||
          presetResult.value?.presets ||
          []
        setPresets(Array.isArray(rows) ? rows : [])
      }
      const catalog = providerResult.status === 'fulfilled'
        ? normalizeProviderCatalog(providerResult.value)
        : []
      const nextRuntime = runtimeResult.status === 'fulfilled'
        ? runtimeResult.value
        : null
      setProviders(catalog)
      setRuntime(nextRuntime)
      setProviderDraft(providerDraftFrom({
        runtime: nextRuntime || {},
        local: api.getUserLLMConfigSummary?.() || {},
        providers: catalog,
      }))
      if (providerResult.status === 'rejected') {
        setProviderError(
          providerResult.reason?.message || 'Provider catalog 读取失败',
        )
      }
      setProviderLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [api])

  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === 'Escape' && !busy) onClose?.()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [busy, onClose])

  const estimate = useMemo(() => {
    const total = Number(draft.length.target_total_chars || 0)
    const chapters = Math.max(1, Number(draft.length.chapter_count || 1))
    const perChapter = Math.round(total / chapters)
    const sections = Math.max(
      1,
      Math.ceil(perChapter / Number(draft.length.section_target_chars || 1)),
    )
    return { perChapter, sections, totalSections: sections * chapters }
  }, [draft.length])

  function updateDomain(domain, patch) {
    setDraft((current) => ({
      ...current,
      [domain]: { ...current[domain], ...patch },
    }))
    setError('')
  }

  function validateCurrentStep() {
    if (step === 0) {
      if (!draft.story.title.trim()) return '请填写小说名。'
      if (!draft.story.premise.trim()) return '请写下一句话故事设想。'
      if (!draft.story.genre.trim()) return '请填写题材。'
      if (!draft.story.theme.trim()) return '请填写主题。'
    }
    if (step === 1) {
      const length = draft.length
      if (Number(length.target_total_chars) < 1000) return '目标总字数至少为 1,000。'
      if (Number(length.volume_count) < 1) return '卷数至少为 1。'
      if (Number(length.chapter_count) < 1) return '章节数至少为 1。'
      if (Number(length.target_chapter_chars) < 500) return '单章目标字数至少为 500。'
      if (Number(length.volume_count) > Number(length.chapter_count)) {
        return '卷数不能超过章节数。'
      }
      if (
        Number(length.accepted_chapter_min_chars) >
        Number(length.target_chapter_chars)
      ) {
        return '单章下限不能超过单章目标字数。'
      }
      if (
        Number(length.target_chapter_chars) >
        Number(length.accepted_chapter_max_chars)
      ) {
        return '单章目标字数不能超过单章上限。'
      }
      if (
        Number(length.section_target_chars) >
        Number(length.accepted_chapter_max_chars)
      ) {
        return '单节目标字数不能超过单章上限。'
      }
      const plannedMinimum =
        Number(length.chapter_count) *
        Number(length.accepted_chapter_min_chars)
      const plannedMaximum =
        Number(length.chapter_count) *
        Number(length.accepted_chapter_max_chars)
      if (
        Number(length.target_total_chars) < plannedMinimum ||
        Number(length.target_total_chars) > plannedMaximum
      ) {
        return `总字数需落在当前章数的可接受区间 ${plannedMinimum.toLocaleString()}–${plannedMaximum.toLocaleString()}。`
      }
    }
    if (step === 2 && draft.style.custom && !draft.style.name.trim()) {
      return '请为自定义风格命名。'
    }
    if (step === 3 && !providerDraft.provider) {
      return '请从后端 catalog 选择 Provider。'
    }
    if (
      step === 3 &&
      providerDraft.credential_required &&
      !providerDraft.api_key?.trim()
    ) {
      return 'Provider 或 Base URL 已改变，请重新输入该服务的 API key。'
    }
    return ''
  }

  function next() {
    const issue = validateCurrentStep()
    if (issue) {
      setError(issue)
      return
    }
    setStep((current) => Math.min(STEPS.length - 1, current + 1))
  }

  async function runProbe() {
    setProbeBusy(true)
    setProbe(null)
    try {
      const result = await api.probeLLMConfig(providerDraft)
      setProbe(result)
    } catch (probeError) {
      setProbe({
        success: false,
        code: probeError.code,
        message: probeError.message,
        details: probeError.details,
      })
    } finally {
      setProbeBusy(false)
    }
  }

  async function submit() {
    const issue = validateCurrentStep()
    if (issue) {
      setError(issue)
      return
    }
    setBusy(true)
    setError('')
    api.setUserLLMConfig(providerDraft, {
      remember: persistence === 'device',
    })
    try {
      const created = await api.createNovel({
        title: draft.story.title.trim(),
        generation_mode: 'author',
      })
      const novelId = created?.id || created?.novel_id
      if (!novelId) throw new Error('后端没有返回 novel_id')

      if (api.fetchStoryBible && api.saveStoryBible) {
        const storyBibleResult = await api.fetchStoryBible(novelId)
        const storyBible =
          storyBibleResult?.story_bible || storyBibleResult?.bible || {}
        await api.saveStoryBible(
          novelId,
          storyBiblePayload(draft, storyBible),
        )
      }

      let styleProfileId =
        draft.style.style_profile_id ||
        (
          draft.style.base_preset_key
            ? `preset_${draft.style.base_preset_key}`
            : 'preset_literary'
        )
      if (draft.style.custom) {
        const style = await api.createStyleProfile(
          novelId,
          stylePayload(draft.style),
        )
        styleProfileId =
          style?.style_profile?.id || style?.profile?.id || style?.id || ''
      }

      const currentSpecResult = api.fetchProductionSpec
        ? await api.fetchProductionSpec(novelId)
        : null
      const currentSpec =
        currentSpecResult?.production_spec ||
        currentSpecResult?.spec ||
        currentSpecResult ||
        { revision: 1 }
      const specResult = await api.saveProductionSpec(
        novelId,
        productionSpecPayload(
          draft,
          styleProfileId,
          Number(currentSpec.revision || 1),
        ),
      )
      let spec =
        specResult?.production_spec || specResult?.spec || specResult
      const stylesResult = api.fetchStyleProfiles
        ? await api.fetchStyleProfiles(novelId)
        : null
      const activeStyle =
        stylesResult?.active_style || stylesResult?.active || null
      const activationResult = await api.activateStyleProfile(
        novelId,
        styleProfileId,
        {
          expected_revision: Number(activeStyle?.revision || 1),
          expected_spec_revision: Number(spec?.revision || 1),
        },
      )
      spec =
        activationResult?.production_spec ||
        activationResult?.spec ||
        spec
      const outline = await api.generateBookOutline(novelId, {
        expected_spec_revision: spec?.revision,
      })

      notify('作品已创建，整书大纲已生成', 'success')
      onCreated?.(novelId, 'author', {
        productionSpec: spec,
        outline: outline?.book_outline || outline?.outline || outline,
      })
      onClose?.()
    } catch (submitError) {
      setError(submitError.message || '创建作品失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="dc-modal-overlay dc-wizard-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose?.()
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-novel-title"
    >
      <div className="dc-wizard-card">
        <header className="dc-wizard-head">
          <div>
            <span className="dc-modal-kicker">NEW AUTHOR PROJECT</span>
            <h2 id="new-novel-title">新建长篇作品</h2>
          </div>
          <button
            type="button"
            className="dc-modal-close"
            onClick={onClose}
            aria-label="关闭"
            disabled={busy}
          >
            ×
          </button>
        </header>

        <nav className="dc-wizard-steps" aria-label="建书步骤">
          {STEPS.map((label, index) => (
            <button
              type="button"
              key={label}
              className={`${index === step ? 'is-active' : ''} ${
                index < step ? 'is-done' : ''
              }`}
              onClick={() => {
                if (index <= step) setStep(index)
              }}
              aria-current={index === step ? 'step' : undefined}
              disabled={index > step}
            >
              <span>{String(index + 1).padStart(2, '0')}</span>
              <strong>{label}</strong>
            </button>
          ))}
        </nav>

        <div className="dc-wizard-body">
          {error && <InlineNotice kind="error">{error}</InlineNotice>}
          {step === 0 && (
            <StoryStep
              value={draft.story}
              onChange={(patch) => updateDomain('story', patch)}
            />
          )}
          {step === 1 && (
            <LengthStep
              value={draft.length}
              estimate={estimate}
              onChange={(patch) => updateDomain('length', patch)}
            />
          )}
          {step === 2 && (
            <StyleStep
              value={draft.style}
              presets={presets}
              onChange={(patch) => updateDomain('style', patch)}
            />
          )}
          {step === 3 && (
            <ProviderConfigPanel
              compact
              providers={providers}
              value={providerDraft}
              onChange={(nextValue) => {
                setProviderDraft(nextValue)
                setProbe(null)
              }}
              persistence={persistence}
              onPersistenceChange={setPersistence}
              runtime={runtime}
              probe={probe}
              probeBusy={probeBusy}
              onProbe={runProbe}
              catalogLoading={providerLoading}
              catalogError={providerError}
            />
          )}
          {step === 4 && (
            <ConfirmStep
              draft={draft}
              estimate={estimate}
              providerDraft={providerDraft}
              probe={probe}
              runtime={runtime}
            />
          )}
        </div>

        <footer className="dc-wizard-foot">
          <span>步骤 {step + 1} / {STEPS.length}</span>
          <div>
            {step > 0 && (
              <button
                type="button"
                className="dc-btn-ghost"
                onClick={() => setStep((current) => current - 1)}
                disabled={busy}
              >
                上一步
              </button>
            )}
            {step < STEPS.length - 1 ? (
              <button type="button" className="dc-btn" onClick={next}>
                继续
              </button>
            ) : (
              <button
                type="button"
                className="dc-btn"
                onClick={submit}
                disabled={busy}
              >
                {busy ? '正在创建并规划…' : '创建作品并生成大纲'}
              </button>
            )}
          </div>
        </footer>
      </div>
    </div>
  )
}

function StoryStep({ value, onChange }) {
  return (
    <WizardSection
      kicker="01 · STORY"
      title="先把故事的北极星钉牢"
      description="这些信息会进入 ProductionSpec 与 StoryBible，而不是启动旧世界模拟。"
    >
      <div className="dc-wizard-form is-two">
        <Field label="小说名" wide>
          <input value={value.title} onChange={(e) => onChange({ title: e.target.value })} placeholder="例如：潮汐尽头的灯" />
        </Field>
        <Field label="一句话设想" wide>
          <textarea rows={3} value={value.premise} onChange={(e) => onChange({ premise: e.target.value })} placeholder="一个守灯人发现旧信，被迫在真相与家族之间选择。" />
        </Field>
        <Field label="题材">
          <input value={value.genre} onChange={(e) => onChange({ genre: e.target.value })} placeholder="现实主义悬疑" />
        </Field>
        <Field label="主题">
          <input value={value.theme} onChange={(e) => onChange({ theme: e.target.value })} placeholder="记忆与责任" />
        </Field>
        <Field label="核心问题" wide>
          <input value={value.central_question} onChange={(e) => onChange({ central_question: e.target.value })} placeholder="沉默究竟保护了谁？" />
        </Field>
        <Field label="结局方向" wide>
          <textarea rows={2} value={value.ending_direction} onChange={(e) => onChange({ ending_direction: e.target.value })} placeholder="真相公开，但关系留下不可逆裂痕。" />
        </Field>
        <Field label="原始 seed" wide hint="保留你的原始表达，不会被自动改写。">
          <textarea rows={4} value={value.source_seed} onChange={(e) => onChange({ source_seed: e.target.value })} placeholder="可选：粘贴最初的灵感、人物或场景。" />
        </Field>
      </div>
    </WizardSection>
  )
}

function LengthStep({ value, estimate, onChange }) {
  return (
    <WizardSection
      kicker="02 · LENGTH"
      title="让篇幅成为生产约束"
      description="统一按非空白字符统计“字数”；模板只填默认值，所有数字仍可自定义。"
    >
      <div className="dc-length-presets">
        {LENGTH_PRESETS.map((preset) => (
          <button
            type="button"
            key={preset.label}
            className={Number(value.target_total_chars) === preset.chars ? 'is-active' : ''}
            onClick={() =>
              {
                const perChapter = Math.round(preset.chars / preset.chapters)
                onChange({
                  target_total_chars: preset.chars,
                  volume_count: preset.volumes,
                  chapter_count: preset.chapters,
                  target_chapter_chars: perChapter,
                  accepted_chapter_min_chars: Math.floor(perChapter * 0.84),
                  accepted_chapter_max_chars: Math.ceil(perChapter * 1.18),
                  section_target_chars: Math.min(
                    Number(value.section_target_chars || 1100),
                    Math.ceil(perChapter * 0.55),
                  ),
                })
              }
            }
          >
            <strong>{preset.label}</strong>
            <span>{(preset.chars / 10000).toLocaleString()} 万字</span>
          </button>
        ))}
      </div>
      <div className="dc-wizard-form is-three">
        <NumberField label="目标总字数" value={value.target_total_chars} min={1000} step={10000} onChange={(v) => onChange({ target_total_chars: v })} />
        <NumberField label="卷数" value={value.volume_count} min={1} step={1} onChange={(v) => onChange({ volume_count: v })} />
        <NumberField label="章节数" value={value.chapter_count} min={1} step={1} onChange={(v) => onChange({ chapter_count: v })} />
        <NumberField label="单章目标字数" value={value.target_chapter_chars} min={500} step={100} onChange={(v) => onChange({ target_chapter_chars: v })} />
        <NumberField label="单节目标字数" value={value.section_target_chars} min={200} step={100} onChange={(v) => onChange({ section_target_chars: v })} />
        <div className="dc-length-range">
          <NumberField label="单章下限" value={value.accepted_chapter_min_chars} min={300} step={100} onChange={(v) => onChange({ accepted_chapter_min_chars: v })} />
          <NumberField label="单章上限" value={value.accepted_chapter_max_chars} min={500} step={100} onChange={(v) => onChange({ accepted_chapter_max_chars: v })} />
        </div>
      </div>
      <div className="dc-length-estimate">
        <span>预计分配</span>
        <strong>{value.volume_count} 卷 · {value.chapter_count} 章 · 约 {estimate.totalSections} 节</strong>
        <p>按总字数折算每章约 {estimate.perChapter.toLocaleString()} 字，每章约 {estimate.sections} 节。</p>
      </div>
    </WizardSection>
  )
}

function StyleStep({ value, presets, onChange }) {
  return (
    <WizardSection
      kicker="03 · STYLE"
      title="选择声音，或建立自己的风格档案"
      description="风格只控制表达方式，不能覆盖事实、事件、终态或字数门槛。"
    >
      <div className="dc-style-preset-grid">
        {presets.slice(0, 12).map((preset) => {
          const key = preset.key || preset.id
          return (
            <button
              type="button"
              key={key}
              className={!value.custom && value.base_preset_key === key ? 'is-active' : ''}
              onClick={() => onChange({
                custom: false,
                base_preset_key: preset.base_preset_key || preset.key || key,
                style_profile_id:
                  preset.id ||
                  `preset_${preset.base_preset_key || preset.key || key}`,
                name: preset.label || preset.name || key,
              })}
            >
              <strong>{preset.label || preset.name || key}</strong>
              <p>{preset.description || '内置只读风格 preset'}</p>
            </button>
          )
        })}
        <button
          type="button"
          className={`is-create ${value.custom ? 'is-active' : ''}`}
          onClick={() => onChange({ custom: true })}
        >
          <strong>＋ 创建自定义风格</strong>
          <p>保存为可复用、可版本化的 StyleProfile。</p>
        </button>
      </div>
      {value.custom && (
        <div className="dc-wizard-form is-two dc-custom-style-form">
          <Field label="风格名称">
            <input value={value.name} onChange={(e) => onChange({ name: e.target.value })} placeholder="潮湿的克制现实主义" />
          </Field>
          <Field label="叙述视角">
            <select value={value.narrative_voice} onChange={(e) => onChange({ narrative_voice: e.target.value })}>
              <option>第三人称限知</option><option>第一人称</option><option>第三人称全知</option>
            </select>
          </Field>
          <SelectField label="句子长度" value={value.sentence_length_tendency} options={['短促', '中等', '舒展']} onChange={(v) => onChange({ sentence_length_tendency: v })} />
          <SelectField label="段落密度" value={value.paragraph_density} options={['疏朗', '适中', '密集']} onChange={(v) => onChange({ paragraph_density: v })} />
          <RangeField label="对话比例" value={value.dialogue_ratio} onChange={(v) => onChange({ dialogue_ratio: v })} />
          <RangeField label="描写比例" value={value.description_ratio} onChange={(v) => onChange({ description_ratio: v })} />
          <Field label="节奏"><input value={value.pacing} onChange={(e) => onChange({ pacing: e.target.value })} /></Field>
          <ScaleField label="情绪强度" value={value.emotional_intensity} onChange={(v) => onChange({ emotional_intensity: v })} />
          <ScaleField label="幽默程度" value={value.humor_level} onChange={(v) => onChange({ humor_level: v })} />
          <Field label="意象偏好"><input value={value.imagery_preference} onChange={(e) => onChange({ imagery_preference: e.target.value })} placeholder="海雾、锈迹、旧纸" /></Field>
          <Field label="词汇偏好"><input value={value.vocabulary_preference} onChange={(e) => onChange({ vocabulary_preference: e.target.value })} placeholder="具体名词、少用抽象形容词" /></Field>
          <Field label="节奏指令" wide><textarea rows={2} value={value.rhythm_instructions} onChange={(e) => onChange({ rhythm_instructions: e.target.value })} /></Field>
          <Field label="章节开篇偏好"><input value={value.chapter_opening_preference} onChange={(e) => onChange({ chapter_opening_preference: e.target.value })} /></Field>
          <Field label="章节收束偏好"><input value={value.chapter_ending_preference} onChange={(e) => onChange({ chapter_ending_preference: e.target.value })} /></Field>
          <Field label="必须遵守" wide><textarea rows={3} value={value.must_do_rules} onChange={(e) => onChange({ must_do_rules: e.target.value })} /></Field>
          <Field label="必须避免" wide><textarea rows={3} value={value.forbidden_rules} onChange={(e) => onChange({ forbidden_rules: e.target.value })} /></Field>
          <Field label="避免短语" wide><textarea rows={2} value={value.avoided_phrases} onChange={(e) => onChange({ avoided_phrases: e.target.value })} /></Field>
          <Field label="可选样文" wide hint="仅用于抽取风格特征，不会复刻句子。"><textarea rows={5} value={value.user_sample} onChange={(e) => onChange({ user_sample: e.target.value })} /></Field>
        </div>
      )}
      <div className="dc-style-summary">
        <span>风格摘要预览</span>
        <p>{styleSummary(value)}</p>
      </div>
    </WizardSection>
  )
}

function ConfirmStep({ draft, estimate, providerDraft, probe, runtime }) {
  return (
    <WizardSection
      kicker="05 · CONFIRM"
      title="把整本书的生产契约确认一次"
      description="创建后会生成整书大纲；不会调用 bootstrapWorld，也不会装配九 Agent simulation。"
    >
      <div className="dc-confirm-grid">
        <SummaryCard label="故事" value={draft.story.title} detail={`${draft.story.genre} · ${draft.story.theme}`} />
        <SummaryCard label="篇幅" value={`${Number(draft.length.target_total_chars).toLocaleString()} 字`} detail={`${draft.length.volume_count} 卷 · ${draft.length.chapter_count} 章 · 约 ${estimate.totalSections} 节`} />
        <SummaryCard label="风格" value={draft.style.name || draft.style.base_preset_key || '默认风格'} detail={styleSummary(draft.style)} />
        <SummaryCard label="Provider" value={`${providerDraft.provider || '—'} · ${providerDraft.model || '—'}`} detail={probe?.success ? `已测试 · ${probe.latency_ms || 0} ms` : runtime?.credential_present ? '已有脱敏凭据 · 尚未测试本次配置' : '尚未测试'} />
      </div>
      <section className="dc-authority-files">
        <span>将创建的权威文件</span>
        <div>
          {['production_spec.json', 'book_outline.json', 'style_profiles.json', 'active_style.json', 'generation_jobs/', 'production_events/'].map((file) => <code key={file}>{file}</code>)}
        </div>
      </section>
    </WizardSection>
  )
}

function WizardSection({ kicker, title, description, children }) {
  return (
    <section className="dc-wizard-section">
      <header>
        <span>{kicker}</span>
        <h3>{title}</h3>
        <p>{description}</p>
      </header>
      {children}
    </section>
  )
}

function Field({ label, hint, wide, children }) {
  return (
    <label className={wide ? 'is-wide' : ''}>
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  )
}

function NumberField({ label, value, min, step, onChange }) {
  return (
    <Field label={label}>
      <input type="number" value={value} min={min} step={step} onChange={(e) => onChange(Number(e.target.value))} />
    </Field>
  )
}

function SelectField({ label, value, options, onChange }) {
  return (
    <Field label={label}>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((option) => <option key={option}>{option}</option>)}
      </select>
    </Field>
  )
}

function RangeField({ label, value, onChange }) {
  return (
    <Field label={`${label} · ${value}%`}>
      <input type="range" min="0" max="100" step="5" value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </Field>
  )
}

function ScaleField({ label, value, onChange }) {
  return (
    <Field label={`${label} · ${value}/10`}>
      <input
        type="range"
        min="0"
        max="10"
        step="1"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </Field>
  )
}

function SummaryCard({ label, value, detail }) {
  return (
    <article>
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </article>
  )
}

function styleSummary(style) {
  if (!style.custom) return style.name || style.base_preset_key || '沿用内置默认风格'
  return [
    style.narrative_voice,
    `${style.sentence_length_tendency}句`,
    `${style.paragraph_density}段落`,
    style.pacing,
    `情绪 ${style.emotional_intensity}/10`,
  ].filter(Boolean).join(' · ')
}

function splitRules(value) {
  return String(value || '')
    .split(/\r?\n|[,，;]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function stylePayload(style) {
  return {
    name: style.name.trim(),
    base_preset_key: style.base_preset_key || '',
    description: style.description,
    narrative_voice: style.narrative_voice,
    viewpoint: style.viewpoint,
    tense: style.tense,
    sentence_length_tendency: style.sentence_length_tendency,
    paragraph_density: style.paragraph_density,
    dialogue_ratio: Number(style.dialogue_ratio) / 100,
    description_ratio: Number(style.description_ratio) / 100,
    pacing: style.pacing,
    emotional_intensity: Number(style.emotional_intensity),
    humor_level: Number(style.humor_level),
    imagery_preference: style.imagery_preference,
    vocabulary_preference: style.vocabulary_preference,
    rhythm_instructions: style.rhythm_instructions,
    chapter_opening_preference: style.chapter_opening_preference,
    chapter_ending_preference: style.chapter_ending_preference,
    must_do_rules: splitRules(style.must_do_rules),
    forbidden_rules: splitRules(style.forbidden_rules),
    avoided_phrases: splitRules(style.avoided_phrases),
    optional_user_sample: style.user_sample,
    derived_style_anchors: [],
    deterministic_rules: [],
  }
}

function productionSpecPayload(draft, styleProfileId, expectedRevision) {
  return {
    expected_revision: expectedRevision,
    title: draft.story.title.trim(),
    premise: draft.story.premise.trim(),
    genre: draft.story.genre.trim(),
    theme: draft.story.theme.trim(),
    central_question: draft.story.central_question.trim(),
    target_total_chars: Number(draft.length.target_total_chars),
    volume_count: Number(draft.length.volume_count),
    chapter_count: Number(draft.length.chapter_count),
    target_chapter_chars: Number(draft.length.target_chapter_chars),
    accepted_chapter_min_chars: Number(draft.length.accepted_chapter_min_chars),
    accepted_chapter_max_chars: Number(draft.length.accepted_chapter_max_chars),
    section_target_chars: Number(draft.length.section_target_chars),
    generation_language: draft.length.generation_language,
    ending_direction: draft.story.ending_direction.trim(),
    active_style_profile_id: styleProfileId || 'preset_literary',
  }
}

function storyBiblePayload(draft, current = {}) {
  return {
    expected_revision: Number(current.revision || 0),
    title: draft.story.title.trim(),
    source_seed: draft.story.source_seed,
    theme_key: current.theme_key || '',
    positioning: current.positioning || draft.story.genre.trim(),
    reference_preferences: current.reference_preferences || [],
    premise: draft.story.premise.trim(),
    theme: draft.story.theme.trim(),
    central_question: draft.story.central_question.trim(),
    genre: draft.story.genre.trim(),
    setting_summary:
      current.setting_summary ||
      `题材：${draft.story.genre.trim()}。故事前提：${draft.story.premise.trim()}`,
    ending_direction: draft.story.ending_direction.trim(),
    style_contract: current.style_contract || {},
    immutable_world_rules: current.immutable_world_rules || [],
    forbidden_deviations: current.forbidden_deviations || [],
    protagonist_contracts: current.protagonist_contracts || [],
    main_conflicts: current.main_conflicts || [],
  }
}
