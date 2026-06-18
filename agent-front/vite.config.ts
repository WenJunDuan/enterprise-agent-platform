import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { tanstackRouter } from '@tanstack/router-plugin/vite'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath, URL } from 'node:url'

function loadEnvFile(envFile: string) {
  const envFilePath = resolve(process.cwd(), envFile)
  if (!existsSync(envFilePath)) return {}

  return readFileSync(envFilePath, 'utf8')
    .split(/\r?\n/)
    .reduce(
      (acc, line) => {
        const trimmed = line.trim()
        if (!trimmed || trimmed.startsWith('#')) return acc

        const separatorIndex = trimmed.indexOf('=')
        if (separatorIndex === -1) return acc

        const key = trimmed.slice(0, separatorIndex).trim()
        const value = trimmed.slice(separatorIndex + 1).trim()

        if (key.startsWith('VITE_')) {
          acc[key] = value.replace(/^['"]|['"]$/g, '')
        }

        return acc
      },
      {} as Record<string, string>
    )
}

function loadCustomEnv(mode: string) {
  const envFileMap: Record<string, string> = {
    development: '.env.dev',
    production: '.env.prod',
  }
  const envFile = envFileMap[mode]
  const envFiles = envFile ? [envFile] : []

  return envFiles.reduce(
    (acc, file) => ({
      ...acc,
      ...loadEnvFile(file),
    }),
    {} as Record<string, string>
  )
}

function normalizeProxyHost(host: string) {
  return host === '0.0.0.0' || host === '::' ? '127.0.0.1' : host
}

function resolveAuditProxyTarget(env: Record<string, string>) {
  if (env.VITE_AUDIT_API_PROXY_TARGET?.trim()) {
    return env.VITE_AUDIT_API_PROXY_TARGET.trim()
  }
  if (env.VITE_API_PROXY_TARGET?.trim()) {
    return env.VITE_API_PROXY_TARGET.trim()
  }
  if (env.API_PROXY_TARGET?.trim()) {
    return env.API_PROXY_TARGET.trim()
  }

  const host = normalizeProxyHost(env.APP_SERVER_HOST?.trim() || '127.0.0.1')
  const port = env.APP_SERVER_PORT?.trim() || '8000'
  return `http://${host}:${port}`
}

function resolveAdminProxyTarget(env: Record<string, string>) {
  if (env.VITE_ADMIN_API_PROXY_TARGET?.trim()) {
    return env.VITE_ADMIN_API_PROXY_TARGET.trim()
  }
  if (
    env.VITE_REQUIRE_ADMIN_AUTH === 'true' &&
    env.VITE_API_PROXY_TARGET?.trim()
  ) {
    return env.VITE_API_PROXY_TARGET.trim()
  }
  return ''
}

export default defineConfig(({ mode }) => {
  const customEnv = { ...process.env, ...loadCustomEnv(mode) } as Record<
    string,
    string
  >
  const define = Object.fromEntries(
    Object.entries(customEnv)
      .filter(([key]) => key.startsWith('VITE_'))
      .map(([key, value]) => [
        `import.meta.env.${key}`,
        JSON.stringify(value),
      ])
  )
  const auditProxyTarget = resolveAuditProxyTarget(customEnv)
  const adminProxyTarget = resolveAdminProxyTarget(customEnv)
  const proxy = {
    ...(adminProxyTarget
      ? {
          '/api': {
            target: adminProxyTarget,
            changeOrigin: true,
            rewrite: (path: string) => path.replace(/^\/api/, '/talent_manger'),
          },
        }
      : {}),
    '/audit': {
      target: auditProxyTarget,
      changeOrigin: true,
    },
    '/ocr': {
      target: auditProxyTarget,
      changeOrigin: true,
    },
    '/health': {
      target: auditProxyTarget,
      changeOrigin: true,
    },
  }

  return {
    define,
    plugins: [
      tanstackRouter({
        target: 'react',
        autoCodeSplitting: true,
      }),
      react(),
      tailwindcss(),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: { proxy },
  }
})
