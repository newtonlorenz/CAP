import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8000'
  const allowAllHosts = env.VITE_ALLOW_ALL_HOSTS === 'true'

  return {
    base: env.VITE_BASE_PATH || '/',
    plugins: [react()],
    server: {
      // Enabled only by the public tunnel script.
      allowedHosts: allowAllHosts ? true : undefined,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
      exclude: ['e2e/**', 'e2e-feedback/**', 'node_modules/**'],
    },
  }
})
