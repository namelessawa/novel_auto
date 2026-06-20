import React, { useEffect, useRef, useState } from 'react'
import DayNightToggle from './DayNightToggle'
import { useAuth } from '../auth/AuthContext'
import { avatarLetter, formatTick, safeEmail } from './utils'

// v2.47 — Dashboard 顶栏. 1:1 移植 Novel Auto Dashboard.dc.html 的 <header>.
// 不挂 v2.26 的旧 TopBar — App.jsx 切到新 Shell 后那个不再渲染.

export default function TopBar({
  novels,
  activeNovelId,
  onSwitchNovel,
  onCreateNovel,
  tickStatus,
  onOpenConfig,
  onOpenProfile,
  onOpenSecurity,
}) {
  const { user, logout } = useAuth()
  const [novelOpen, setNovelOpen] = useState(false)
  const [accountOpen, setAccountOpen] = useState(false)
  const novelRef = useRef(null)
  const acctRef = useRef(null)

  useEffect(() => {
    if (!novelOpen && !accountOpen) return undefined
    function onClick(e) {
      if (novelOpen && novelRef.current && !novelRef.current.contains(e.target)) {
        setNovelOpen(false)
      }
      if (accountOpen && acctRef.current && !acctRef.current.contains(e.target)) {
        setAccountOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [novelOpen, accountOpen])

  const active = (novels || []).find((n) => n.id === activeNovelId) || null
  const running = Boolean(tickStatus && !tickStatus.is_paused)
  const currentTick =
    typeof tickStatus?.current_tick === 'number' ? tickStatus.current_tick : 0

  return (
    <header className="dc-topbar">
      {/* Brand */}
      <div className="dc-brand">
        <div className="dc-brand-mark" />
        <div className="dc-brand-text">
          <span className="dc-brand-name">novel_auto</span>
          <span className="dc-brand-tag">V2.47 · MOYAN</span>
        </div>
      </div>

      <div className="dc-divider-vert" />

      {/* Novel switcher */}
      <div className="dc-novel-switch" ref={novelRef}>
        <button
          type="button"
          className="dc-novel-switch-btn"
          onClick={() => setNovelOpen((v) => !v)}
          aria-expanded={novelOpen}
        >
          <span className="dc-novel-switch-name">
            {active?.title || '选择作品'}
          </span>
          {active?.id && (
            <span className="dc-novel-switch-id">{active.id}</span>
          )}
          <svg
            className="dc-novel-switch-caret"
            width="10"
            height="10"
            viewBox="0 0 10 10"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M2 4 L5 7 L8 4"
              stroke="currentColor"
              strokeWidth="1.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity="0.55"
            />
          </svg>
        </button>
        {novelOpen && (
          <div className="dc-novel-pop">
            {(novels || []).length === 0 && (
              <div
                style={{
                  padding: '12px',
                  font: "400 12px/1.5 'Inter', sans-serif",
                  color: 'var(--text3)',
                }}
              >
                还没有作品 — 点新建小说开始
              </div>
            )}
            {(novels || []).map((n) => (
              <div
                key={n.id}
                className={`dc-novel-pop-item ${n.id === activeNovelId ? 'is-active' : ''}`}
                onClick={() => {
                  onSwitchNovel?.(n.id)
                  setNovelOpen(false)
                }}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    onSwitchNovel?.(n.id)
                    setNovelOpen(false)
                  }
                }}
              >
                <span className="dc-novel-pop-item-bar" />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1, minWidth: 0 }}>
                  <span className="dc-novel-pop-item-title">
                    {n.title || n.id}
                  </span>
                  <span className="dc-novel-pop-item-meta">
                    {n.id}
                    {typeof n.current_tick === 'number' && ` · ${n.current_tick} tick`}
                  </span>
                </div>
              </div>
            ))}
            <div className="dc-account-sep" />
            <button
              type="button"
              className="dc-sb-novel-add"
              style={{ marginTop: 0 }}
              onClick={() => {
                setNovelOpen(false)
                onCreateNovel?.()
              }}
            >
              <span className="dc-sb-novel-add-plus">+</span>
              <span>新建小说</span>
            </button>
          </div>
        )}
      </div>

      {/* Tick clock pill */}
      <div className="dc-tickclock">
        <div className="dc-tickclock-dot">
          {running ? (
            <>
              <span className="dc-tickclock-dot-run" />
              <span className="dc-tickclock-dot-halo" />
            </>
          ) : (
            <span className="dc-tickclock-dot-idle" />
          )}
        </div>
        <span className="dc-tickclock-kicker">TICK</span>
        <span className="dc-tickclock-num">{formatTick(currentTick)}</span>
      </div>

      <div className="dc-topbar-right">
        <a
          className="dc-topbar-link"
          href="/docs"
          target="_blank"
          rel="noreferrer noopener"
        >
          文档
        </a>
        <a
          className="dc-topbar-link"
          href="https://github.com/namelessawa/novel_auto/blob/main/CHANGELOG.md"
          target="_blank"
          rel="noreferrer noopener"
        >
          CHANGELOG
        </a>
        <a
          className="dc-topbar-link"
          href="https://github.com/namelessawa/novel_auto"
          target="_blank"
          rel="noreferrer noopener"
        >
          GitHub
        </a>

        <DayNightToggle />

        <div className="dc-divider-vert" style={{ height: 20 }} />

        <div ref={acctRef} style={{ position: 'relative' }}>
          <button
            type="button"
            className="dc-account-btn"
            onClick={() => setAccountOpen((v) => !v)}
            title="账户"
            aria-label="账户"
            aria-expanded={accountOpen}
          >
            {avatarLetter(user)}
          </button>
          {accountOpen && (
            <div className="dc-account-pop">
              <div className="dc-account-pop-id">
                <div className="dc-account-pop-avatar">{avatarLetter(user)}</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 }}>
                  <span className="dc-account-pop-name">
                    {user?.display_name || safeEmail(user) || '未登录'}
                  </span>
                  <span className="dc-account-pop-mail">
                    {safeEmail(user)}
                  </span>
                </div>
              </div>
              <div className="dc-account-menu">
                <button
                  type="button"
                  className="dc-account-item"
                  onClick={() => {
                    setAccountOpen(false)
                    onOpenProfile?.()
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="5.2" r="2.6" stroke="currentColor" strokeWidth="1.3" />
                    <path
                      d="M3 13 C3 10.4 5.2 9 8 9 C10.8 9 13 10.4 13 13"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinecap="round"
                    />
                  </svg>
                  个人资料
                </button>
                <button
                  type="button"
                  className="dc-account-item"
                  onClick={() => {
                    setAccountOpen(false)
                    onOpenSecurity?.()
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path
                      d="M8 1.6 L13 3.6 V8 C13 11 10.8 13.2 8 14.4 C5.2 13.2 3 11 3 8 V3.6 Z"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinejoin="round"
                    />
                    <path
                      d="M5.8 8 L7.3 9.5 L10.2 6.4"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  账户与安全
                </button>
                <button
                  type="button"
                  className="dc-account-item"
                  onClick={() => {
                    setAccountOpen(false)
                    onOpenConfig?.()
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="2.2" stroke="currentColor" strokeWidth="1.3" />
                    <path
                      d="M8 1.5 V3 M8 13 V14.5 M14.5 8 H13 M3 8 H1.5 M12.6 3.4 L11.5 4.5 M4.5 11.5 L3.4 12.6 M12.6 12.6 L11.5 11.5 M4.5 4.5 L3.4 3.4"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinecap="round"
                    />
                  </svg>
                  系统配置
                </button>
              </div>
              <div className="dc-account-sep" />
              <div className="dc-account-menu">
                <button
                  type="button"
                  className="dc-account-item dc-account-item-danger"
                  onClick={async () => {
                    setAccountOpen(false)
                    await logout()
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path
                      d="M9.5 11 V12.5 C9.5 13 9 13.5 8.5 13.5 H3.5 C3 13.5 2.5 13 2.5 12.5 V3.5 C2.5 3 3 2.5 3.5 2.5 H8.5 C9 2.5 9.5 3 9.5 3.5 V5"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    <path
                      d="M6.5 8 H14 M14 8 L11.5 5.6 M14 8 L11.5 10.4"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  退出登录
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
