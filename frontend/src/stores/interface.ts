import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ProfileId } from '../types'

export const useInterfaceStore = defineStore('interface', () => {
  const solRequested = ref(0)
  const profile = ref<ProfileId>('EURUSD_R1')
  const theme = ref<'dark' | 'light'>('dark')
  function openSol() { solRequested.value++ }
  function setTheme(value: 'dark' | 'light') {
    theme.value = value
    document.documentElement.dataset.theme = value
    try { localStorage.setItem('tradingagent-theme', value) } catch { /* Theme remains usable without storage. */ }
  }
  function initializeTheme() {
    let stored: string | null = null
    try { stored = localStorage.getItem('tradingagent-theme') } catch { /* Private browser storage. */ }
    setTheme(stored === 'light' ? 'light' : 'dark')
  }
  return { solRequested, profile, theme, openSol, setTheme, initializeTheme }
})
