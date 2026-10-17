import { defineStore } from 'pinia'
import { shallowRef } from 'vue'
import { aggressiveGrowthSchema, type AggressiveGrowthView } from '../modules/aggressive-growth/contracts'

export const useAggressiveGrowthStore = defineStore('aggressiveGrowth', () => {
  const view = shallowRef<AggressiveGrowthView | null>(null)
  const error = shallowRef('')
  function update(value: unknown) {
    if (value == null) { view.value = null; error.value = ''; return }
    const parsed = aggressiveGrowthSchema.safeParse(value)
    if (!parsed.success) { error.value = 'DATA_UNAVAILABLE: contrato R20 no confirmado; datos conservados STALE.'; return }
    view.value = parsed.data; error.value = ''
  }
  return { view, error, update }
})
