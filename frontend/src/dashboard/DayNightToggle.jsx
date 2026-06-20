import React from 'react'
import { useTheme } from './ThemeContext'

// v2.47 — jh3y 风格 day/night 拨片. 复用 .dc-na-toggle 等样式.
export default function DayNightToggle({ title = '切换主题' }) {
  const { isDark, toggleTheme } = useTheme()
  return (
    <button
      type="button"
      className="dc-na-toggle"
      onClick={toggleTheme}
      title={title}
      aria-label={title}
      aria-pressed={isDark}
    >
      <span className="dc-tgl-cloud dc-tgl-c1" />
      <span className="dc-tgl-cloud dc-tgl-c2" />
      <span className="dc-tgl-cloud dc-tgl-c3" />
      <span className="dc-tgl-star dc-tgl-s1" />
      <span className="dc-tgl-star dc-tgl-s2" />
      <span className="dc-tgl-star dc-tgl-s3" />
      <span className="dc-tgl-star dc-tgl-s4" />
      <span className="dc-na-knob">
        <span className="dc-tgl-crater dc-tgl-k1" />
        <span className="dc-tgl-crater dc-tgl-k2" />
        <span className="dc-tgl-crater dc-tgl-k3" />
      </span>
    </button>
  )
}
