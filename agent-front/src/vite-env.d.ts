/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ENABLE_DEVTOOLS?: string
  readonly VITE_APP_TITLE?: string
  readonly VITE_API_BASE?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_API_PROXY_TARGET?: string
  readonly VITE_AUDIT_API_PROXY_TARGET?: string
  readonly VITE_ADMIN_API_PROXY_TARGET?: string
  readonly VITE_TENANT_PIN_KEYS?: string
  readonly VITE_ENABLED_SCENARIOS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
