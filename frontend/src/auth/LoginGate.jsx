import React, { useEffect, useRef, useState } from 'react'
import './LoginGate.css'
import {
  authLoginPassword,
  authLoginSendOTP,
  authLoginVerifyOTP,
  authRegisterSendOTP,
  authRegisterVerify,
} from '../services/api'
import { showToast } from '../utils/toast'
import { useAuth } from './AuthContext'

// v2.46 — 全新 LoginGate, 直译自 claude.ai/design 项目「小说自动化前端页面」
// 中 Novel Auto Login.dc.html 的视觉与交互. 三模式 (验证码登录 / 密码登录 /
// 注册) 共用同一邮箱 + 60s 冷却 + 6 位 OTP, 接 backend.auth.routes 的 5 个端点.
//
// 与旧版 (v2.26 的居中卡片) 的差异:
//   - 左 46% 文学纸面 + 右表单, 760px 以下文学侧自动隐藏
//   - 顶部右侧 jh3y Day/Night 切换 (太阳⇄月亮 + 云⇄星 + 月球坑)
//   - 登录成功瞬间不直接跳走, 渲染 ~1.2s 的 SESSION OPEN 反馈再 setSession()
//   - 主题写到 html[data-theme="dark"], LoginGate 卸载时清理, 不污染 AppShell

const COOLDOWN_SECONDS = 60
const THEME_KEY = 'na_login_theme'
const SUCCESS_TRANSITION_MS = 1200

function readInitialTheme() {
  try {
    const v = localStorage.getItem(THEME_KEY)
    if (v === 'dark' || v === 'light') return v
  } catch {
    /* localStorage blocked — fall through */
  }
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light'
  }
  return 'light'
}

function applyTheme(t) {
  const root = document.documentElement
  if (t === 'dark') root.setAttribute('data-theme', 'dark')
  else root.removeAttribute('data-theme')
}

function useCooldown() {
  const [remaining, setRemaining] = useState(0)
  useEffect(() => {
    if (remaining <= 0) return undefined
    const t = setTimeout(() => setRemaining((r) => r - 1), 1000)
    return () => clearTimeout(t)
  }, [remaining])
  return [remaining, () => setRemaining(COOLDOWN_SECONDS)]
}

