// Lightweight toast helper — mirrors v1 frontend_express showToast().
//
// Usage: import { showToast } from '../utils/toast'
//        showToast('Saved', 'success')

const ICON_BY_KIND = {
  success: 'fa-check-circle',
  error: 'fa-exclamation-circle',
  info: 'fa-info-circle',
}

export function showToast(message, kind = 'info') {
  const existing = document.querySelector('.toast')
  if (existing) existing.remove()

  const toast = document.createElement('div')
  toast.className = `toast ${kind}`
  // a11y: error 用 alert (assertive) 立刻打断屏阅; 其他用 status (polite) 不打断
  if (kind === 'error') {
    toast.setAttribute('role', 'alert')
    toast.setAttribute('aria-live', 'assertive')
  } else {
    toast.setAttribute('role', 'status')
    toast.setAttribute('aria-live', 'polite')
  }
  toast.setAttribute('aria-atomic', 'true')
  const icon = ICON_BY_KIND[kind] || ICON_BY_KIND.info
  toast.innerHTML = `<i class="fas ${icon}" aria-hidden="true" style="margin-right:8px;"></i>${escape(message)}`
  document.body.appendChild(toast)

  requestAnimationFrame(() => toast.classList.add('show'))
  setTimeout(() => {
    toast.classList.remove('show')
    setTimeout(() => toast.remove(), 300)
  }, 3500)
}

function escape(text) {
  if (!text) return ''
  const div = document.createElement('div')
  div.textContent = String(text)
  return div.innerHTML
}
