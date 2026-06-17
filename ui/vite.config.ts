import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

function proxyTarget(env: Record<string, string>): string {
  if (env.VITE_API_PROXY_TARGET) return env.VITE_API_PROXY_TARGET
  if (env.API_PROXY_TARGET) return env.API_PROXY_TARGET
  const rawHost = env.APP_SERVER_HOST || '127.0.0.1'
  const host = rawHost === '0.0.0.0' || rawHost === '::' ? '127.0.0.1' : rawHost
  const port = env.APP_SERVER_PORT || '8000'
  return `http://${host}:${port}`
}

export default defineConfig(({ mode }) => {
  const rootEnv = loadEnv(mode, '..', '')
  const uiEnv = loadEnv(mode, '.', '')
  const env = { ...rootEnv, ...uiEnv }
  const target = proxyTarget(env)

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/audit': {
          target,
          changeOrigin: true,
        },
        '/ocr': {
          target,
          changeOrigin: true,
        },
        '/health': {
          target,
          changeOrigin: true,
        },
      },
    },
  }
})
