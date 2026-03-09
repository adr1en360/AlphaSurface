import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Any request from React starting with /ws gets forwarded to your Python server
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,  // this tells Vite the proxy should handle WebSocket traffic
      }
    }
  }
})