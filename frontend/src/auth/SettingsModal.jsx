import React, { useEffect, useState } from 'react'
import { authSetPassword, authUpdateSettings } from '../services/api'
import { showToast } from '../utils/toast'
import { useAuth } from './AuthContext'

// v2.27 — 设置弹窗精简版.
// API key (文本 LLM + 图片生成) 已经迁到「系统设置」页面,这里只剩:
//   1. 保存我的作品 (服务端开关)
//   2. 安全 (设置 / 更新密码)
//   3. 退出登录

export default function SettingsModal({ open, onClose }) {
  const { user, refreshUser, logout } = useAuth()

  const [saveMyWorks, setSaveMyWorks] = useState(false)
  const [savingPref, setSavingPref] = useState(false)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [settingPassword, setSettingPassword] = useState(false)

  useEffect(() => {
    if (!open) return
    setSaveMyWorks(Boolean(user?.save_my_works))
    setCurrentPassword('')
    setNewPassword('')
  }, [open, user])

  if (!open) return null

  const handleSavePref = async (next) => {
    setSavingPref(true)
    try {
      await authUpdateSettings({ save_my_works: next })
      setSaveMyWorks(next)
      await refreshUser()
    } catch (err) {
      showToast(err.message || '保存失败', 'error')
      setSaveMyWorks(!next)
    } finally {
      setSavingPref(false)
    }
  }

  const handleSetPassword = async () => {
    if (newPassword.length < 8 || newPassword.length > 128) {
      showToast('密码须 8-128 位', 'error')
      return
    }
    if (user?.has_password && !currentPassword) {
      showToast('请输入当前密码', 'error')
      return
    }
    setSettingPassword(true)
    try {
      await authSetPassword({
        password: newPassword,
        current_password: currentPassword,
      })
      await refreshUser()
      setCurrentPassword('')
      setNewPassword('')
      showToast(user?.has_password ? '密码已更新' : '密码已设置', 'success')
    } catch (err) {
      showToast(err.message || '设置失败', 'error')
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
          width: 'min(440px, 100%)',
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
            marginBottom: 4,
          }}
        >
          <h2 style={{ margin: 0, fontSize: 16 }}>
            <i className="fas fa-user-cog" style={{ marginRight: 8 }}></i>
            账户
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
            aria-label="关闭"
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
          {user?.email}
        </div>

        <SectionBox icon="fa-database" title="保存我的作品">
          <label
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 10,
              cursor: 'pointer',
              padding: '4px 0',
            }}
          >
            <input
              type="checkbox"
              checked={saveMyWorks}
              onChange={(e) => handleSavePref(e.target.checked)}
              disabled={savingPref}
              style={{ marginTop: 3 }}
            />
            <div style={{ fontSize: 13, lineHeight: 1.6 }}>
              {saveMyWorks
                ? '已开启 — 作品永久保留'
                : '未开启 — 24h 未访问的作品会被清理'}
            </div>
          </label>
        </SectionBox>

        <SectionBox
          icon="fa-shield-alt"
          title={user?.has_password ? '更新密码' : '设置密码'}
        >
          {user?.has_password ? (
            <input
              type="password"
              className="input-field"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="当前密码"
              autoComplete="current-password"
              style={{ width: '100%', marginBottom: 8 }}
            />
          ) : null}
          <input
            type="password"
            className="input-field"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder={user?.has_password ? '新密码 8-128 位' : '8-128 位'}
            autoComplete="new-password"
            style={{ width: '100%', marginBottom: 8 }}
          />
          <button
            className="btn btn-primary btn-sm"
            onClick={handleSetPassword}
            disabled={
              settingPassword ||
              newPassword.length < 8 ||
              (user?.has_password && !currentPassword)
            }
          >
            {settingPassword ? '保存中…' : '保存'}
          </button>
        </SectionBox>

        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            marginTop: 16,
            paddingTop: 16,
            borderTop: '1px solid var(--border-subtle, rgba(255,255,255,0.08))',
          }}
        >
          <button
            className="btn btn-danger btn-sm"
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

function SectionBox({ icon, title, children }) {
  return (
    <div
      style={{
        marginBottom: 12,
        padding: 14,
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid var(--border-subtle, rgba(255,255,255,0.06))',
        borderRadius: 8,
      }}
    >
      <div
        style={{
          fontSize: 13,
          fontWeight: 600,
          marginBottom: 8,
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
      {children}
    </div>
  )
}
