import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8000'
  const allowAllHosts = env.VITE_ALLOW_ALL_HOSTS === 'true'
  const { version } = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as { version: string }

  return {
    base: env.VITE_BASE_PATH || '/',
    plugins: [react()],
    define: {
      'import.meta.env.VITE_APP_VERSION': JSON.stringify(env.VITE_APP_VERSION || version),
      'import.meta.env.VITE_APP_REVISION': JSON.stringify(env.VITE_APP_REVISION || ''),
    },
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
