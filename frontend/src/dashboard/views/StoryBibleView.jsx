import React, { useEffect, useMemo, useState } from 'react'
import { fetchStoryBible, saveStoryBible } from '../../services/api'
import { showToast } from '../../utils/toast'

const DEFAULT_API = { fetchStoryBible, saveStoryBible }

const LIST_FIELDS = [
  ['immutable_world_rules', '不可变世界规则', '每行一条。Writer 和 StateDelta 都不能修改。'],
  ['forbidden_deviations', '禁止偏移', '明确列出绝不能发生的题材、设定或人物偏移。'],
  ['protagonist_contracts', '主角契约', '主角的核心价值、底线、长期欲望与不可丢失特征。'],
  ['main_conflicts', '主冲突', '每行一条必须持续推进或回响的主线冲突。'],
]

function toForm(bible) {
  const next = { ...bible }
  LIST_FIELDS.forEach(([key]) => {
    next[key] = (bible?.[key] || []).join('\n')
  })
  next.style_contract = JSON.stringify(bible?.style_contract || {}, null, 2)
  next.reference_preferences = (bible?.reference_preferences || []).join('\n')
  return next
}

function normaliseLines(value) {
  return String(value || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
}

export default function StoryBibleView({ novel, api = DEFAULT_API, notify = showToast }) {
  const [bible, setBible] = useState(null)
  const [migration, setMigration] = useState(null)
  const [form, setForm] = useState(null)
  const [edit, setEdit] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})

  const dirty = useMemo(() => {
    if (!bible || !form) return false
    return JSON.stringify(form) !== JSON.stringify(toForm(bible))
  }, [bible, form])

  useEffect(() => {
    if (!novel?.id) return undefined
    let cancelled = false
    setLoading(true)
    setError('')
    api.fetchStoryBible(novel.id)
      .then((data) => {
        if (cancelled) return
        setBible(data.story_bible)
        setMigration(data.migration)
        setForm(toForm(data.story_bible))
        setEdit(false)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || '创作圣经加载失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [novel?.id, api])

  useEffect(() => {
    function beforeUnload(event) {
      if (!dirty) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [dirty])

  function update(key, value) {
    setForm((current) => ({ ...current, [key]: value }))
    setFieldErrors((current) => ({ ...current, [key]: '' }))
  }

  async function save() {
    const errors = {}
    ;['premise', 'theme', 'setting_summary'].forEach((key) => {
      if (!String(form?.[key] || '').trim()) errors[key] = '此字段不能为空'
    })
    let styleContract = {}
    try {
      styleContract = JSON.parse(form?.style_contract || '{}')
      if (!styleContract || Array.isArray(styleContract) || typeof styleContract !== 'object') {
        errors.style_contract = '风格契约必须是 JSON 对象'
      }
    } catch {
      errors.style_contract = 'JSON 格式无效'
    }
    if (Object.keys(errors).length) {
      setFieldErrors(errors)
      return
    }
    const payload = {
      expected_revision: bible.revision,
      title: form.title || '',
      source_seed: form.source_seed || '',
      theme_key: form.theme_key || '',
      positioning: form.positioning || '',
      reference_preferences: normaliseLines(form.reference_preferences),
      premise: form.premise.trim(),
      theme: form.theme.trim(),
      central_question: form.central_question || '',
      genre: form.genre || '',
      setting_summary: form.setting_summary.trim(),
      ending_direction: form.ending_direction || '',
      style_contract: styleContract,
    }
    LIST_FIELDS.forEach(([key]) => {
      payload[key] = normaliseLines(form[key])
    })
    setSaving(true)
    setError('')
    try {
      const data = await api.saveStoryBible(novel.id, payload)
      setBible(data.story_bible)
      setForm(toForm(data.story_bible))
      setMigration((current) => ({ ...current, inferred_fields: [] }))
      setEdit(false)
      notify(`创作圣经已保存 · revision ${data.story_bible.revision}`, 'success')
    } catch (err) {
      setError(
        err.code === 'REVISION_CONFLICT'
          ? '另一个会话已更新创作圣经。请刷新页面后合并你的修改。'
          : err.message || '保存失败',
      )
    } finally {
      setSaving(false)
    }
  }

  if (!novel?.id) return <EmptyState text="请先选择作品。" />
  if (loading) return <EmptyState text="正在装订创作圣经…" />
  if (!bible || !form) return <EmptyState text={error || '创作圣经暂不可用。'} error />

  return (
    <div className="dc-view-switch dc-au-root">
      <header className="dc-au-masthead">
        <div>
          <span className="dc-au-eyebrow">STORY BIBLE · 最高创作权威</span>
          <h1>创作圣经</h1>
          <p>主题、背景规则与主角契约始终进入每一次正文生成，不参与相似度淘汰。</p>
        </div>
        <div className="dc-au-mast-actions">
          <span className="dc-au-revision">REV {String(bible.revision).padStart(3, '0')}</span>
          {dirty && <span className="dc-au-dirty">有未保存修改</span>}
          <button
            type="button"
            className="dc-btn-ghost"
            onClick={() => {
              if (edit && dirty && !window.confirm('放弃尚未保存的修改？')) return
              setForm(toForm(bible))
              setEdit((value) => !value)
              setFieldErrors({})
            }}
          >
            {edit ? '取消编辑' : '编辑圣经'}
          </button>
          {edit && (
            <button type="button" className="dc-btn" onClick={save} disabled={saving}>
              {saving ? '保存中…' : '保存并提升 revision'}
            </button>
          )}
        </div>
      </header>

      {bible.migration?.needs_confirmation && (
        <div className="dc-au-notice is-inferred">
          <span className="dc-au-notice-mark">推断草稿</span>
          <div>
            <strong>
              {bible.migration.source === 'legacy_inferred'
                ? '由旧数据推断，需要确认'
                : '初始化补充字段待确认'}
            </strong>
            <p>
              来源：{(migration?.source_files || bible.migration.source_files || []).join(' / ') || '作品标题'}。
              推断字段：{(bible.migration.inferred_fields || []).join('、') || '基础创作契约'}。
            </p>
          </div>
        </div>
      )}
      {error && <div className="dc-au-notice is-error">{error}</div>}

      <div className="dc-au-bible-grid">
        <section className="dc-au-paper is-lead">
          <div className="dc-au-two-col">
            <Field
              label="作品标题 · TITLE"
              value={form.title}
              editing={edit}
              onChange={(value) => update('title', value)}
            />
            <Field
              label="主题 PRESET KEY"
              value={form.theme_key}
              editing={edit}
              onChange={(value) => update('theme_key', value)}
            />
          </div>
          <Field
            label="原始种子 · SOURCE SEED（逐字保存）"
            value={form.source_seed}
            editing={edit}
            multiline
            onChange={(value) => update('source_seed', value)}
          />
          <Field
            label="故事前提 · PREMISE"
            value={form.premise}
            editing={edit}
            multiline
            error={fieldErrors.premise}
            onChange={(value) => update('premise', value)}
          />
          <div className="dc-au-two-col">
            <Field
              label="主题 · THEME"
              value={form.theme}
              editing={edit}
              error={fieldErrors.theme}
              onChange={(value) => update('theme', value)}
            />
            <Field
              label="核心问题 · CENTRAL QUESTION"
              value={form.central_question}
              editing={edit}
              onChange={(value) => update('central_question', value)}
            />
          </div>
          <div className="dc-au-two-col">
            <Field
              label="作品定位 · POSITIONING"
              value={form.positioning}
              editing={edit}
              multiline
              onChange={(value) => update('positioning', value)}
            />
            <Field
              label="参考偏好 · REFERENCES"
              value={form.reference_preferences}
              editing={edit}
              multiline
              onChange={(value) => update('reference_preferences', value)}
            />
          </div>
          <Field
            label="背景摘要 · SETTING"
            value={form.setting_summary}
            editing={edit}
            multiline
            error={fieldErrors.setting_summary}
            onChange={(value) => update('setting_summary', value)}
          />
          <div className="dc-au-two-col">
            <Field
              label="类型 · GENRE"
              value={form.genre}
              editing={edit}
              onChange={(value) => update('genre', value)}
            />
            <Field
              label="结局方向 · ENDING DIRECTION"
              value={form.ending_direction}
              editing={edit}
              onChange={(value) => update('ending_direction', value)}
            />
          </div>
        </section>

        <aside className="dc-au-margin-note">
          <span>权威顺序</span>
          <ol>
            <li>StoryBible</li>
            <li>CanonicalState</li>
            <li>已验证 StateDelta</li>
            <li>历史记忆</li>
          </ol>
          <p>低层信息永远不能覆盖高层契约。</p>
        </aside>
      </div>

      <div className="dc-au-contract-grid">
        {LIST_FIELDS.map(([key, label, hint]) => (
          <section className={`dc-au-contract ${key === 'immutable_world_rules' ? 'is-sealed' : ''}`} key={key}>
            <div className="dc-au-contract-head">
              <span>{label}</span>
              {key === 'immutable_world_rules' && <em>IMMUTABLE</em>}
            </div>
            <p>{hint}</p>
            {edit ? (
              <textarea
                value={form[key]}
                onChange={(event) => update(key, event.target.value)}
                rows={7}
                className="dc-au-textarea"
              />
            ) : (
              <ul>
                {normaliseLines(form[key]).map((item) => <li key={item}>{item}</li>)}
                {normaliseLines(form[key]).length === 0 && <li className="is-empty">尚未定义</li>}
              </ul>
            )}
          </section>
        ))}
      </div>

      <section className="dc-au-paper">
        <Field
          label="风格契约 · STYLE CONTRACT (JSON)"
          value={form.style_contract}
          editing={edit}
          code
          multiline
          error={fieldErrors.style_contract}
          onChange={(value) => update('style_contract', value)}
        />
      </section>
    </div>
  )
}

function Field({ label, value, editing, multiline, code, error, onChange }) {
  return (
    <label className="dc-au-field">
      <span>{label}</span>
      {editing ? (
        multiline ? (
          <textarea
            className={`dc-au-input ${code ? 'is-code' : ''}`}
            value={value || ''}
            rows={code ? 8 : 4}
            onChange={(event) => onChange(event.target.value)}
          />
        ) : (
          <input
            className="dc-au-input"
            value={value || ''}
            onChange={(event) => onChange(event.target.value)}
          />
        )
      ) : (
        <div className={`dc-au-value ${code ? 'is-code' : ''}`}>{value || '尚未定义'}</div>
      )}
      {error && <small className="dc-au-field-error">{error}</small>}
    </label>
  )
}

function EmptyState({ text, error = false }) {
  return <div className={`dc-au-empty ${error ? 'is-error' : ''}`}>{text}</div>
}
