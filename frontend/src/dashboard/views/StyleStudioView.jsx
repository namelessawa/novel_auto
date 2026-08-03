import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  activateStyleProfile,
  createStyleProfile,
  fetchCommittedChapters,
  fetchProductionSpec,
  fetchStyleProfiles,
  previewStyleProfile,
  saveStyleProfile,
} from '../../services/api'
import AsyncState, { InlineNotice } from '../components/AsyncState'
import { showToast } from '../../utils/toast'

const DEFAULT_API = {
  activateStyleProfile,
  createStyleProfile,
  fetchCommittedChapters,
  fetchProductionSpec,
  fetchStyleProfiles,
  previewStyleProfile,
  saveStyleProfile,
}

const EMPTY_STYLE = {
  id: '',
  revision: 0,
  name: '',
  description: '',
  base_preset_key: '',
  narrative_voice: '第三人称限知',
  viewpoint: '近距离',
  tense: '过去时',
  sentence_length_tendency: '中等',
  paragraph_density: '适中',
  pacing: '张弛交替',
  dialogue_ratio: 0.35,
  description_ratio: 0.35,
  emotional_intensity: 4,
  humor_level: 1,
  imagery_preference: '',
  vocabulary_preference: '',
  rhythm_instructions: '',
  chapter_opening_preference: '',
  chapter_ending_preference: '',
  must_do_rules: [],
  forbidden_rules: [],
  avoided_phrases: [],
  optional_user_sample: '',
  derived_style_anchors: [],
  deterministic_rules: [],
  prompt_hash: '',
  read_only: false,
}