const KNOB_STYLE_LIGHT = {
  transform: 'translateX(0px)',
  background:
    'radial-gradient(circle at 35% 30%, #FFE89B, #FFC93C 70%)',
  boxShadow:
    '0 0 10px 2px rgba(255,201,60,0.65), 0 1px 2px rgba(120,80,0,0.25)',
}
const KNOB_STYLE_DARK = {
  transform: 'translateX(54px)',
  background:
    'radial-gradient(circle at 35% 30%, #F2F0E6, #CFCDC0 75%)',
  boxShadow:
    'inset -6px -3px 0 0 rgba(150,148,138,0.55), 0 0 8px 1px rgba(220,222,235,0.4), 0 1px 2px rgba(0,0,20,0.4)',
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
  const [theme, setTheme] = useState(() => readInitialTheme())
  // done = null | { title, msg } — 成功面板的内容
  const [done, setDone] = useState(null)
  // SESSION OPEN 渐出 → setSession 的定时器, 让 ← 返回登录 能真正取消
  const sessionTimerRef = useRef(null)

  // 主题写入 html 根 + 持久化
  useEffect(() => {
    applyTheme(theme)
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      /* private mode etc — silent */
    }
  }, [theme])

  // 卸载时清掉 data-theme — AppShell 用 global.css 单一深色, 不需要这个属性
  useEffect(
    () => () => {
      try {
        document.documentElement.removeAttribute('data-theme')
      } catch {
        /* SSR safe */
      }
    },
    [],
  )

  const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
  const isOtp = mode === 'login_otp'
  const isPw = mode === 'login_password'
  const isReg = mode === 'register'
  const otpMode = isOtp || isReg

  const toggleTheme = () =>
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'))

  const switchMode = (next) => {
    if (next === mode) return
    setMode(next)
    setOtp('')
    setPassword('')
    setOtpSent(false)
  }

  // 登录/注册成功 — 先渲染 SESSION OPEN 面板, 再短暂延迟交给 AuthContext.
  // 用 ref 存 timer id, 让 onBack 能取消 (否则点了"返回登录"也只是延迟一下又进 app).
  const completeWith = (result, registered) => {
    setDone({
      title: registered ? '账户已创建' : '欢迎回来',
      msg: registered
        ? '注册成功, 正在进入工作台并初始化你的第一个世界。'
        : '登录成功, 正在恢复你的小说与上下文。',
    })
    if (sessionTimerRef.current) clearTimeout(sessionTimerRef.current)
    sessionTimerRef.current = setTimeout(() => {
      sessionTimerRef.current = null
      setSession(result)
    }, SUCCESS_TRANSITION_MS)
  }

  // 组件卸载兜底 — AppShell 接管后定时器若仍在排队, 取消防 setState-after-unmount
  useEffect(
    () => () => {
      if (sessionTimerRef.current) {
        clearTimeout(sessionTimerRef.current)
        sessionTimerRef.current = null
      }
    },
    [],
  )

  const handleSendOTP = async () => {
    if (!validEmail) {
      showToast('请输入有效邮箱', 'error')
      return
    }
    setBusy(true)
    try {
      if (isReg) await authRegisterSendOTP(email)
      else await authLoginSendOTP(email)
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
      const result = isReg
        ? await authRegisterVerify(email, otp)
        : await authLoginVerifyOTP(email, otp)
      completeWith(result, isReg)
    } catch (err) {
      showToast(err.message || '验证失败', 'error')
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
      completeWith(result, false)
    } catch (err) {
      showToast(err.message || '登录失败', 'error')
      setBusy(false)
    }
  }

  return (
    <div className="na-login-root" role="dialog" aria-modal="true" aria-label="登录或注册">
      <LiteraryPanel />
      <main className="na-main">
        <ThemeToggle theme={theme} onToggle={toggleTheme} />
        <div className="na-form-inner">
          <CompactBrand />
          {done ? (
            <SuccessPanel
              email={email}
              title={done.title}
              msg={done.msg}
              onBack={() => {
                // 真正取消进入工作台 — 清掉排队中的 setSession 并重置 busy/done
                if (sessionTimerRef.current) {
                  clearTimeout(sessionTimerRef.current)
                  sessionTimerRef.current = null
                }
                setDone(null)
                setBusy(false)
              }}
            />
          ) : (
            <FormBody
              mode={mode}
              switchMode={switchMode}
              email={email}
              setEmail={setEmail}
              password={password}
              setPassword={setPassword}
              otp={otp}
              setOtp={setOtp}
              busy={busy}
              otpSent={otpSent}
              cooldown={cooldown}
              validEmail={validEmail}
              isOtp={isOtp}
              isPw={isPw}
              isReg={isReg}
              otpMode={otpMode}
              onSendOTP={handleSendOTP}
              onVerifyOTP={handleVerifyOTP}
              onPasswordLogin={handlePasswordLogin}
            />
          )}
        </div>
      </main>
    </div>
  )
}

// ════════════════ 文学侧 ════════════════
function LiteraryPanel() {
  return (
    <aside className="na-aside" aria-hidden="true">
      <div className="na-aside-watermark">山</div>

      <div className="na-brand">
        <div className="na-brand-square">
          <div className="na-brand-square-dot" />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span className="na-brand-name">novel_auto</span>
          <span className="na-brand-ver">V2.46 · MOYAN</span>
        </div>
      </div>

      <div
        style={{
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          gap: 30,
          maxWidth: 440,
        }}
      >
        <div className="na-kicker">
          <span className="na-kicker-bar" />
          <span className="na-kicker-text">THE STORY IS A BYPRODUCT</span>
        </div>

        <h1 className="na-hero">
          故事,是模拟<br />世界的副产品
          <span className="na-hero-period">。</span>
        </h1>

        <p className="na-quote">
          她在十字路口勒住马,雪线之下三里地。山雾把后方的马蹄声裹住了,
          似有似无——昨夜火塘旁,老兵把一枚铜符压进她掌心,只说了半句话。
        </p>

        <div className="na-chips">
          <span className="na-chip na-chip-red">10 AGENT</span>
          <span className="na-chip">7 阶段 TICK</span>
          <span className="na-chip">选择性叙述</span>
        </div>
      </div>

      <div className="na-aside-meta">
        <span>
          575 tests <span className="na-green">GREEN</span>
        </span>
        <span className="na-sep">·</span>
        <span>
          tokens <span style={{ color: 'var(--na-as-fg)' }}>−77%</span>
        </span>
      </div>
    </aside>
  )
}

