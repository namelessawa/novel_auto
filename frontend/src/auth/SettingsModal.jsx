import React, { useEffect, useState } from 'react'
import {
  authSetPassword,
  authUpdateSettings,
  getUserLLMConfig,
  setUserLLMConfig,
} from '../services/api'
import { showToast } from '../utils/toast'
import { useAuth } from './AuthContext'

// v2.26 — 用户设置面板.
//
// 3 个 section:
//   1. 个人 LLM API 配置 (localStorage, 不上服务端)
//   2. 数据保存 ("保存我的作品" 开关, PUT /api/auth/me/settings)
//   3. 安全 (设置/更新密码, POST /api/auth/me/set-password)

export default function SettingsModal({ open, onClose }) {
  const { user, refreshUser, logout } = useAuth()

  // LLM 配置 (本地存储)
  const [llmKey, setLlmKey] = useState('')
  const [llmBaseUrl, setLlmBaseUrl] = useState('')
  const [llmModel, setLlmModel] = useState('')

  // save_my_works 开关
  const [saveMyWorks, setSaveMyWorks] = useState(false)
  const [savingPref, setSavingPref] = useState(false)

  // 密码
  const [newPassword, setNewPassword] = useState('')
  const [settingPassword, setSettingPassword] = useState(false)

  useEffect(() => {
    if (!open) return
    const c = getUserLLMConfig()
    setLlmKey(c.api_key || '')
    setLlmBaseUrl(c.base_url || '')
    setLlmModel(c.model || '')
    setSaveMyWorks(Boolean(user?.save_my_works))
    setNewPassword('')
  }, [open, user])

  if (!open) return null

  const handleSaveLLM = () => {
    setUserLLMConfig({
      api_key: llmKey.trim(),
      base_url: llmBaseUrl.trim(),
      model: llmModel.trim(),
    })
    showToast('API 配置已保存到本地浏览器', 'success')
  }

  const handleSavePref = async (next) => {
    setSavingPref(true)
    try {
      await authUpdateSettings({ save_my_works: next })
      setSaveMyWorks(next)
      await refreshUser()
      showToast(
        next
          ? '已开启永久保存 — 作品不会被自动清理'
          : '已关闭 — 24h 未访问的作品将被自动清理',
        'success',
      )
    } catch (err) {
      showToast(err.message || '保存失败', 'error')
      setSaveMyWorks(!next)
    } finally {
      setSavingPref(false)
    }
  }

  const handleSetPassword = async () => {
    if (newPassword.length < 8) {
      showToast('密码至少 8 位', 'error')
      return
    }
    if (newPassword.length > 128) {
      showToast('密码最多 128 位', 'error')
      return
    }
    setSettingPassword(true)
    try {
      await authSetPassword(newPassword)
      await refreshUser()
      setNewPassword('')
      showToast(
        user?.has_password ? '密码已更新' : '密码已设置, 之后可用密码登录',
        'success',
      )
    } catch (err) {
      showToast(err.message || '密码设置失败', 'error')
    } finally {
      setSettingPassword(false)
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        backdropFilter: 'blur(4px)',
        zIndex: 900,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(560px, 100%)',
          maxHeight: 'calc(100vh - 32px)',
          overflowY: 'auto',
          background: 'var(--bg-card, #1a1d24)',
          border: '1px solid var(--border-subtle, rgba(255,255,255,0.1))',
          borderRadius: 12,
          padding: 24,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 8,
          }}
        >
          <h2 style={{ margin: 0, fontSize: 18 }}>
            <i className="fas fa-sliders-h" style={{ marginRight: 8 }}></i>
            设置
          </h2>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-muted, #888)',
              cursor: 'pointer',
              fontSize: 18,
            }}
          >
            <i className="fas fa-times"></i>
          </button>
        </div>
        <div
          style={{
            fontSize: 12,
            color: 'var(--text-muted, #888)',
            marginBottom: 20,
          }}
        >
          已登录: {user?.email}
        </div>

        {/* ---- API 配置 ---- */}
        <SectionBox
          icon="fa-key"
          title="个人 LLM API 配置"
          subtitle="保存在浏览器 localStorage, 永远不上传到服务端。用于随机生成种子/标题等功能。"
        >
          <Field label="API Key">
            <input
              type="password"
              className="input-field"
              value={llmKey}
              onChange={(e) => setLlmKey(e.target.value)}
              placeholder="sk-..."
              style={{ width: '100%' }}
            />
          </Field>
          <Field label="Base URL (可选, 默认 deepseek)">
            <input
              type="text"
              className="input-field"
              value={llmBaseUrl}
              onChange={(e) => setLlmBaseUrl(e.target.value)}
              placeholder="https://api.deepseek.com"
              style={{ width: '100%' }}
            />
          </Field>
          <Field label="Model (可选)">
            <input
              type="text"
              className="input-field"
              value={llmModel}
              onChange={(e) => setLlmModel(e.target.value)}
              placeholder="deepseek-chat"
              style={{ width: '100%' }}
            />
          </Field>
          <button
            className="btn btn-primary"
            onClick={handleSaveLLM}
            style={{ marginTop: 4 }}
          >
            保存到本地
          </button>
        </SectionBox>

        {/* ---- 数据保存 ---- */}
        <SectionBox
          icon="fa-database"
          title="数据保存"
          subtitle="默认作品 24 小时未访问会被自动清理。勾选下方开关后, 您的作品会永久保留在服务端。"
        >
          <label
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 10,
              cursor: 'pointer',
              padding: '8px 0',
            }}
          >
            <input
              type="checkbox"
              checked={saveMyWorks}
              onChange={(e) => handleSavePref(e.target.checked)}
              disabled={savingPref}
              style={{ marginTop: 4 }}
            />
            <div>
              <div style={{ fontSize: 14, fontWeight: 500 }}>
                保存我的作品 <span style={{ color: 'var(--text-muted, #888)', fontSize: 12, fontWeight: 400 }}>
                  (不用于任何用途, 仅供保存)
                </span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted, #888)', marginTop: 4, lineHeight: 1.6 }}>
                {saveMyWorks
                  ? '已开启 — 您的作品永久保留在服务端。'
                  : '未开启 — 24h 未访问的作品会被自动清理。'}
              </div>
            </div>
          </label>
        </SectionBox>

        {/* ---- 安全 ---- */}
        <SectionBox
          icon="fa-shield-alt"
          title={user?.has_password ? '更新密码' : '设置密码 (可选)'}
          subtitle={
            user?.has_password
              ? '更新后请用新密码登录。'
              : '设置密码后, 除了验证码登录, 也可以使用密码登录。'
          }
        >
          <Field label="新密码">
            <input
              type="password"
              className="input-field"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="8-128 位"
              style={{ width: '100%' }}
            />
          </Field>
          <button
            className="btn btn-primary"
            onClick={handleSetPassword}
            disabled={settingPassword || newPassword.length < 8}
            style={{ marginTop: 4 }}
          >
            {settingPassword
              ? '保存中…'
              : user?.has_password
              ? '更新密码'
              : '设置密码'}
          </button>
        </SectionBox>

        {/* ---- 退出 ---- */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
            marginTop: 16,
            paddingTop: 16,
            borderTop: '1px solid var(--border-subtle, rgba(255,255,255,0.08))',
          }}
        >
          <button
            className="btn btn-danger"
            onClick={async () => {
              await logout()
              onClose()
            }}
          >
            <i className="fas fa-sign-out-alt" style={{ marginRight: 6 }}></i>
            退出登录
          </button>
        </div>
      </div>
    </div>
  )
}

function SectionBox({ icon, title, subtitle, children }) {
  return (
    <div
      style={{
        marginBottom: 16,
        padding: 16,
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid var(--border-subtle, rgba(255,255,255,0.06))',
        borderRadius: 10,
      }}
    >
      <div
        style={{
          fontSize: 14,
          fontWeight: 600,
          marginBottom: 4,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <i
          className={`fas ${icon}`}
          style={{ color: 'var(--accent-purple, #8b5cf6)' }}
        ></i>
        {title}
      </div>
      {subtitle && (
        <div
          style={{
            fontSize: 11,
            color: 'var(--text-muted, #888)',
            marginBottom: 12,
            lineHeight: 1.6,
          }}
        >
          {subtitle}
        </div>
      )}
      {children}
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <label
        style={{
          display: 'block',
          fontSize: 11,
          color: 'var(--text-muted, #888)',
          marginBottom: 4,
        }}
      >
        {label}
      </label>
      {children}
    </div>
  )
}
