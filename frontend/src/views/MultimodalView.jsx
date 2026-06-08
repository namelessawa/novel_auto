import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchMultimodalAssetBlobUrl,
  generateMultimodal,
  getActiveImageProviderConfig,
  getMultimodalManifest,
  listMultimodalSections,
  listTickSections,
  listTTSVoices,
  previewMultimodalSegments,
  watchTaskStream,
} from '../services/api'
import { showToast } from '../utils/toast'

// v2.33 — 多模态生成视图: 选节 → 预览分段 → 配置 → 生成 → 视频.
//
// 流程:
//   1. 用户进来, 左侧列出当前 active novel 的所有节
//   2. 点一节, 右侧自动预览分段 + 检查是否已有 manifest
//   3. 配置好后点"开始生成", 通过 task SSE 流监听进度
//   4. 完成后右侧显示视频播放器 + 段卡片 (图 + 音 + 字)

// v2.32 — 讯飞 MaaS 6 档分辨率
const SIZE_PRESETS = [
  { label: '768×768 (方形 SD)', w: 768, h: 768 },
  { label: '1024×1024 (方形 HD)', w: 1024, h: 1024 },
  { label: '1024×576 (16:9 横)', w: 1024, h: 576 },
  { label: '576×1024 (9:16 竖)', w: 576, h: 1024 },
  { label: '1024×768 (4:3 横)', w: 1024, h: 768 },
  { label: '768×1024 (3:4 竖)', w: 768, h: 1024 },
]

const DEFAULT_PROMPT_SUFFIX = '电影感画面, 写实细节, 高质量插画'
const DEFAULT_NEGATIVE_PROMPT = '低质量, 模糊, 水印, 字幕, 文字'

