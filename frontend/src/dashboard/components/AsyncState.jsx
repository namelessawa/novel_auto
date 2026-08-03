import React from 'react'

export default function AsyncState({
  kind = 'loading',
  title,
  detail,
  actionLabel,
  onAction,
  compact = false,
}) {
  const copy = {
    loading: ['正在读取', '请稍候，正在同步作品的权威状态。'],
    empty: ['还没有内容', '完成上一步后，这里会自动出现。'],
    error: ['暂时无法读取', '保留当前操作，稍后可安全重试。'],
  }
  const [fallbackTitle, fallbackDetail] = copy[kind] || copy.loading
  return (
    <div
      className={`dc-async-state is-${kind} ${compact ? 'is-compact' : ''}`}
      role={kind === 'error' ? 'alert' : 'status'}
      aria-live={kind === 'error' ? 'assertive' : 'polite'}
      aria-busy={kind === 'loading' || undefined}
    >
      <span className="dc-async-mark" aria-hidden="true">
        {kind === 'loading' ? '···' : kind === 'error' ? '!' : '○'}
      </span>
      <div>
        <strong>{title || fallbackTitle}</strong>
        <p>{detail || fallbackDetail}</p>
      </div>
      {actionLabel && onAction && (
        <button type="button" className="dc-btn-ghost" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  )
}

export function InlineNotice({ kind = 'info', children, actions }) {
  return (
    <div
      className={`dc-inline-notice is-${kind}`}
      role={kind === 'error' ? 'alert' : 'status'}
      aria-live="polite"
    >
      <div>{children}</div>
      {actions && <div className="dc-inline-notice-actions">{actions}</div>}
    </div>
  )
}
