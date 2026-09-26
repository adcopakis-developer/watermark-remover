import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  // './' agar index.html + aset jalan via file:// di Electron packaged.
  base: './',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
