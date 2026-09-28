import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BACKEND_PORT = process.env.BACKEND_PORT || '8000'
const FE_PORT = parseInt(process.env.FE_PORT || '5173', 10)

export default defineConfig({
  // './' agar index.html + aset jalan via file:// di Electron packaged.
  base: './',
  plugins: [react()],
  server: {
    port: FE_PORT,
    strictPort: true,
    proxy: {
      '/api': `http://127.0.0.1:${BACKEND_PORT}`,
    },
  },
})
