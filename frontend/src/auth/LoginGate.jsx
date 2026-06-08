import React, { useState } from 'react'
import {
  authLoginPassword,
  authLoginSendOTP,
  authLoginVerifyOTP,
  authRegisterSendOTP,
  authRegisterVerify,
} from '../services/api'
import { showToast } from '../utils/toast'
import { useAuth } from './AuthContext'

// v2.26 — 全屏遮罩登录/注册卡片. 未登录时挂在 App 顶层覆盖一切.
//
// 模式 (tab):
//   - login_otp: 邮箱 + 验证码登录
//   - login_password: 邮箱 + 密码登录
//   - register: 邮箱注册 (验证码)
//
// 注册成功 / 登录成功 → setSession() 自动关闭遮罩.

const COOLDOWN_SECONDS = 60

function useCooldown() {
  const [remaining, setRemaining] = useState(0)
  React.useEffect(() => {
    if (remaining <= 0) return undefined
    const t = setTimeout(() => setRemaining((r) => r - 1), 1000)
    return () => clearTimeout(t)
  }, [remaining])
  return [remaining, () => setRemaining(COOLDOWN_SECONDS)]
}

export default function LoginGate() {
  const { setSession } = useAuth()
  const [mode, setMode] = useState('login_otp')
  const [email, setEmail] = useState('')
  const [otp, setOtp] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [otpSent, setOtpSent] = useState(false)
  const [cooldown, startCooldown] = useCooldown()

  const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)

  const handleSendOTP = async () => {
    if (!validEmail) {
      showToast('请输入有效邮箱', 'error')
      return
    }
    setBusy(true)
    try {
      if (mode === 'register') {
        await authRegisterSendOTP(email)
      } else {
        await authLoginSendOTP(email)
      }
      setOtpSent(true)
      startCooldown()
      showToast('验证码已发送, 请查收邮件 (5 分钟内有效)', 'success')
    } catch (err) {
      showToast(err.message || '发送失败', 'error')
    } finally {
      setBusy(false)
    }
  }

  const handleVerifyOTP = async () => {
    if (!/^\d{6}$/.test(otp)) {
      showToast('验证码必须是 6 位数字', 'error')
      return
    }
    setBusy(true)
    try {
      const result =
        mode === 'register'
          ? await authRegisterVerify(email, otp)
          : await authLoginVerifyOTP(email, otp)
      setSession(result)
    } catch (err) {
      showToast(err.message || '验证失败', 'error')
    } finally {
      setBusy(false)
    }
  }

  const handlePasswordLogin = async () => {
    if (!validEmail) {
      showToast('请输入有效邮箱', 'error')
      return
    }
    if (password.length < 8) {
      showToast('密码至少 8 位', 'error')
      return
    }
    setBusy(true)
    try {
      const result = await authLoginPassword(email, password)
      setSession(result)
    } catch (err) {
      showToast(err.message || '登录失败', 'error')
    } finally {
      setBusy(false)
    }
  }

  const switchMode = (next) => {
    setMode(next)
    setOtp('')
    setPassword('')
    setOtpSent(false)
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.65)',
        backdropFilter: 'blur(8px)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          width: 'min(420px, calc(100vw - 32px))',
          background: 'var(--bg-card, #1a1d24)',
          border: '1px solid var(--border-subtle, rgba(255,255,255,0.1))',
          borderRadius: 14,
          padding: '28px 32px',
          boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <div
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: 'var(--text-primary, #fff)',
              letterSpacing: 1,
              marginBottom: 4,
            }}
          >
            NovelAuto
          </div>
          <div
            style={{
              fontSize: 12,
              color: 'var(--text-muted, #888)',
            }}
          >
            登录或注册以开始创作
          </div>
        </div>

        {/* Tab 选择 */}
        <div
          style={{
            display: 'flex',
            gap: 4,
            marginBottom: 20,
            padding: 4,
            background: 'rgba(255,255,255,0.04)',
            borderRadius: 8,
          }}
        >
          <TabButton
            active={mode === 'login_otp'}
            onClick={() => switchMode('login_otp')}
          >
            验证码登录
          </TabButton>
          <TabButton
            active={mode === 'login_password'}
            onClick={() => switchMode('login_password')}
          >
            密码登录
          </TabButton>
          <TabButton
            active={mode === 'register'}
            onClick={() => switchMode('register')}
          >
            注册
          </TabButton>
        </div>

        {/* Email 输入 (所有 mode 都需要) */}
        <div style={{ marginBottom: 14 }}>
          <label
            style={{
              display: 'block',
              fontSize: 12,
              color: 'var(--text-muted, #888)',
              marginBottom: 6,
            }}
          >
            邮箱
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            disabled={busy || otpSent}
            autoComplete="email"
            className="input-field"
            style={{ width: '100%' }}
          />
        </div>

        {/* 模式分支 */}
        {mode === 'login_password' ? (
          <>
            <div style={{ marginBottom: 14 }}>
              <label
                style={{
                  display: 'block',
                  fontSize: 12,
                  color: 'var(--text-muted, #888)',
                  marginBottom: 6,
                }}
              >
                密码
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="至少 8 位"
                disabled={busy}
                autoComplete="current-password"
                className="input-field"
                style={{ width: '100%' }}
                onKeyDown={(e) => e.key === 'Enter' && handlePasswordLogin()}
              />
            </div>
            <button
              className="btn btn-primary btn-full"
              onClick={handlePasswordLogin}
              disabled={busy || !validEmail || password.length < 8}
            >
              {busy ? '登录中…' : '登录'}
            </button>
          </>
        ) : (
          <>
            {!otpSent ? (
              <button
                className="btn btn-primary btn-full"
                onClick={handleSendOTP}
                disabled={busy || !validEmail || cooldown > 0}
              >
                {cooldown > 0
                  ? `${cooldown}s 后可重发`
                  : busy
                  ? '发送中…'
                  : '发送验证码'}
              </button>
            ) : (
              <>
                <div style={{ marginBottom: 14 }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: 12,
                      color: 'var(--text-muted, #888)',
                      marginBottom: 6,
                    }}
                  >
                    6 位验证码
                  </label>
                  <input
                    type="text"
                    value={otp}
                    onChange={(e) =>
                      setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))
                    }
                    placeholder="••••••"
                    disabled={busy}
                    autoComplete="one-time-code"
                    inputMode="numeric"
                    className="input-field"
                    style={{
                      width: '100%',
                      letterSpacing: 8,
                      fontSize: 18,
                      textAlign: 'center',
                    }}
                    onKeyDown={(e) => e.key === 'Enter' && handleVerifyOTP()}
                  />
                </div>
                <button
                  className="btn btn-primary btn-full"
                  onClick={handleVerifyOTP}
                  disabled={busy || otp.length !== 6}
                >
                  {busy ? '验证中…' : mode === 'register' ? '完成注册' : '登录'}
                </button>
                <div
                  style={{
                    marginTop: 10,
                    textAlign: 'center',
                    fontSize: 12,
                  }}
                >
                  {cooldown > 0 ? (
                    <span style={{ color: 'var(--text-muted, #888)' }}>
                      {cooldown}s 后可重发
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={handleSendOTP}
                      disabled={busy}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: 'var(--accent-cyan, #06b6d4)',
                        cursor: 'pointer',
                        textDecoration: 'underline',
                      }}
                    >
                      重新发送
                    </button>
                  )}
                </div>
              </>
            )}
          </>
        )}

        <div
          style={{
            marginTop: 20,
            paddingTop: 16,
            borderTop: '1px solid var(--border-subtle, rgba(255,255,255,0.08))',
            fontSize: 11,
            color: 'var(--text-muted, #666)',
            textAlign: 'center',
            lineHeight: 1.6,
          }}
        >
          注册即同意系统会按需缓存您的会话凭据。
          <br />
          默认作品 24h 后自动清理, 设置中可勾选「保存我的作品」永久保留。
        </div>
      </div>
    </div>
  )
}

function TabButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        flex: 1,
        padding: '8px 6px',
        background: active
          ? 'var(--accent-purple, #8b5cf6)'
          : 'transparent',
        color: active ? '#fff' : 'var(--text-muted, #888)',
        border: 'none',
        borderRadius: 6,
        cursor: 'pointer',
        fontSize: 13,
        fontWeight: active ? 600 : 400,
        transition: 'all 0.15s',
      }}
    >
      {children}
    </button>
  )
}
