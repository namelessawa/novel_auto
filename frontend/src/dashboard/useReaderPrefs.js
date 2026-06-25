// Phase 6-B iter#G — Reader 阅读偏好 + scroll 位置持久化 (localStorage).
//
// Keys:
//   reader.continuousMode  global boolean ("1"/"0")
//   reader.fontSize        global 16 / 18 / 20
//   reader.lineHeight      global 1.6 / 1.85 / 2.05
//   reader.scrollY.{id}    per-novel scroll position (px)
//
// SAFE: 所有 localStorage 访问 try/catch — 隐私模式 / Safari intel 限额
// 都会抛, 不该让 reader 因此挂掉.

import { useCallback, useEffect, useRef, useState } from 'react'

const KEYS = {
  continuous: 'reader.continuousMode',
  fontSize: 'reader.fontSize',
  lineHeight: 'reader.lineHeight',
  fontFamily: 'reader.fontFamily',
  scrollPrefix: 'reader.scrollY.',
}

const DEFAULT_FONT_SIZE = 18
const DEFAULT_LINE_HEIGHT = 2.05
const DEFAULT_FONT_FAMILY = 'serif'
const FONT_SIZE_OPTIONS = [16, 18, 20]
const LINE_HEIGHT_OPTIONS = [1.6, 1.85, 2.05]
// iter#L — 3 font family options. 值映射到 CSS font-family stack.
const FONT_FAMILY_OPTIONS = ['serif', 'sans', 'kaiti']
const FONT_FAMILY_STACK = {
  serif: "'Noto Serif SC', 'Source Han Serif SC', serif",
  sans: "'Noto Sans SC', 'Source Han Sans SC', 'Inter', sans-serif",
  kaiti: "'STKaiti', 'KaiTi', '楷体', 'Noto Serif SC', serif",
}
const FONT_FAMILY_LABEL = {
  serif: '宋',
  sans: '黑',
  kaiti: '楷',
}

function _safeGet(key, fallback) {
  try {
    const v = window.localStorage.getItem(key)
    return v === null ? fallback : v
  } catch {
    return fallback
  }
}

function _safeSet(key, value) {
  try {
    window.localStorage.setItem(key, String(value))
  } catch {
    /* swallow */
  }
}

export function useReaderPrefs(novelId) {
  // Initial values read once on mount.
  const [continuousMode, setContinuousModeState] = useState(() =>
    _safeGet(KEYS.continuous, '0') === '1',
  )
  const [fontSize, setFontSizeState] = useState(() => {
    const raw = Number(_safeGet(KEYS.fontSize, DEFAULT_FONT_SIZE))
    return FONT_SIZE_OPTIONS.includes(raw) ? raw : DEFAULT_FONT_SIZE
  })
  const [lineHeight, setLineHeightState] = useState(() => {
    const raw = Number(_safeGet(KEYS.lineHeight, DEFAULT_LINE_HEIGHT))
    return LINE_HEIGHT_OPTIONS.includes(raw) ? raw : DEFAULT_LINE_HEIGHT
  })
  const [fontFamily, setFontFamilyState] = useState(() => {
    const raw = String(_safeGet(KEYS.fontFamily, DEFAULT_FONT_FAMILY))
    return FONT_FAMILY_OPTIONS.includes(raw) ? raw : DEFAULT_FONT_FAMILY
  })

  const setContinuousMode = useCallback((v) => {
    const next = typeof v === 'function' ? v((p) => p) : v
    // 上面 functional form 只取一次值 — 简化版直接覆写
    setContinuousModeState((prev) => {
      const resolved = typeof v === 'function' ? v(prev) : Boolean(v)
      _safeSet(KEYS.continuous, resolved ? '1' : '0')
      return resolved
    })
    return next
  }, [])

  const setFontSize = useCallback((px) => {
    const v = FONT_SIZE_OPTIONS.includes(Number(px))
      ? Number(px)
      : DEFAULT_FONT_SIZE
    setFontSizeState(v)
    _safeSet(KEYS.fontSize, v)
  }, [])

  const setLineHeight = useCallback((lh) => {
    const v = LINE_HEIGHT_OPTIONS.includes(Number(lh))
      ? Number(lh)
      : DEFAULT_LINE_HEIGHT
    setLineHeightState(v)
    _safeSet(KEYS.lineHeight, v)
  }, [])

  const setFontFamily = useCallback((ff) => {
    const v = FONT_FAMILY_OPTIONS.includes(String(ff))
      ? String(ff)
      : DEFAULT_FONT_FAMILY
    setFontFamilyState(v)
    _safeSet(KEYS.fontFamily, v)
  }, [])

  // ----- Per-novel scroll persistence ------------------------------------
  const scrollKey = novelId ? KEYS.scrollPrefix + novelId : ''
  const initialScrollRef = useRef(
    scrollKey ? Number(_safeGet(scrollKey, 0)) || 0 : 0,
  )

  const restoreScroll = useCallback(
    (containerEl) => {
      if (!containerEl) return
      const y = initialScrollRef.current
      if (y > 0) {
        // rAF defer — DOM may not be measured yet on first paint
        requestAnimationFrame(() => {
          try {
            containerEl.scrollTop = y
          } catch {
            /* swallow */
          }
        })
      }
    },
    [],
  )

  const saveScroll = useCallback(
    (y) => {
      if (!scrollKey || typeof y !== 'number') return
      _safeSet(scrollKey, Math.round(y))
    },
    [scrollKey],
  )

  // Whenever novelId changes, refresh initialScrollRef so restore picks up.
  useEffect(() => {
    if (!scrollKey) {
      initialScrollRef.current = 0
      return
    }
    initialScrollRef.current = Number(_safeGet(scrollKey, 0)) || 0
  }, [scrollKey])

  return {
    continuousMode,
    setContinuousMode,
    fontSize,
    setFontSize,
    lineHeight,
    setLineHeight,
    // iter#L — font family
    fontFamily,
    setFontFamily,
    fontFamilyStack: FONT_FAMILY_STACK[fontFamily],
    restoreScroll,
    saveScroll,
    FONT_SIZE_OPTIONS,
    LINE_HEIGHT_OPTIONS,
    FONT_FAMILY_OPTIONS,
    FONT_FAMILY_LABEL,
  }
}