// ════════════════ 紧凑品牌 (小屏文学侧隐藏时出现) ════════════════
function CompactBrand() {
  return (
    <div className="na-compact-brand">
      <div className="na-brand-square">
        <div className="na-brand-square-dot" />
      </div>
      <span className="na-brand-name">novel_auto</span>
      <span className="na-brand-ver">V2.46</span>
    </div>
  )
}

// ════════════════ jh3y 日夜切换 ════════════════
function ThemeToggle({ theme, onToggle }) {
  const isDark = theme === 'dark'
  return (
    <button
      type="button"
      className="na-toggle"
      onClick={onToggle}
      title={isDark ? '切换到日间' : '切换到夜间'}
      aria-label={isDark ? '切换到日间' : '切换到夜间'}
      aria-pressed={isDark}
    >
      <span className="na-tgl-sky">
        <span className="na-tgl-cloud na-tgl-c1" />
        <span className="na-tgl-cloud na-tgl-c2" />
        <span className="na-tgl-cloud na-tgl-c3" />
        <span className="na-tgl-star na-tgl-s1" />
        <span className="na-tgl-star na-tgl-s2" />
        <span className="na-tgl-star na-tgl-s3" />
        <span className="na-tgl-star na-tgl-s4" />
      </span>
      <span
        className="na-knob"
        style={isDark ? KNOB_STYLE_DARK : KNOB_STYLE_LIGHT}
      >
        <span className="na-tgl-crater na-tgl-k1" />
        <span className="na-tgl-crater na-tgl-k2" />
        <span className="na-tgl-crater na-tgl-k3" />
      </span>
    </button>
  )
}

// ════════════════ 表单主体 ════════════════
function FormBody({
  mode,
  switchMode,
  email,
  setEmail,
  password,
  setPassword,
  otp,
  setOtp,
  busy,
  otpSent,
  cooldown,
  validEmail,
  isOtp,
  isPw,
  isReg,
  otpMode,
  onSendOTP,
  onVerifyOTP,
  onPasswordLogin,
}) {
  const heading = isReg ? '创建账户' : '欢迎回来'
  const sub = isReg
    ? '邮箱验证 · 一分钟完成注册'
    : isPw
    ? '使用邮箱与密码登录'
    : '使用邮箱验证码登录'

  const emailLock = otpMode && otpSent

  return (
    <div className="na-block">
      <div className="na-heading-group">
        <div className="na-kicker">
          <span className="na-kicker-bar" />
          <span className="na-kicker-text">ACCESS</span>
        </div>
        <div className="na-heading-text">
          <h2 className="na-heading">{heading}</h2>
          <p className="na-sub">{sub}</p>
        </div>
      </div>

      <div className="na-tabs" role="tablist">
        <Tab
          active={isOtp}
          onClick={() => switchMode('login_otp')}
          label="验证码登录"
        />
        <Tab
          active={isPw}
          onClick={() => switchMode('login_password')}
          label="密码登录"
        />
        <Tab
          active={isReg}
          onClick={() => switchMode('register')}
          label="注册"
          variant="register"
        />
      </div>

      <div className="na-field-group">
        <label className="na-label" htmlFor="na-email">
          邮箱 · EMAIL
        </label>
        <input
          id="na-email"
          className="na-field"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          disabled={emailLock || busy}
          autoComplete="email"
          autoFocus
          onKeyDown={(e) => {
            if (e.key !== 'Enter') return
            if (isPw) onPasswordLogin()
            else if (!otpSent) onSendOTP()
          }}
        />
      </div>

      {isPw && (
        <PasswordBlock
          password={password}
          setPassword={setPassword}
          busy={busy}
          validEmail={validEmail}
          onSubmit={onPasswordLogin}
        />
      )}

      {otpMode && !otpSent && (
        <SendOtpBlock
          busy={busy}
          validEmail={validEmail}
          cooldown={cooldown}
          onSend={onSendOTP}
        />
      )}

      {otpMode && otpSent && (
        <VerifyOtpBlock
          email={email}
          otp={otp}
          setOtp={setOtp}
          busy={busy}
          isReg={isReg}
          cooldown={cooldown}
          onVerify={onVerifyOTP}
          onResend={onSendOTP}
        />
      )}

      <div className="na-footer-note">
        继续即表示同意系统按需缓存会话凭据。默认作品 24h 后自动清理,
        <br />
        设置中可勾选「保存我的作品」永久保留。
      </div>
    </div>
  )
}

