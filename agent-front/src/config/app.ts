export const APP_TITLE =
  import.meta.env.VITE_APP_TITLE?.trim() || '晓数智能云平台'

export const REQUIRE_ADMIN_AUTH =
  import.meta.env.VITE_REQUIRE_ADMIN_AUTH?.trim() === 'true'
