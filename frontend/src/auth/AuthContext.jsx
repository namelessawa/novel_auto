import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import {
  authMe,
  authLogout,
  getStoredToken,
  setStoredToken,
} from '../services/api'

// v2.26 — Auth state container.
//
// Token 存 localStorage (跨 tab + 跨刷新生效)。app 启动时若有 token,
// 立即调 /api/auth/me 验证; 失败 (401) 自动清 token。
//
// services/api.js 在收到任意 401 时 dispatch 'auth:expired' — 这里订阅,
// 自动 logout 触发 LoginGate 出现。

const AuthContext = createContext({
  user: null,
  ready: false,
  hasToken: false,
  setSession: () => {},
  refreshUser: async () => {},
  logout: async () => {},
})

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  const [hasToken, setHasToken] = useState(() => Boolean(getStoredToken()))

  // 初次挂载: 若有 token 验证一次
  useEffect(() => {
    let cancelled = false
    async function init() {
      const token = getStoredToken()
      if (!token) {
        if (!cancelled) setReady(true)
        return
      }
      try {
        const u = await authMe()
        if (!cancelled) {
          setUser(u)
          setHasToken(true)
        }
      } catch {
        // 401 — token 失效, api.js 已经清掉了
        if (!cancelled) {
          setUser(null)
          setHasToken(false)
        }
      } finally {
        if (!cancelled) setReady(true)
      }
    }
    init()
    return () => {
      cancelled = true
    }
  }, [])

  // 订阅 401 自动 logout
  useEffect(() => {
    function onExpired() {
      setUser(null)
      setHasToken(false)
    }
    window.addEventListener('auth:expired', onExpired)
    return () => window.removeEventListener('auth:expired', onExpired)
  }, [])

  // 登录/注册成功后调用 — 拿到 {token, user}
  const setSession = useCallback(({ token, user: u }) => {
    setStoredToken(token)
    setUser(u)
    setHasToken(true)
  }, [])

  const refreshUser = useCallback(async () => {
    try {
      const u = await authMe()
      setUser(u)
      return u
    } catch {
      setUser(null)
      setHasToken(false)
      return null
    }
  }, [])

  const logout = useCallback(async () => {
    await authLogout()
    setUser(null)
    setHasToken(false)
  }, [])

  const value = useMemo(
    () => ({ user, ready, hasToken, setSession, refreshUser, logout }),
    [user, ready, hasToken, setSession, refreshUser, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}
