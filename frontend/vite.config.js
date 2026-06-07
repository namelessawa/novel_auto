import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendPort = process.env.BACKEND_PORT || 8762
const frontendPort = process.env.FRONTEND_PORT || 3143

// 静态资源前缀, 默认根路径 `/`。
// - 同源部署: FastAPI 把 SPA mount 到 `/`, 直接 serve dist/。
// - Vercel 等独立托管: 不用设, 默认就对。
// - 如果你想把前端塞到 /nw/ 之类的子路径下, 显式 VITE_BASE_PATH=/nw/。
const basePath = process.env.VITE_BASE_PATH || '/'

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
