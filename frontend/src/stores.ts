import { defineStore } from 'pinia'
import { shallowRef as ref } from 'vue'
import { api } from './api'
import type { KronosView, SystemStatus, MarketQuote, Experiment, Trade, Prediction, Research, Calibration, Notification, SolResponse, DashboardSnapshot, RealtimeEvent } from './types'
import { useActivityStore } from './stores/activity'
import { useAggressiveGrowthStore } from './stores/aggressiveGrowth'
export { useInterfaceStore } from './stores/interface'
export const useSystemStore = defineStore('system', () => { const status = ref<SystemStatus | null>(null); const rotation = ref<DashboardSnapshot['rotation']>(undefined); const priceRisk = ref<DashboardSnapshot['priceRisk']>(undefined); const connection = ref('DISCONNECTED'); const authenticated = ref(false); const error = ref(''); const studyId = ref<string | null>(null); const studyStatus = ref('DATA_UNAVAILABLE'); return { status, rotation, priceRisk, connection, authenticated, error, studyId, studyStatus } })
export const useKronosStore = defineStore('kronos', () => { const view = ref<KronosView | null>(null); return { view } })
export const useMarketStore = defineStore('market', () => { const quote = ref<MarketQuote | null>(null); return { quote } })
export const useExperimentStore = defineStore('experiments', () => { const experiments = ref<Experiment[]>([]); const calibration = ref<Calibration | null>(null); const research = ref<Research | null>(null); return { experiments, calibration, research } })
export const useTradeStore = defineStore('trades', () => { const open = ref<Trade[]>([]); const closed = ref<Trade[]>([]); const selected = ref<Trade | null>(null); return { open, closed, selected } })
export const usePredictionStore = defineStore('prediction', () => { const current = ref<Prediction | null>(null); return { current } })
export const useNotificationStore = defineStore('notifications', () => { const items = ref<Notification[]>([]); function add(item: Notification) { items.value = [item, ...items.value.filter(n => n.id !== item.id)].slice(0, 50) } return { items, add } })
export const useSolStore = defineStore('sol', () => {
  const messages = ref<{ id: string; question: string; response?: SolResponse; error?: string }[]>([]); const busy = ref(false)
  async function send(question: string) {
    if (busy.value || !question.trim()) return
    const id = crypto.randomUUID(); messages.value = [...messages.value, { id, question }]; busy.value = true
    try { const response = await api.chat({ requestId: id, message: question }); messages.value = messages.value.map(m => m.id === id ? { ...m, response } : m); useActivityStore().sol(response) }
    catch { messages.value = messages.value.map(m => m.id === id ? { ...m, error: 'No se pudo consultar. Sin reintento automático; revisa conexión y journal.' } : m) }
    finally { busy.value = false }
  }
  return { messages, busy, send }
})
export function applySnapshot(s: DashboardSnapshot) {
  useAggressiveGrowthStore().update(s.aggressiveGrowth)
  useActivityStore().hydrate(s)
  useKronosStore().view = s.kronos ?? null
  const system = useSystemStore(); system.status = s.system; system.rotation = s.rotation; system.priceRisk = s.priceRisk; system.studyId = s.studyId; system.studyStatus = s.studyStatus; system.error = ''
  useMarketStore().quote = s.market; useExperimentStore().experiments = s.experiments; useExperimentStore().calibration = s.calibration; useExperimentStore().research = s.research
  useTradeStore().open = s.openPositions; useTradeStore().closed = s.trades; usePredictionStore().current = s.prediction; useNotificationStore().items = s.notifications
}
export function applyEvent(e: RealtimeEvent) {
  useActivityStore().ingest(e)
  // Event shapes originate in the same versioned backend projection as the snapshot.
  switch (e.type) {
    case 'aggressiveGrowth.updated': useAggressiveGrowthStore().update(e.data); break;
    case 'kronos.updated': useKronosStore().view = e.data as KronosView; break;
    case 'priceRisk.updated': useSystemStore().priceRisk = e.data as DashboardSnapshot['priceRisk']; break;
    case 'rotation.updated': useSystemStore().rotation = e.data as DashboardSnapshot['rotation']; break;
    case 'study.updated': useSystemStore().studyStatus = e.data as string; break
    case 'connection.updated': useSystemStore().status = e.data as SystemStatus; break
    case 'market.quote.updated': useMarketStore().quote = e.data as MarketQuote; break
    case 'experiment.updated': useExperimentStore().experiments = e.data as Experiment[]; break
    case 'position.updated': useTradeStore().open = e.data as Trade[]; break
    case 'trade.completed': useTradeStore().closed = e.data as Trade[]; break
    case 'prediction.updated': usePredictionStore().current = e.data as Prediction; break
    case 'research.updated': useExperimentStore().calibration = e.data as Calibration; break
    case 'journal.updated': useExperimentStore().research = e.data as Research; break
    case 'notification.updated': useNotificationStore().items = e.data as Notification[]; break
    case 'source.unavailable': {
      useSystemStore().error = 'DATA_UNAVAILABLE: journal o proyección de lectura no disponibles.'
      const market = useMarketStore(); if (market.quote) market.quote = { ...market.quote, quality: 'STALE' }
      const system = useSystemStore(); if (system.status) system.status = { ...system.status, postgres: 'UNKNOWN' }
      break
    }
  }
}
