import React, { useState } from 'react'
import SettingsModal from './SettingsModal'
import { useAuth } from './AuthContext'

// v2.26 — 右上角浮层: 登录/用户徽章 + 设置按钮.
// 始终可见 — 未登录时显示"登录"按钮 (但 LoginGate 也会全屏覆盖让用户必须登).

export default function TopBar() {
  const { user, hasToken } = useAuth()
  const [settingsOpen, setSettingsOpen] = useState(false)

  return (
    <>
      <div
        style={{
          position: 'fixed',
          top: 12,
          right: 16,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          zIndex: 500,
        }}
      >
        {hasToken && user ? (
          <div
            style={{
              padding: '6px 12px',
              background: 'var(--bg-card, rgba(26,29,36,0.95))',
              border: '1px solid var(--border-subtle, rgba(255,255,255,0.08))',
              borderRadius: 8,
              fontSize: 12,
              color: 'var(--text-secondary, #ccc)',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              maxWidth: 220,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              backdropFilter: 'blur(8px)',
            }}
            title={user.email}
          >
            <i
              className="fas fa-user-circle"
              style={{ color: 'var(--accent-purple, #8b5cf6)' }}
            ></i>
            <span
              style={{
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {user.email}
            </span>
          </div>
        ) : (
          <div
            style={{
              padding: '6px 12px',
              background: 'var(--accent-purple, #8b5cf6)',
              color: '#fff',
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <i className="fas fa-sign-in-alt"></i>
            未登录
          </div>
        )}

        <button
          type="button"
          onClick={() => hasToken && setSettingsOpen(true)}
          disabled={!hasToken}
          title={hasToken ? '设置' : '请先登录'}
          style={{
            width: 36,
            height: 36,
            background: 'var(--bg-card, rgba(26,29,36,0.95))',
            border: '1px solid var(--border-subtle, rgba(255,255,255,0.08))',
            borderRadius: 8,
            color: hasToken ? 'var(--text-secondary, #ccc)' : 'rgba(255,255,255,0.3)',
            cursor: hasToken ? 'pointer' : 'not-allowed',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backdropFilter: 'blur(8px)',
          }}
        >
          <i className="fas fa-cog"></i>
        </button>
      </div>

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
    </>
  )
}
