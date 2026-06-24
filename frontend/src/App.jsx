import React from 'react'
import { AuthProvider, useAuth } from './auth/AuthContext'
import LoginGate from './auth/LoginGate'
import DashboardShell from './dashboard/Shell'

// v2.48 — App.jsx 仅做 auth 网关 + dashboard 装载.
// 旧 AppShell (v2.24-v2.46) 及其 7000+ 行 src/views + src/components 已删除.
// 仅 views/MultimodalView 因为 dashboard/Shell.jsx 仍在引用而保留.

export default function App() {
  return (
    <AuthProvider>
      <AuthGated>
        <DashboardShell />
      </AuthGated>
    </AuthProvider>
  )
}

function AuthGated({ children }) {
  const { ready, hasToken } = useAuth()
  if (!ready) {
    // 初始化中 — 短暂空白避免闪现登录框
    return (
      <div
        style={{
          height: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-muted, #888)',
        }}
      >
        <i className="fas fa-spinner fa-spin"></i>
      </div>
    )
  }
  if (!hasToken) {
    return <LoginGate />
  }
  return children
}
