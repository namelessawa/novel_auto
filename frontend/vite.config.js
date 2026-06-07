import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendPort = process.env.BACKEND_PORT || 8762
const frontendPort = process.env.FRONTEND_PORT || 3143

// 静态资源前缀。
// - 默认 `/nw/` — 与 FastAPI 的 `app.mount('/nw/', ...)` 对齐(同源部署)。
// - Vercel 等独立托管把 VITE_BASE_PATH=/ 显式覆盖, 资源走根路径。
const basePath = process.env.VITE_BASE_PATH || '/nw/'

export default defineConfig({
  plugins: [react()],
  base: basePath,
  server: {
    host: '127.0.0.1',
    port: Number(frontendPort),
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
      },
    },
  },
  define: {
    'import.meta.env.VITE_API_BASE': JSON.stringify(process.env.VITE_API_BASE || ''),
  },
})
