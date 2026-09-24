import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'
import { backendBridge } from './scripts/vite-backend'

export default defineConfig({
  test: { include: ['src/**/*.test.{ts,tsx}'] },
  plugins: [react(), tailwindcss(), backendBridge()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { port: 1420, strictPort: true, host: '127.0.0.1' },
  preview: { port: 1420, strictPort: true, host: '127.0.0.1' },
  clearScreen: false,
  build: {
    rollupOptions: {
      output: {
        manualChunks: { charts: ['echarts'], react: ['react', 'react-dom'] },
      },
    },
  },
})
