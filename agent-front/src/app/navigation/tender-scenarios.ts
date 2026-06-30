import type { TenderScenario } from '@/features/contract/tender-review/types'

const TENDER_SCENARIOS: TenderScenario[] = [
  'bidder_self_check',
  'expert_assist',
  'post_eval_monitor',
]

const DEFAULT_TENDER_SCENARIOS: TenderScenario[] = ['expert_assist']

export function parseEnabledTenderScenarios(
  value: string | undefined
): TenderScenario[] {
  if (!value?.trim()) return DEFAULT_TENDER_SCENARIOS
  const enabled = value
    .split(',')
    .map((item) => item.trim())
    .filter((item): item is TenderScenario =>
      TENDER_SCENARIOS.includes(item as TenderScenario)
    )
  return enabled.length > 0 ? Array.from(new Set(enabled)) : DEFAULT_TENDER_SCENARIOS
}

export function getEnabledTenderScenarios(
  env: Record<string, string | undefined> = import.meta.env
): TenderScenario[] {
  return parseEnabledTenderScenarios(env.VITE_ENABLED_SCENARIOS)
}