export default function MultimodalView({ novel }) {
  // ----- 节列表 -----
  const [sections, setSections] = useState([])
  const [sectionsLoading, setSectionsLoading] = useState(false)
  const [selectedKey, setSelectedKey] = useState(null) // "ch-sec"

  // ----- 多模态已有节 (用于左侧角标) -----
  const [multimodalIndex, setMultimodalIndex] = useState({}) // {"ch-sec": item}

  // ----- 当前选中节状态 -----
  const [preview, setPreview] = useState(null) // {source_chars, segments: []}
  const [previewLoading, setPreviewLoading] = useState(false)
  const [manifest, setManifest] = useState(null)
  const [manifestLoading, setManifestLoading] = useState(false)

  // ----- 配置 -----
  const [voices, setVoices] = useState([])
  const [voice, setVoice] = useState('zh-CN-XiaoxiaoNeural')
  const [size, setSize] = useState(SIZE_PRESETS[0])
  const [promptSuffix, setPromptSuffix] = useState(DEFAULT_PROMPT_SUFFIX)
  const [negativePrompt, setNegativePrompt] = useState(DEFAULT_NEGATIVE_PROMPT)

  // ----- 任务 -----
  const [task, setTask] = useState(null)
  const taskControllerRef = useRef(null)
  // 防双击 — handleGenerate 是 async, taskRunning 状态滞后, 中间窗口会双发
  const generatingRef = useRef(false)

  // ----- 资产 blob URL (视频 + 图 + 音) -----
  // key = filename, value = blob URL.
  // 用 ref 同步影像保证 unmount cleanup 拿到最新 map — 否则 useEffect deps=[]
  // 闭包只会捕获初始 {}, 真实分配的 URL 永远不会 revoke → 内存泄漏.
  const [assetUrls, setAssetUrls] = useState({})
  const assetUrlsRef = useRef({})
  useEffect(() => {
    assetUrlsRef.current = assetUrls
  }, [assetUrls])

  useEffect(() => {
    return () => {
      // unmount 全清: blob URLs + SSE controller
      Object.values(assetUrlsRef.current).forEach((u) => {
        try {
          URL.revokeObjectURL(u)
        } catch {
          /* noop */
        }
      })
      if (taskControllerRef.current) {
        try {
          taskControllerRef.current.abort()
        } catch {
          /* noop */
        }
      }
    }
  }, [])

  // ----- 初始化: 拉 voices -----
  useEffect(() => {
    listTTSVoices()
      .then((r) => {
        setVoices(r.voices || [])
        if (r.default) setVoice(r.default)
      })
      .catch((e) => console.warn('listTTSVoices failed', e))
  }, [])

  // ----- novel 切换: 重新拉节列表 -----
  useEffect(() => {
    if (!novel?.id) {
      setSections([])
      setMultimodalIndex({})
      setSelectedKey(null)
      return
    }
    refreshSectionsAndIndex(novel.id)
  }, [novel?.id])

  async function refreshSectionsAndIndex(novelId) {
    setSectionsLoading(true)
    try {
      const [secResp, mmResp] = await Promise.all([
        listTickSections(novelId).catch(() => ({ sections: [] })),
        listMultimodalSections(novelId).catch(() => ({ items: [] })),
      ])
      setSections(secResp.sections || [])
      const idx = {}
      for (const item of mmResp.items || []) {
        idx[`${item.chapter}-${item.section}`] = item
      }
      setMultimodalIndex(idx)
    } catch (e) {
      console.error(e)
    }
    setSectionsLoading(false)
  }

  // ----- 选中节变化: 拉预览 + manifest -----
  const selectedSection = useMemo(() => {
    if (!selectedKey) return null
    return sections.find((s) => `${s.chapter}-${s.section}` === selectedKey) || null
  }, [selectedKey, sections])

  useEffect(() => {
    setPreview(null)
    setManifest(null)
    // 切节时撤销旧 blob URL — 用 ref 拿最新 map, 避免闭包过期
    Object.values(assetUrlsRef.current).forEach((u) => {
      try {
        URL.revokeObjectURL(u)
      } catch {
        /* noop */
      }
    })
    setAssetUrls({})
    if (!selectedSection || !novel?.id) return

    const ns = novel.id
    const { chapter, section } = selectedSection

    // 预览分段
    setPreviewLoading(true)
    previewMultimodalSegments({ novel_id: ns, chapter, section })
      .then(setPreview)
      .catch((e) => {
        showToast(e.message || '预览失败', 'error')
      })
      .finally(() => setPreviewLoading(false))

    // manifest (可能不存在, 404 时返回 null)
    setManifestLoading(true)
    getMultimodalManifest(ns, chapter, section)
      .then(setManifest)
      .catch(() => setManifest(null))
      .finally(() => setManifestLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSection?.chapter, selectedSection?.section, novel?.id])

  // ----- 生成按钮 -----
  async function handleGenerate() {
    if (!novel?.id || !selectedSection) return
    // 防双击 — async + state 更新滞后, 这里用同步 ref 锁
    if (generatingRef.current) return
    const { active, config } = getActiveImageProviderConfig()
    if (active !== 'xfyun') {
      showToast('当前多模态仅支持讯飞图片 — 请到「系统设置」切换为 xfyun', 'error')
      return
    }
    if (!(config.app_id && config.api_key && config.api_secret)) {
      showToast(
        '请先在「系统设置 → 图片生成」填写讯飞 AppID/APIKey/APISecret',
        'error',
      )
      return
    }

    const { chapter, section } = selectedSection
    generatingRef.current = true
    try {
      const snap = await generateMultimodal({
        novel_id: novel.id,
        chapter,
        section,
        voice,
        image_width: size.w,
        image_height: size.h,
        image_prompt_suffix: promptSuffix,
        negative_prompt: negativePrompt,
      })
      setTask(snap)
      // 启动 SSE 监听 — 旧 controller 必须先 abort, 否则会两路同时推
      if (taskControllerRef.current) {
        try { taskControllerRef.current.abort() } catch { /* noop */ }
      }
      taskControllerRef.current = watchTaskStream(snap.id, {
        onSnapshot: (s) => setTask(s),
        onDone: async () => {
          // 任务完成 (无论成败) → 刷新 manifest + 左侧索引
          try {
            const fresh = await getMultimodalManifest(novel.id, chapter, section)
            setManifest(fresh)
          } catch {
            // 失败时 manifest 可能 404, 静默吞 — 错误已显示在 task.error
          }
          refreshSectionsAndIndex(novel.id)
        },
        onError: (e) => {
          showToast(e.message || '任务流断开', 'error')
        },
      })
    } catch (e) {
      showToast(e.message || '创建任务失败', 'error')
    } finally {
      // ref 解锁 — 即使创建任务失败也要复位, 让用户能重试
      generatingRef.current = false
    }
  }

  // ----- 加载视频 / 图 / 音的 blob URL -----
  async function ensureAssetUrl(filename) {
    if (!novel?.id || !selectedSection) return null
    if (assetUrls[filename]) return assetUrls[filename]
    try {
      const url = await fetchMultimodalAssetBlobUrl(
        novel.id,
        selectedSection.chapter,
        selectedSection.section,
        filename,
      )
      setAssetUrls((prev) => ({ ...prev, [filename]: url }))
      return url
    } catch (e) {
      console.warn('加载资产失败', filename, e)
      return null
    }
  }

  // ----- 渲染 -----
  if (!novel) {
    return (
      <div className="empty-state">
        <i className="fas fa-photo-video"></i>
        <p>请先从左侧「我的作品」选择一部小说</p>
      </div>
    )
  }

  const taskRunning =
    task && (task.status === 'queued' || task.status === 'running')

  return (
    <div style={{ display: 'flex', gap: 16, height: '100%' }}>
      {/* ---------------- 左栏: 节列表 ---------------- */}
      <div
        className="card"
        style={{
          width: 280,
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div className="card-title" style={{ marginBottom: 8 }}>
          <i className="fas fa-list" style={{ marginRight: 6 }}></i>
          节列表 ({sections.length})
        </div>
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          {sectionsLoading && (
            <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>加载中…</p>
          )}
          {!sectionsLoading && sections.length === 0 && (
            <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              该作品还没有任何节 — 请先到「创作控制台」生成一节
            </p>
          )}
          {sections.map((s) => {
            const key = `${s.chapter}-${s.section}`
            const mm = multimodalIndex[key]
            const isActive = key === selectedKey
            return (
              <div
                key={key}
                onClick={() => setSelectedKey(key)}
                style={{
                  padding: '8px 10px',
                  marginBottom: 4,
                  borderRadius: 6,
                  cursor: 'pointer',
                  background: isActive
                    ? 'var(--bg-hover, #2a2a3a)'
                    : 'transparent',
                  border: isActive
                    ? '1px solid var(--accent-purple, #8b5cf6)'
                    : '1px solid transparent',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    fontSize: 13,
                  }}
                >
                  <span>
                    第{s.chapter}章 第{s.section}节
                  </span>
                  <MultimodalBadge status={mm?.video_status} />
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: 'var(--text-muted)',
                    marginTop: 2,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {s.title || `${s.word_count || 0} 字`}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ---------------- 右栏: 详情 ---------------- */}
      <div style={{ flex: 1, overflowY: 'auto', minWidth: 0 }}>
        {!selectedSection ? (
          <div className="empty-state">
            <i className="fas fa-arrow-left"></i>
            <p>从左侧选一节, 开始把文字变成视频</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <h2
              style={{
                margin: 0,
                fontSize: 18,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <i
                className="fas fa-photo-video"
                style={{ color: 'var(--accent-purple)' }}
              ></i>
              第{selectedSection.chapter}章 第{selectedSection.section}节 · 多模态
              {selectedSection.title && (
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  · {selectedSection.title}
                </span>
              )}
            </h2>

            <ConfigCard
              voices={voices}
              voice={voice}
              setVoice={setVoice}
              size={size}
              setSize={setSize}
              promptSuffix={promptSuffix}
              setPromptSuffix={setPromptSuffix}
              negativePrompt={negativePrompt}
              setNegativePrompt={setNegativePrompt}
              taskRunning={taskRunning}
              segmentCount={preview?.segments?.length || 0}
              onGenerate={handleGenerate}
              alreadyGenerated={
                manifest && manifest.video_status === 'done'
              }
            />

            {task && <TaskProgressCard task={task} />}

            <PreviewCard
              loading={previewLoading}
              preview={preview}
              manifest={manifest}
            />

            {manifest && (
              <ResultCard
                novel={novel}
                section={selectedSection}
                manifest={manifest}
                assetUrls={assetUrls}
                ensureAssetUrl={ensureAssetUrl}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

function MultimodalBadge({ status }) {
  if (!status) return null
  const map = {
    pending: { label: '待生成', color: 'var(--text-muted, #777)' },
    running: { label: '生成中', color: '#f59e0b' },
    done: { label: '已完成', color: '#10b981' },
    failed: { label: '失败', color: '#ef4444' },
  }
  const m = map[status] || map.pending
  return (
    <span
      style={{
        fontSize: 10,
        color: m.color,
        border: `1px solid ${m.color}`,
        padding: '1px 6px',
        borderRadius: 8,
      }}
    >
      {m.label}
    </span>
  )
}

function ConfigCard({
  voices,
  voice,
  setVoice,
  size,
  setSize,
  promptSuffix,
  setPromptSuffix,
  negativePrompt,
  setNegativePrompt,
  taskRunning,
  segmentCount,
  onGenerate,
  alreadyGenerated,
}) {
  return (
    <div className="card">
      <div className="card-title" style={{ marginBottom: 12 }}>
        <i className="fas fa-sliders-h" style={{ marginRight: 6 }}></i>
        生成配置
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <label style={smallLabel}>TTS 音色</label>
          <select
            className="input-field"
            value={voice}
            onChange={(e) => setVoice(e.target.value)}
            disabled={taskRunning}
          >
            {voices.length === 0 && (
              <option value="zh-CN-XiaoxiaoNeural">晓晓 (女, 温柔)</option>
            )}
            {voices.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label style={smallLabel}>图片尺寸</label>
          <select
            className="input-field"
            value={`${size.w}x${size.h}`}
            onChange={(e) => {
              const found = SIZE_PRESETS.find(
                (p) => `${p.w}x${p.h}` === e.target.value,
              )
              if (found) setSize(found)
            }}
            disabled={taskRunning}
          >
            {SIZE_PRESETS.map((p) => (
              <option key={`${p.w}x${p.h}`} value={`${p.w}x${p.h}`}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div style={{ marginTop: 12 }}>
        <label style={smallLabel}>图片画风后缀 (拼在段落后)</label>
        <input
          className="input-field"
          value={promptSuffix}
          onChange={(e) => setPromptSuffix(e.target.value)}
          disabled={taskRunning}
        />
      </div>

      <div style={{ marginTop: 12 }}>
        <label style={smallLabel}>反向提示词 (不希望出现)</label>
        <input
          className="input-field"
          value={negativePrompt}
          onChange={(e) => setNegativePrompt(e.target.value)}
          disabled={taskRunning}
        />
      </div>

      <div
        style={{
          marginTop: 16,
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}
      >
        <button
          className="btn btn-primary"
          onClick={onGenerate}
          disabled={taskRunning || segmentCount === 0}
        >
          {taskRunning ? (
            <>
              <span className="loading-spinner" style={{ marginRight: 6 }}></span>
              生成中…
            </>
          ) : alreadyGenerated ? (
            <>
              <i className="fas fa-redo" style={{ marginRight: 6 }}></i>
              重新生成
            </>
          ) : (
            <>
              <i className="fas fa-magic" style={{ marginRight: 6 }}></i>
              开始生成 ({segmentCount} 段)
            </>
          )}
        </button>
        {alreadyGenerated && !taskRunning && (
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            重新生成会覆盖现有资产
          </span>
        )}
      </div>
    </div>
  )
}

function TaskProgressCard({ task }) {
  const pct =
    task.progress?.target_words > 0
      ? Math.min(
          100,
          (task.progress.current_words / task.progress.target_words) * 100,
        )
      : 0
  const statusColor = {
    queued: '#94a3b8',
    running: '#f59e0b',
    completed: '#10b981',
    failed: '#ef4444',
    cancelled: '#94a3b8',
  }[task.status]

  return (
    <div className="card">
      <div
        className="card-title"
        style={{
          marginBottom: 8,
          display: 'flex',
          justifyContent: 'space-between',
        }}
      >
        <span>
          <i className="fas fa-cog fa-spin" style={{ marginRight: 6 }}></i>
          任务进度
        </span>
        <span style={{ color: statusColor, fontSize: 12 }}>
          {task.status} · {task.progress?.current_words || 0}/
          {task.progress?.target_words || 0} 段
        </span>
      </div>
      <div
        style={{
          height: 8,
          borderRadius: 4,
          background: 'var(--bg-secondary, #1f2030)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            background: statusColor,
            transition: 'width 200ms ease',
          }}
        />
      </div>
      {task.progress?.last_message && (
        <div
          style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}
        >
          {task.progress.last_message}
        </div>
      )}
      {task.error && (
        <div
          style={{
            marginTop: 8,
            fontSize: 12,
            color: '#ef4444',
            padding: 8,
            background: 'rgba(239, 68, 68, 0.1)',
            borderRadius: 4,
          }}
        >
          {task.error}
        </div>
      )}
    </div>
  )
}

function PreviewCard({ loading, preview, manifest }) {
  if (loading) {
    return (
      <div className="card">
        <p style={{ color: 'var(--text-muted)' }}>分段预览加载中…</p>
      </div>
    )
  }
  if (!preview) return null
  const segs = preview.segments || []
  // 如果 manifest 存在, 用它的段状态;否则纯预览
  const segMap = {}
  if (manifest?.segments) {
    for (const m of manifest.segments) segMap[m.index] = m
  }
  return (
    <div className="card">
      <div
        className="card-title"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          marginBottom: 8,
        }}
      >
        <span>
          <i className="fas fa-cut" style={{ marginRight: 6 }}></i>
          分段预览 ({segs.length} 段)
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          原文 {preview.source_chars} 字
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {segs.map((s) => {
          const stat = segMap[s.index]
          return (
            <div
              key={s.index}
              style={{
                padding: 8,
                background: 'var(--bg-secondary, #1f2030)',
                borderRadius: 6,
                fontSize: 13,
                lineHeight: 1.6,
              }}
            >
              <div
                style={{
                  fontSize: 10,
                  color: 'var(--text-muted)',
                  marginBottom: 4,
                  display: 'flex',
                  justifyContent: 'space-between',
                }}
              >
                <span>段 {s.index + 1} · {s.char_count} 字</span>
                {stat && (
                  <span>
                    <SegStatus label="图" status={stat.image_status} />
                    <SegStatus label="音" status={stat.audio_status} />
                    {stat.duration_ms > 0 && (
                      <span style={{ marginLeft: 4 }}>
                        {(stat.duration_ms / 1000).toFixed(1)}s
                      </span>
                    )}
                  </span>
                )}
              </div>
              <div>{s.text}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function SegStatus({ label, status }) {
  const color = {
    pending: 'var(--text-muted)',
    running: '#f59e0b',
    done: '#10b981',
    failed: '#ef4444',
  }[status] || 'var(--text-muted)'
  const sym = { pending: '○', running: '◐', done: '●', failed: '✕' }[status] || '○'
  return (
    <span style={{ marginLeft: 8, color }}>
      {label}
      {sym}
    </span>
  )
}

function ResultCard({ novel, section, manifest, assetUrls, ensureAssetUrl }) {
  const [videoUrl, setVideoUrl] = useState(null)
  const videoStatus = manifest.video_status
  const videoFn = manifest.video_filename || 'output.mp4'

  useEffect(() => {
    setVideoUrl(null)
    if (videoStatus === 'done') {
      ensureAssetUrl(videoFn).then((u) => setVideoUrl(u))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoStatus, videoFn, section.chapter, section.section])

  return (
    <div className="card">
      <div className="card-title" style={{ marginBottom: 12 }}>
        <i className="fas fa-film" style={{ marginRight: 6 }}></i>
        合成结果
        <MultimodalBadge status={videoStatus} />
      </div>

      {videoStatus === 'failed' && manifest.video_error && (
        <div
          style={{
            padding: 8,
            background: 'rgba(239, 68, 68, 0.1)',
            color: '#ef4444',
            borderRadius: 4,
            fontSize: 12,
            marginBottom: 12,
          }}
        >
          {manifest.video_error}
        </div>
      )}

      {videoStatus === 'done' && videoUrl && (
        <div>
          <video
            src={videoUrl}
            controls
            style={{ width: '100%', borderRadius: 6, background: '#000' }}
          />
          <div style={{ marginTop: 8, display: 'flex', gap: 12 }}>
            <a
              href={videoUrl}
              download={`${novel.title || novel.id}-第${section.chapter}章第${section.section}节.mp4`}
              className="btn btn-secondary"
              style={{ fontSize: 12 }}
            >
              <i className="fas fa-download" style={{ marginRight: 4 }}></i>
              下载视频
            </a>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', alignSelf: 'center' }}>
              {manifest.segments?.length || 0} 段 · {manifest.voice}
            </span>
          </div>
        </div>
      )}

      {videoStatus === 'done' && !videoUrl && (
        <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>
          视频加载中…
        </p>
      )}

      {videoStatus !== 'done' && videoStatus !== 'failed' && (
        <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>
          视频尚未生成 — 配置好后点「开始生成」
        </p>
      )}

      {/* 段级缩略图 + 音频 */}
      {manifest.segments && manifest.segments.length > 0 && (
        <SegmentThumbnails
          manifest={manifest}
          assetUrls={assetUrls}
          ensureAssetUrl={ensureAssetUrl}
        />
      )}
    </div>
  )
}

function SegmentThumbnails({ manifest, assetUrls, ensureAssetUrl }) {
  // 仅展示已 done 的段缩略图
  useEffect(() => {
    for (const seg of manifest.segments) {
      if (seg.image_status === 'done' && seg.image_filename) {
        if (!assetUrls[seg.image_filename]) {
          ensureAssetUrl(seg.image_filename)
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manifest.segments])

  return (
    <div style={{ marginTop: 16 }}>
      <div
        style={{
          fontSize: 12,
          color: 'var(--text-muted)',
          marginBottom: 8,
        }}
      >
        分段缩略图
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
          gap: 8,
        }}
      >
        {manifest.segments.map((seg) => {
          const imgUrl = assetUrls[seg.image_filename]
          return (
            <div
              key={seg.index}
              style={{
                background: 'var(--bg-secondary, #1f2030)',
                borderRadius: 4,
                overflow: 'hidden',
              }}
            >
              {imgUrl ? (
                <img
                  src={imgUrl}
                  alt={`第 ${seg.index + 1} 段插图: ${(seg.text || '').slice(0, 30)}`}
                  style={{ width: '100%', display: 'block', aspectRatio: '1/1', objectFit: 'cover' }}
                />
              ) : (
                <div
                  style={{
                    width: '100%',
                    aspectRatio: '1/1',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 11,
                    color: 'var(--text-muted)',
                  }}
                >
                  {seg.image_status === 'done' ? '加载中…' : seg.image_status}
                </div>
              )}
              <div
                style={{
                  padding: '4px 6px',
                  fontSize: 10,
                  color: 'var(--text-muted)',
                  display: 'flex',
                  justifyContent: 'space-between',
                }}
              >
                <span>段 {seg.index + 1}</span>
                <span>{(seg.duration_ms / 1000).toFixed(1)}s</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

const smallLabel = {
  display: 'block',
  fontSize: 11,
  color: 'var(--text-muted)',
  marginBottom: 4,
}
