import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// En local, /api se reenvía al backend para reproducir el mismo origen que en Vercel.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': process.env.API_URL ?? 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: false,
  },
})
