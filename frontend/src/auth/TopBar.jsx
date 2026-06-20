import React, { useState } from 'react'
import SettingsModal from './SettingsModal'
import { useAuth } from './AuthContext'

// v2.26 — 右上角浮层: 登录/用户徽章 + 设置按钮.
// 始终可见 — 未登录时显示"登录"按钮 (但 LoginGate 也会全屏覆盖让用户必须登).

export default function TopBar() {
  const { user, hasToken } = useAuth()
  const [settingsOpen, setSettingsOpen] = useState(false)

  // v2.46 — LoginGate 的新设计在右上角自带 day/night 切换, 在左侧面板自带品牌块.
  // 未登录时这里再画一个"未登录"胶囊 + 灰色齿轮会与新设计互相挤压. 直接 noop:
  // AuthGated 会让 LoginGate 全屏接管, TopBar 的存在意义只在登录后.
  if (!hasToken || !user) return null

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

        <button
          type="button"
          onClick={() => setSettingsOpen(true)}
          title="设置"
          style={{
            width: 36,
            height: 36,
            background: 'var(--bg-card, rgba(26,29,36,0.95))',
            border: '1px solid var(--border-subtle, rgba(255,255,255,0.08))',
            borderRadius: 8,
            color: 'var(--text-secondary, #ccc)',
            cursor: 'pointer',
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
