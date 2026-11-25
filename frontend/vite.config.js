import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend port the proxy talks to. Override with BACKEND_URL when the API
// is running somewhere other than the default local uvicorn port.
const backend = process.env.BACKEND_URL || 'http://127.0.0.1:8000'

// The /api proxy is not a convenience: without it the browser would call
// localhost:5173/api/... and get the Vite dev server's own 404, which looks
// exactly like an application bug. The README promised this proxy before it
// existed, so it lives here now and is covered by the browser pass.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: backend,
        changeOrigin: true,
      },
      '/health': {
        target: backend,
        changeOrigin: true,
      },
    },
  },
  build: {
    // A farmer on a metered 3G connection is the person this app is for, so
    // the build is checked for weight rather than assumed to be fine.
    chunkSizeWarningLimit: 300,
  },
})
