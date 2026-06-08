import React, { useState } from 'react'
import {
  generateImage,
  getActiveImageProviderConfig,
} from '../services/api'
import { showToast } from '../utils/toast'

// v2.28 — 多模态生成: 占位文生图.
// 暂不接入小说内容, 单纯文本输入 → 图片输出, 让用户先把凭据跑通.
// 凭据从「系统设置」localStorage 读, 不在后端持久化.

const PRESETS = [
  { label: '512×512 (方形)', w: 512, h: 512 },
  { label: '768×768 (方形 HD)', w: 768, h: 768 },
  { label: '1024×576 (16:9)', w: 1024, h: 576 },
  { label: '576×1024 (9:16)', w: 576, h: 1024 },
]

export default function MultimodalView() {
  const [prompt, setPrompt] = useState('')
  const [size, setSize] = useState(PRESETS[0])
  const [busy, setBusy] = useState(false)
  const [image, setImage] = useState(null)

  const handleGenerate = async () => {
    if (!prompt.trim()) return
    const { active, config } = getActiveImageProviderConfig()
    if (active === 'xfyun' && !(config.app_id && config.api_key && config.api_secret)) {
      showToast('请先在「系统设置 → 图片生成」填写讯飞 AppID/APIKey/APISecret', 'error')
      return
    }
    if (active !== 'xfyun' && !config.api_key) {
      showToast('请先在「系统设置 → 图片生成」填写 API Key', 'error')
      return
    }
    setBusy(true)
    setImage(null)
    try {
      const r = await generateImage({
        prompt: prompt.trim(),
        width: size.w,
        height: size.h,
      })
      setImage(r)
    } catch (err) {
      showToast(err.message || '生成失败', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      style={{
        maxWidth: 720,
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
      }}
    >
      <h2
        style={{
          margin: 0,
          fontSize: 18,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <i className="fas fa-image" style={{ color: 'var(--accent-purple)' }}></i>
        多模态生成
        <span
          style={{
            fontSize: 11,
            color: 'var(--text-muted)',
            fontWeight: 400,
            marginLeft: 4,
          }}
        >
          文生图占位 — 后续接入章节插图 / 封面
        </span>
      </h2>

      <div className="card">
        <label
          style={{
            display: 'block',
            fontSize: 12,
            color: 'var(--text-muted)',
            marginBottom: 6,
          }}
        >
          提示词
        </label>
        <textarea
          className="input-field"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="例如: 雪山下的古老村落, 黄昏, 油画风格"
          style={{ minHeight: 88, marginBottom: 12 }}
          disabled={busy}
        />

        <label
          style={{
            display: 'block',
            fontSize: 12,
            color: 'var(--text-muted)',
            marginBottom: 6,
          }}
        >
          尺寸
        </label>
        <select
          className="input-field"
          value={`${size.w}x${size.h}`}
          onChange={(e) => {
            const found = PRESETS.find(
              (p) => `${p.w}x${p.h}` === e.target.value,
            )
            if (found) setSize(found)
          }}
          disabled={busy}
          style={{ marginBottom: 12 }}
        >
          {PRESETS.map((p) => (
            <option key={`${p.w}x${p.h}`} value={`${p.w}x${p.h}`}>
              {p.label}
            </option>
          ))}
        </select>

        <button
          className="btn btn-primary"
          onClick={handleGenerate}
          disabled={busy || !prompt.trim()}
        >
          {busy ? (
            <>
              <span className="loading-spinner" style={{ marginRight: 6 }}></span>
              生成中…
            </>
          ) : (
            <>
              <i className="fas fa-magic" style={{ marginRight: 6 }}></i>
              生成图片
            </>
          )}
        </button>
      </div>

      {image && (
        <div className="card">
          <img
            src={`data:${image.mime_type};base64,${image.image_base64}`}
            alt="生成结果"
            style={{
              width: '100%',
              borderRadius: 8,
              display: 'block',
            }}
          />
          <div
            style={{
              fontSize: 11,
              color: 'var(--text-muted)',
              marginTop: 8,
              display: 'flex',
              justifyContent: 'space-between',
            }}
          >
            <span>provider: {image.provider}</span>
            <a
              href={`data:${image.mime_type};base64,${image.image_base64}`}
              download="generated.png"
              style={{ color: 'var(--accent-cyan)' }}
            >
              <i className="fas fa-download" style={{ marginRight: 4 }}></i>
              下载
            </a>
          </div>
        </div>
      )}
    </div>
  )
}
