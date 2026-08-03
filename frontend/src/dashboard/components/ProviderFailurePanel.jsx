import React from 'react'

export function isProviderError(error) {
  return String(error?.code || '').startsWith('PROVIDER_')
}

export default function ProviderFailurePanel({
  error,
  provider,
  model,
  source,
  onOpenConfig,
  onRetry,
}) {
  if (!error && !provider) return null
  return (
    <section className="dc-provider-failure" role="alert">
      <div className="dc-provider-failure-mark">!</div>
      <div className="dc-provider-failure-copy">
        <span>PROVIDER PAUSED</span>
        <h3>模型服务认证失败</h3>
        <p>
          应用登录仍然有效；整书任务已在安全边界暂停。修复配置后可直接恢复。
        </p>
        <dl>
          <div><dt>provider</dt><dd>{provider || error?.details?.provider || '—'}</dd></div>
          <div><dt>model</dt><dd>{model || error?.details?.model || '—'}</dd></div>
          <div><dt>source</dt><dd>{source || error?.details?.source || 'masked'}</dd></div>
          <div><dt>code</dt><dd>{error?.code || 'PROVIDER_AUTH_FAILED'}</dd></div>
        </dl>
      </div>
      <div className="dc-provider-failure-actions">
        <button type="button" className="dc-btn" onClick={onOpenConfig}>
          打开 Provider 配置
        </button>
        <button type="button" className="dc-btn-ghost" onClick={onRetry}>
          重新测试
        </button>
      </div>
    </section>
  )
}
