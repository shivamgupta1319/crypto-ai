import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Backend target is overridable via env so it can avoid local port clashes.
const apiTarget = process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Proxy API + WS to the FastAPI backend during development.
      '/api': { target: apiTarget, ws: true, changeOrigin: true },
      '/health': apiTarget,
    },
  },
})
