import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

// v2.47 — Dashboard 主题 + 强调色 Context.
//
// theme:  'light' | 'dark' — 写到 html[data-theme]. 与 LoginGate 共享同一开关.
// accent: hex string '#RRGGBB' — 写到 .dc-root --accent + --red-tint.
//
// 持久化 → localStorage. 关掉再开仍保留. SSR-safe (typeof window 检查).

const THEME_KEY = 'na_dashboard_theme'
const ACCENT_KEY = 'na_dashboard_accent'

const DEFAULT_ACCENT = '#c8392a'
const DEFAULT_DARK_TINT = '#2A1813'
const DEFAULT_LIGHT_TINT = '#FDF1EE'

const ACCENT_SWATCHES = [
  '#c8392a', // brick red (default)
  '#0a0a0a', // near-black
  '#0f766e', // teal-700
  '#1d4ed8', // blue-700
  '#7c3aed', // violet-600
  '#d97706', // amber-600
  '#16a34a', // green-600
  '#db2777', // pink-600
]

function readInitialTheme() {
  try {
    const v = localStorage.getItem(THEME_KEY)
    if (v === 'dark' || v === 'light') return v
  } catch {
    /* private mode */
  }
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return 'light'
}

function readInitialAccent() {
  try {
    const v = localStorage.getItem(ACCENT_KEY)
    if (typeof v === 'string' && /^#[0-9a-fA-F]{6}$/.test(v)) return v
  } catch {
    /* */
  }
  return DEFAULT_ACCENT
}

function applyTheme(theme) {
  if (typeof document === 'undefined') return
  const html = document.documentElement
  if (theme === 'dark') html.setAttribute('data-theme', 'dark')
  else html.removeAttribute('data-theme')
}

// 把 #RRGGBB + alpha 转 rgba — 给 --red-tint 用.
function hexToRgba(hex, alpha) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '')
  if (!m) return `rgba(200,57,42,${alpha})`
  const v = m[1]
  const r = parseInt(v.slice(0, 2), 16)
  const g = parseInt(v.slice(2, 4), 16)
  const b = parseInt(v.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

// 在登录页/dashboard 之外的页面, 不写 data-theme. 但 dashboard 卸载时不应清,
// 因为 LoginGate / ReaderOverlay 也用同一开关. 这里只负责设置, 不清.
function applyAccent(accent, theme) {
  if (typeof document === 'undefined') return
  // 用 :root level CSS var, 让 dashboard 内所有 .dc-root 都拿到.
  const root = document.documentElement
  root.style.setProperty('--dc-accent-override', accent)
  // 同时直接设置一个 stylesheet-level rule via a single style tag.
  let tag = document.getElementById('dc-accent-style')
  if (!tag) {
    tag = document.createElement('style')
    tag.id = 'dc-accent-style'
    document.head.appendChild(tag)
  }
  const tintAlpha = theme === 'dark' ? 0.16 : 0.08
  tag.textContent =
    `.dc-root { --accent: ${accent}; --red-tint: ${hexToRgba(accent, tintAlpha)}; }`
}

const ThemeContext = createContext({
  theme: 'light',
  accent: DEFAULT_ACCENT,
  isDark: false,
  toggleTheme: () => {},
  setTheme: () => {},
  setAccent: () => {},
  accentSwatches: ACCENT_SWATCHES,
})

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(readInitialTheme)
  const [accent, setAccentState] = useState(readInitialAccent)

  useEffect(() => {
    applyTheme(theme)
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      /* */
    }
  }, [theme])

  useEffect(() => {
    applyAccent(accent, theme)
    try {
      localStorage.setItem(ACCENT_KEY, accent)
    } catch {
      /* */
    }
  }, [accent, theme])

  const toggleTheme = useCallback(
    () => setThemeState((t) => (t === 'dark' ? 'light' : 'dark')),
    [],
  )

  const setTheme = useCallback((t) => {
    if (t === 'dark' || t === 'light') setThemeState(t)
  }, [])

  const setAccent = useCallback((a) => {
    if (typeof a === 'string' && /^#[0-9a-fA-F]{6}$/.test(a)) {
      setAccentState(a)
    }
  }, [])

  const value = useMemo(
    () => ({
      theme,
      accent,
      isDark: theme === 'dark',
      toggleTheme,
      setTheme,
      setAccent,
      accentSwatches: ACCENT_SWATCHES,
    }),
    [theme, accent, toggleTheme, setTheme, setAccent],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  return useContext(ThemeContext)
}

export { DEFAULT_ACCENT, DEFAULT_DARK_TINT, DEFAULT_LIGHT_TINT, ACCENT_SWATCHES }
