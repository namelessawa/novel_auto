import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendPort = process.env.BACKEND_PORT || 8762
const frontendPort = process.env.FRONTEND_PORT || 3143

export default defineConfig({
  plugins: [react()],
  base: '/nw/',
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
