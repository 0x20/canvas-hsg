import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/spotify/',
  server: {
    port: 5173,
    host: '0.0.0.0', // Allow access from any IP (Chromium on same machine)
    strictPort: true, // Fail if port 5173 is already in use
    cors: true, // Enable CORS for WebSocket connections
    allowedHosts: ['.local'], // Allow mDNS .local hosts
    hmr: {
      overlay: false // Disable error overlay in kiosk mode
    },
    proxy: {
      // Proxy API and static file requests to backend
      '/static': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/ws': {
        target: 'http://127.0.0.1:8000',
        ws: true,
        changeOrigin: true
      }
    }
  }
})