function Tab({ active, onClick, label, variant }) {
  const cls = [
    'na-tab',
    active ? 'na-tab-active' : '',
    variant === 'register' ? 'na-tab-register' : '',
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <button
      type="button"
      className={cls}
      onClick={onClick}
      role="tab"
      aria-selected={active}
    >
      {label}
    </button>
  )
}

function PasswordBlock({ password, setPassword, busy, validEmail, onSubmit }) {
  return (
    <div
      className="na-fade-in"
      style={{ display: 'flex', flexDirection: 'column', gap: 18 }}
    >
      <div className="na-field-group">
        <div className="na-field-row">
          <label className="na-label" htmlFor="na-password">
            密码 · PASSWORD
          </label>
          <span className="na-hint">至少 8 位</span>
        </div>
        <input
          id="na-password"
          className="na-field"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          autoComplete="current-password"
          disabled={busy}
          onKeyDown={(e) => e.key === 'Enter' && onSubmit()}
        />
      </div>
      <button
        type="button"
        className="na-btn-primary"
        onClick={onSubmit}
        disabled={busy || !validEmail || password.length < 8}
      >
        {busy ? '登录中…' : '登录'}
      </button>
    </div>
  )
}

function SendOtpBlock({ busy, validEmail, cooldown, onSend }) {
  const label =
    cooldown > 0
      ? `${cooldown}s 后可重发`
      : busy
      ? '发送中…'
      : '发送验证码'
  return (
    <div
      className="na-fade-in"
      style={{ display: 'flex', flexDirection: 'column', gap: 14 }}
    >
      <button
        type="button"
        className="na-btn-primary"
        onClick={onSend}
        disabled={busy || !validEmail || cooldown > 0}
      >
        {label}
      </button>
      <p className="na-otp-helper">
        验证码将发送至上方邮箱, 5 分钟内有效
      </p>
    </div>
  )
}

function VerifyOtpBlock({
  email,
  otp,
  setOtp,
  busy,
  isReg,
  cooldown,
  onVerify,
  onResend,
}) {
  const verifyLabel = busy
    ? '验证中…'
    : isReg
    ? '完成注册'
    : '登录'
  return (
    <div
      className="na-fade-in"
      style={{ display: 'flex', flexDirection: 'column', gap: 18 }}
    >
      <div className="na-field-group">
        <label className="na-label" htmlFor="na-otp">
          6 位验证码 · OTP
        </label>
        <input
          id="na-otp"
          className="na-field na-field-otp"
          type="text"
          value={otp}
          onChange={(e) =>
            setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))
          }
          placeholder="••••••"
          inputMode="numeric"
          autoComplete="one-time-code"
          disabled={busy}
          autoFocus
          onKeyDown={(e) => e.key === 'Enter' && onVerify()}
        />
        <div className="na-pulse-wrap">
          <span className="na-pulse" aria-hidden="true">
            <span className="na-pulse-core" />
            <span className="na-pulse-halo" />
          </span>
          <span className="na-pulse-text">
            已发送至 <span className="na-pulse-email">{email}</span>
          </span>
        </div>
      </div>
      <button
        type="button"
        className="na-btn-primary"
        onClick={onVerify}
        disabled={busy || otp.length !== 6}
      >
        {verifyLabel}
      </button>
      <div className="na-resend-row">
        {cooldown > 0 ? (
          <span className="na-cooldown-text">
            {cooldown}s 后可重新发送
          </span>
        ) : (
          <button
            type="button"
            className="na-btn-link"
            onClick={onResend}
            disabled={busy}
          >
            重新发送验证码
          </button>
        )}
      </div>
    </div>
  )
}

// ════════════════ 成功面板 ════════════════
function SuccessPanel({ email, title, msg, onBack }) {
  return (
    <div
      className="na-block na-fade-in-slow"
      role="status"
      aria-live="polite"
    >
      <div className="na-kicker">
        <span className="na-kicker-bar" />
        <span className="na-kicker-text">SESSION OPEN</span>
      </div>
      <div className="na-success-check">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <path
            d="M3 9.5 L7 13.5 L15 4.5"
            stroke="#C8392A"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
      <div className="na-success-info">
        <h2 className="na-success-title">{title}</h2>
        <p className="na-success-msg">{msg}</p>
      </div>
      <div className="na-success-card">
        <span className="na-success-card-email">{email}</span>
        <span className="na-success-card-badge">AUTHED</span>
      </div>
      <button type="button" className="na-btn-back" onClick={onBack}>
        ← 返回登录
      </button>
    </div>
  )
}
