export type DatePreset = 'today' | 'last_7_days' | 'last_14_days' | 'last_30_days'

export const datePresetToDays: Record<DatePreset, number> = {
  today: 1,
  last_7_days: 7,
  last_14_days: 14,
  last_30_days: 30,
}

export const datePresetLabels: Record<DatePreset, string> = {
  today: 'Today',
  last_7_days: 'Last 7 days',
  last_14_days: 'Last 14 days',
  last_30_days: 'Last 30 days',
}