export default function StyleStudioView({
  novel,
  api = DEFAULT_API,
  notify = showToast,
}) {
  const [profiles, setProfiles] = useState([])
  const [active, setActive] = useState(null)
  const [spec, setSpec] = useState(null)
  const [selectedId, setSelectedId] = useState('')
  const [draft, setDraft] = useState(null)
  const [compareId, setCompareId] = useState('')
  const [preview, setPreview] = useState(null)
  const [comparePreview, setComparePreview] = useState(null)
  const [recentValidation, setRecentValidation] = useState(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    if (!novel?.id) return
    setLoading(true)
    setError('')
    const [profilesResult, specResult, chaptersResult] =
      await Promise.allSettled([
        api.fetchStyleProfiles(novel.id),
        api.fetchProductionSpec(novel.id),
        api.fetchCommittedChapters(novel.id),
      ])
    if (profilesResult.status === 'fulfilled') {
      const payload = profilesResult.value || {}
      const rawProfiles = payload.profiles || payload.items || []
      const rows = (
        Array.isArray(rawProfiles)
          ? rawProfiles
          : Object.values(rawProfiles)
      ).map(normalizeStyleProfile)
      const activeStyle = payload.active_style || payload.active || null
      setProfiles(rows)
      setActive(activeStyle)
      const nextId =
        selectedId ||
        activeStyleId(activeStyle) ||
        rows[0]?.id ||
        ''
      setSelectedId(nextId)
      setDraft(cloneStyle(rows.find((item) => item.id === nextId) || null))
    } else {
      setError(profilesResult.reason?.message || '风格档案读取失败')
    }
    if (specResult.status === 'fulfilled') {
      setSpec(
        specResult.value?.production_spec ||
        specResult.value?.spec ||
        specResult.value,
      )
    }
    if (chaptersResult.status === 'fulfilled') {
      const chapters =
        chaptersResult.value?.chapters ||
        chaptersResult.value?.items ||
        []
      const latest = chapters[chapters.length - 1]
      setRecentValidation(
        latest?.style_validation_report ||
        latest?.validation?.style ||
        null,
      )
    }
    setLoading(false)
  }, [api, novel?.id, selectedId])

  useEffect(() => {
    setProfiles([])
    setDraft(null)
    setSelectedId('')
    load()
    // Selection is updated locally; reloading on every click would overwrite edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [novel?.id])

  function select(id) {
    setSelectedId(id)
    setDraft(cloneStyle(profiles.find((item) => item.id === id)))
    setPreview(null)
    setNotice('')
    setError('')
  }

  function createNew(base = null) {
    const source = base || EMPTY_STYLE
    setSelectedId('')
    setDraft({
      ...cloneStyle(source),
      id: '',
      revision: 0,
      read_only: false,
      prompt_hash: '',
      name: base ? `${source.name} · 副本` : '我的新风格',
      base_preset_key: base?.id || base?.base_preset_key || '',
    })
    setPreview(null)
    setNotice('')
  }

  async function save() {
    if (!draft?.name?.trim() || busy) {
      setError('请先填写风格名称。')
      return
    }
    setBusy('save')
    setError('')
    try {
      const payload = editableStylePayload(draft)
      const result = draft.id
        ? await api.saveStyleProfile(novel.id, draft.id, {
            expected_revision: draft.revision,
            ...payload,
          })
        : await api.createStyleProfile(novel.id, payload)
      const saved =
        normalizeStyleProfile(
          result?.style_profile || result?.profile || result,
        )
      setDraft(cloneStyle(saved))
      setSelectedId(saved.id)
      setProfiles((current) => {
        const exists = current.some((item) => item.id === saved.id)
        return exists
          ? current.map((item) => item.id === saved.id ? saved : item)
          : [...current, saved]
      })
      notify(`风格版本已保存 · R${saved.revision}`, 'success')
    } catch (saveError) {
      setError(
        saveError.code === 'REVISION_CONFLICT'
          ? '风格档案已在其他会话更新，请重新载入。'
          : saveError.message || '风格保存失败',
      )
    } finally {
      setBusy('')
    }
  }

  async function generatePreview(style = draft, compare = false) {
    if (!style?.id) {
      setError('请先保存风格版本，再生成样章预览。')
      return
    }
    setBusy(compare ? 'compare' : 'preview')
    setError('')
    try {
      const result = await api.previewStyleProfile(novel.id, style.id, {
        expected_revision: style.revision,
        sample_goal: '用一个短场景展示叙事声音，不推进正式 Canon。',
      })
      const text =
        (
          typeof result?.preview === 'string'
            ? result.preview
            : result?.preview?.text
        ) ||
        result?.text ||
        result?.content ||
        ''
      if (compare) setComparePreview({ style, text })
      else setPreview({ style, text })
    } catch (previewError) {
      setError(previewError.message || '样章预览失败')
    } finally {
      setBusy('')
    }
  }

  async function activate() {
    if (!draft?.id || busy) return
    setBusy('activate')
    setError('')
    try {
      const result = await api.activateStyleProfile(novel.id, draft.id, {
        expected_revision: Number(active?.revision || 1),
        expected_spec_revision: spec?.revision,
      })
      const nextActive =
        result?.active_style ||
        result?.active ||
        result?.binding ||
        result
      setActive(nextActive)
      if (result?.production_spec) setSpec(result.production_spec)
      const ordinal =
        nextActive?.applies_from_chapter_ordinal ||
        result?.applies_from_chapter_ordinal
      setNotice(
        `风格将从下一未生成章节${ordinal ? `（第 ${ordinal} 章）` : ''}生效；不会静默改写已提交章节。`,
      )
      notify('风格已应用到下一章', 'success')
    } catch (activateError) {
      setError(activateError.message || '应用风格失败')
    } finally {
      setBusy('')
    }
  }

  const compareStyle = useMemo(
    () => profiles.find((item) => item.id === compareId) || null,
    [compareId, profiles],
  )

  if (!novel?.id) return <AsyncState kind="empty" title="请先选择作品" />
  if (loading && !draft && !profiles.length) {
    return <AsyncState title="正在载入风格工作室" />
  }

  return (
    <div className="dc-view-switch dc-production-root dc-style-root" data-testid="style-studio">
      <header className="dc-product-masthead">
        <div>
          <span className="dc-product-eyebrow">STYLE PROFILE · VERSIONED</span>
          <h1>风格工作室</h1>
          <p>风格可以复用和比较，但永远排在 NarrativeContract 与 Canon 之后。</p>
        </div>
        <button type="button" className="dc-btn" onClick={() => createNew()}>
          ＋ 创建自定义风格
        </button>
      </header>

      {error && (
        <InlineNotice
          kind="error"
          actions={error.includes('其他会话') ? <button type="button" onClick={load}>载入最新版本</button> : null}
        >
          {error}
        </InlineNotice>
      )}
      {notice && <InlineNotice kind="success">{notice}</InlineNotice>}

      <div className="dc-style-layout">
        <aside className="dc-style-library">
          <span>风格档案 · {profiles.length}</span>
          <div>
            {profiles.map((profile) => (
              <button
                type="button"
                key={profile.id}
                className={selectedId === profile.id ? 'is-active' : ''}
                onClick={() => select(profile.id)}
              >
                <strong>{profile.name}</strong>
                <p>{profile.description || profile.tone || '—'}</p>
                <em>
                  {profile.read_only ? 'PRESET' : `R${profile.revision}`}
                  {activeStyleId(active) === profile.id ? ' · ACTIVE' : ''}
                </em>
              </button>
            ))}
          </div>
        </aside>

        <main className="dc-style-editor">
          {!draft ? (
            <AsyncState
              kind="empty"
              title="选择一个风格，或创建自定义风格"
            />
          ) : (
            <>
              <header className="dc-style-editor-head">
                <div>
                  <span>{draft.read_only ? 'READ-ONLY PRESET' : `STYLE REVISION ${draft.revision || 'NEW'}`}</span>
                  <h2>{draft.name}</h2>
                  <code title={draft.prompt_hash || ''}>
                    prompt {shortHash(draft.prompt_hash)}
                  </code>
                </div>
                <div>
                  {draft.read_only && (
                    <button type="button" className="dc-btn-ghost" onClick={() => createNew(draft)}>
                      复制后修改
                    </button>
                  )}
                  {!draft.read_only && (
                    <button type="button" className="dc-btn" onClick={save} disabled={busy === 'save'}>
                      {busy === 'save' ? '保存中…' : '保存新版本'}
                    </button>
                  )}
                </div>
              </header>
              <StyleEditor
                value={draft}
                disabled={draft.read_only}
                onChange={(patch) => {
                  setDraft((current) => ({ ...current, ...patch }))
                  setNotice('')
                }}
              />
              <div className="dc-style-actions">
                <button type="button" className="dc-btn-ghost" onClick={() => generatePreview()} disabled={!draft.id || Boolean(busy)}>
                  {busy === 'preview' ? '正在生成预览…' : '生成短样章预览'}
                </button>
                <button type="button" className="dc-btn" onClick={activate} disabled={!draft.id || Boolean(busy) || activeStyleId(active) === draft.id}>
                  {activeStyleId(active) === draft.id ? '当前生效风格' : '应用到下一章'}
                </button>
              </div>
            </>
          )}
        </main>
      </div>

      {(preview || profiles.length > 1) && (
        <section className="dc-style-compare">
          <header>
            <div><span>STYLE COMPARISON</span><h2>样章对比</h2></div>
            <div>
              <select value={compareId} onChange={(e) => {
                setCompareId(e.target.value)
                setComparePreview(null)
              }}>
                <option value="">选择另一种风格</option>
                {profiles.filter((profile) => profile.id !== draft?.id).map((profile) => <option value={profile.id} key={profile.id}>{profile.name}</option>)}
              </select>
              <button type="button" onClick={() => generatePreview(compareStyle, true)} disabled={!compareStyle || Boolean(busy)}>
                {busy === 'compare' ? '生成中…' : '生成对比'}
              </button>
            </div>
          </header>
          <div>
            <PreviewCard preview={preview} empty="先生成当前风格预览。" />
            <PreviewCard preview={comparePreview} empty="选择另一种风格后生成对比。" />
          </div>
        </section>
      )}

      <section className="dc-style-validation">
        <span>最近章节风格校验</span>
        {recentValidation ? (
          <pre>{JSON.stringify(recentValidation, null, 2)}</pre>
        ) : (
          <p>尚无正式提交章节的风格校验结果。</p>
        )}
      </section>
    </div>
  )
}

function StyleEditor({ value, onChange, disabled }) {
  return (
    <div className="dc-style-form">
      <TextField label="风格名称" value={value.name} disabled={disabled} onChange={(name) => onChange({ name })} />
      <TextField label="说明" value={value.description} disabled={disabled} onChange={(description) => onChange({ description })} />
      <TextField label="叙述人称" value={value.narrative_voice} disabled={disabled} onChange={(narrative_voice) => onChange({ narrative_voice })} />
      <TextField label="叙事视角 / 距离" value={value.viewpoint} disabled={disabled} onChange={(viewpoint) => onChange({ viewpoint })} />
      <TextField label="时态" value={value.tense} disabled={disabled} onChange={(tense) => onChange({ tense })} />
      <TextField label="句子长度" value={value.sentence_length_tendency} disabled={disabled} onChange={(sentence_length_tendency) => onChange({ sentence_length_tendency })} />
      <TextField label="段落密度" value={value.paragraph_density} disabled={disabled} onChange={(paragraph_density) => onChange({ paragraph_density })} />
      <TextField label="节奏" value={value.pacing} disabled={disabled} onChange={(pacing) => onChange({ pacing })} />
      <TextField label="意象偏好" value={value.imagery_preference} disabled={disabled} onChange={(imagery_preference) => onChange({ imagery_preference })} />
      <TextField label="词汇偏好" value={value.vocabulary_preference} disabled={disabled} onChange={(vocabulary_preference) => onChange({ vocabulary_preference })} />
      <TextField label="节奏指令" value={value.rhythm_instructions} disabled={disabled} onChange={(rhythm_instructions) => onChange({ rhythm_instructions })} />
      <TextField label="章节开篇偏好" value={value.chapter_opening_preference} disabled={disabled} onChange={(chapter_opening_preference) => onChange({ chapter_opening_preference })} />
      <TextField label="章节收束偏好" value={value.chapter_ending_preference} disabled={disabled} onChange={(chapter_ending_preference) => onChange({ chapter_ending_preference })} />
      <RangeField label="对话比例" value={value.dialogue_ratio} disabled={disabled} onChange={(dialogue_ratio) => onChange({ dialogue_ratio })} />
      <RangeField label="描写比例" value={value.description_ratio} disabled={disabled} onChange={(description_ratio) => onChange({ description_ratio })} />
      <ScaleField label="情绪强度" value={value.emotional_intensity} disabled={disabled} onChange={(emotional_intensity) => onChange({ emotional_intensity })} />
      <ScaleField label="幽默程度" value={value.humor_level} disabled={disabled} onChange={(humor_level) => onChange({ humor_level })} />
      <label className="is-wide">
        <span>必须遵守</span>
        <textarea rows={3} disabled={disabled} value={(value.must_do_rules || []).join('\n')} onChange={(e) => onChange({ must_do_rules: splitLines(e.target.value) })} />
      </label>
      <label className="is-wide">
        <span>必须避免</span>
        <textarea rows={3} disabled={disabled} value={(value.forbidden_rules || []).join('\n')} onChange={(e) => onChange({ forbidden_rules: splitLines(e.target.value) })} />
      </label>
      <label className="is-wide">
        <span>避免短语</span>
        <textarea rows={3} disabled={disabled} value={(value.avoided_phrases || []).join('\n')} onChange={(e) => onChange({ avoided_phrases: splitLines(e.target.value) })} />
      </label>
      <label className="is-wide">
        <span>可选样文 · 只抽取特征，不进入 Writer prompt</span>
        <textarea rows={6} disabled={disabled} value={value.optional_user_sample || ''} onChange={(e) => onChange({ optional_user_sample: e.target.value })} />
      </label>
    </div>
  )
}

function TextField({ label, value, onChange, disabled }) {
  return <label><span>{label}</span><input disabled={disabled} value={value || ''} onChange={(e) => onChange(e.target.value)} /></label>
}

function RangeField({ label, value, onChange, disabled }) {
  const normalized = Number(value || 0)
  return (
    <label>
      <span>{label} · {Math.round(normalized * 100)}%</span>
      <input type="range" disabled={disabled} min="0" max="1" step="0.05" value={normalized} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  )
}

function ScaleField({ label, value, onChange, disabled }) {
  const normalized = Number(value || 0)
  return (
    <label>
      <span>{label} · {normalized}/10</span>
      <input type="range" disabled={disabled} min="0" max="10" step="1" value={normalized} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  )
}

function PreviewCard({ preview, empty }) {
  return (
    <article>
      <span>{preview?.style?.name || '—'}</span>
      <p>{preview?.text || empty}</p>
    </article>
  )
}

function cloneStyle(style) {
  if (!style) return null
  return JSON.parse(JSON.stringify(normalizeStyleProfile(style)))
}

function editableStylePayload(style) {
  const {
    name,
    description,
    base_preset_key,
    narrative_voice,
    viewpoint,
    tense,
    sentence_length_tendency,
    paragraph_density,
    pacing,
    dialogue_ratio,
    description_ratio,
    emotional_intensity,
    humor_level,
    imagery_preference,
    vocabulary_preference,
    rhythm_instructions,
    chapter_opening_preference,
    chapter_ending_preference,
    must_do_rules,
    forbidden_rules,
    avoided_phrases,
    optional_user_sample,
    derived_style_anchors,
    deterministic_rules,
  } = style
  return {
    name,
    description,
    base_preset_key: base_preset_key || '',
    narrative_voice,
    viewpoint,
    tense,
    sentence_length_tendency,
    paragraph_density,
    pacing,
    dialogue_ratio: Number(dialogue_ratio),
    description_ratio: Number(description_ratio),
    emotional_intensity: Number(emotional_intensity),
    humor_level: Number(humor_level),
    imagery_preference,
    vocabulary_preference,
    rhythm_instructions,
    chapter_opening_preference,
    chapter_ending_preference,
    must_do_rules,
    forbidden_rules,
    avoided_phrases,
    optional_user_sample,
    derived_style_anchors,
    deterministic_rules,
  }
}

function normalizeStyleProfile(style = {}) {
  const toList = (value) => {
    if (Array.isArray(value)) return value
    if (!value) return []
    return splitLines(String(value))
  }
  const numeric = (value, fallback) => (
    Number.isFinite(Number(value)) ? Number(value) : fallback
  )
  return {
    ...EMPTY_STYLE,
    ...style,
    narrative_voice:
      style.narrative_voice ||
      style.narrative_person ||
      EMPTY_STYLE.narrative_voice,
    viewpoint:
      style.viewpoint ||
      style.distance ||
      EMPTY_STYLE.viewpoint,
    sentence_length_tendency:
      style.sentence_length_tendency ||
      style.sentence_length ||
      EMPTY_STYLE.sentence_length_tendency,
    paragraph_density:
      style.paragraph_density ||
      style.register ||
      EMPTY_STYLE.paragraph_density,
    description_ratio: numeric(
      style.description_ratio ?? style.description_density,
      EMPTY_STYLE.description_ratio,
    ),
    emotional_intensity: numeric(
      style.emotional_intensity,
      EMPTY_STYLE.emotional_intensity,
    ),
    humor_level: numeric(style.humor_level, EMPTY_STYLE.humor_level),
    imagery_preference:
      style.imagery_preference ||
      style.imagery ||
      '',
    vocabulary_preference:
      style.vocabulary_preference ||
      toList(style.lexical_preferences).join('、'),
    must_do_rules: toList(style.must_do_rules),
    forbidden_rules: toList(
      style.forbidden_rules || style.forbidden_patterns,
    ),
    avoided_phrases: toList(style.avoided_phrases),
    derived_style_anchors: toList(style.derived_style_anchors),
    deterministic_rules: toList(style.deterministic_rules),
  }
}

function activeStyleId(active) {
  if (!active) return ''
  if (typeof active === 'string') return active
  return active.style_profile_id || active.id || ''
}

function splitLines(value) {
  return value.split(/\r?\n|[,，]/).map((item) => item.trim()).filter(Boolean)
}

function shortHash(hash) {
  return hash ? `${hash.slice(0, 12)}…` : 'not saved'
}
