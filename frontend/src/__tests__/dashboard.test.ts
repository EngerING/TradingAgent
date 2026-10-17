import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { parseSolResponse, request, api } from '../api'
import { applyEvent, applySnapshot, useExperimentStore, useMarketStore, useNotificationStore, useSolStore, useSystemStore, useTradeStore } from '../stores'
import { retryDelay, SequencedEvents } from '../realtime'
import { money, percent } from '../format'
import StatusBadge from '../components/StatusBadge.vue'
import ExperimentCard from '../components/ExperimentCard.vue'
import SolMessage from '../components/SolMessage.vue'
import { mockSnapshot, mockSol } from './fixtures'
import type { RealtimeEvent, Trade } from '../types'
beforeEach(() => { setActivePinia(createPinia()) })
describe('SolResponse contract', () => {
  it('accepts bounded structured local response', () => expect(parseSolResponse(mockSol).metrics[0]?.value).toBe(100))
  it('rejects JavaScript extra fields', () => expect(() => parseSolResponse({ ...mockSol, javascript: 'fetch(secrets)' })).toThrow())
  it('rejects model-authorized command', () => expect(() => parseSolResponse({ ...mockSol, command: { intent: 'BUY', status: 'BLOCKED', authorized: true, requiresConfirmation: true, reason: 'MOCK' } })).toThrow())
  it('rejects non-finite metrics', () => expect(() => parseSolResponse({ ...mockSol, metrics: [{ label: 'bad', value: NaN, format: 'money' }] })).toThrow())
  it('preserves undefined metric as null', () => expect(parseSolResponse({ ...mockSol, metrics: [{ label: 'win', value: null, format: 'percent' }] }).metrics[0]?.value).toBeNull())
})
describe('Safe and honest rendering', () => {
  it('renders unprotected as danger', () => expect(mount(StatusBadge, { props: { value: 'UNPROTECTED' } }).classes()).toContain('danger'))
  it('live blocked is visible', () => expect(mount(StatusBadge, { props: { value: 'LIVE BLOQUEADO', tone: 'danger' } }).text()).toContain('LIVE BLOQUEADO'))
  it('does not turn missing metrics into zero', () => { expect(money(null)).toBe('No evaluable'); expect(percent(null)).toBe('No evaluable') })
  it('shows initial allocation and paused state', () => { const w = mount(ExperimentCard, { props: { experiment: mockSnapshot.experiments[0]! }, global: { stubs: { EquityChart: true } } }); expect(w.text()).toContain('PAUSED'); expect(w.text()).toContain('100'); expect(w.text()).toContain('No evaluable') })
  it('escapes model HTML and never executes it', () => { const w = mount(SolMessage, { props: { response: { ...mockSol, text: '<script>alert(1)</script>' } }, global: { stubs: { EquityChart: true } } }); expect(w.html()).toContain('&lt;script&gt;'); expect(w.find('script').exists()).toBe(false) })
})
describe('Independent stores', () => {
  it('snapshot reflects no execution authority', () => { applySnapshot(structuredClone(mockSnapshot)); expect(useSystemStore().status?.liveEnabled).toBe(false); expect(useTradeStore().open).toHaveLength(0) })
  it('quote updates leave experiment reference unchanged', () => { applySnapshot(structuredClone(mockSnapshot)); const prior = useExperimentStore().experiments; applyEvent({ sequence: 1, type: 'market.quote.updated', at: 'MOCK', data: { ...mockSnapshot.market, quality: 'LIVE', bid: 1.1 } }); expect(useMarketStore().quote?.bid).toBe(1.1); expect(useExperimentStore().experiments).toBe(prior) })
  it('closed trade removes pending inventory through separate events', () => { applySnapshot(structuredClone(mockSnapshot)); const t = { id: 'MOCK', profile: 'EURUSD_R5', classification: 'SIMULATED_SHADOW', status: 'OPEN_SIMULATED' } as Trade; applyEvent({ sequence: 1, type: 'position.updated', at: 'MOCK', data: [t] }); expect(useTradeStore().open).toHaveLength(1); applyEvent({ sequence: 2, type: 'position.updated', at: 'MOCK', data: [] }); applyEvent({ sequence: 3, type: 'trade.completed', at: 'MOCK', data: [{ ...t, status: 'CLOSED' }] }); expect(useTradeStore().open).toHaveLength(0); expect(useTradeStore().closed).toHaveLength(1) })
  it('failed source marks retained values stale', () => { applySnapshot(structuredClone(mockSnapshot)); applyEvent({ sequence: 1, type: 'source.unavailable', at: 'MOCK', data: {} }); expect(useMarketStore().quote?.quality).toBe('STALE'); expect(useSystemStore().status?.postgres).toBe('UNKNOWN') })
  it('notifications are bounded and deduplicated', () => { const s = useNotificationStore(); for (let i = 0; i < 70; i++) s.add({ id: String(i), text: 'MOCK', kind: 'info' }); s.add({ id: '69', text: 'MOCK updated', kind: 'info' }); expect(s.items).toHaveLength(50); expect(s.items[0]?.text).toContain('updated') })
  it('chat failure causes one request without retries', async () => { const stub = vi.spyOn(api, 'chat').mockRejectedValue(new Error('MOCK')); await useSolStore().send('R5'); expect(stub).toHaveBeenCalledTimes(1); expect(useSolStore().messages[0]?.error).toContain('Sin reintento'); stub.mockRestore() })
  it('concurrent send cannot duplicate an in-flight request', async () => { let resolve: (x: typeof mockSol) => void = () => {}; const stub = vi.spyOn(api, 'chat').mockImplementation(() => new Promise(r => { resolve = r })); const s = useSolStore(); const first = s.send('R5'); await s.send('R5'); expect(stub).toHaveBeenCalledTimes(1); resolve(mockSol); await first; stub.mockRestore() })
})
describe('Realtime recovery', () => {
  const event = (sequence: number): RealtimeEvent => ({ sequence, type: 'MOCK', data: {}, at: 'MOCK' })
  it('sequence gap restores snapshot instead of applying uncertain delta', async () => { const refresh = vi.fn(async () => {}); const apply = vi.fn(); const s = new SequencedEvents(refresh, apply); await s.receive(event(1)); await s.receive(event(3)); expect(refresh).toHaveBeenCalledTimes(1); expect(apply).toHaveBeenCalledTimes(1) })
  it('duplicates and old deltas are ignored', async () => { const apply = vi.fn(); const s = new SequencedEvents(async () => {}, apply); await s.receive(event(4)); await s.receive(event(4)); await s.receive(event(3)); expect(apply).toHaveBeenCalledTimes(1) })
  it('server restart sequence resets after reconnect', async () => { const apply = vi.fn(); const s = new SequencedEvents(async () => {}, apply); await s.receive(event(80)); s.reset(); await s.receive(event(1)); expect(apply).toHaveBeenCalledTimes(2) })
  it('exponential reconnection is bounded', () => { expect(retryDelay(0)).toBe(1000); expect(retryDelay(3)).toBe(8000); expect(retryDelay(30)).toBe(30000) })
  it('unauthorized fetch does not retry or retain token', async () => { const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 401 })); await expect(request('dashboard')).rejects.toMatchObject({ status: 401 }); expect(fetcher).toHaveBeenCalledTimes(1); fetcher.mockRestore() })
})


describe('Exploratory Paper attribution', () => {
 it('rotation snapshot and realtime stay separate from execution commands', () => { const rotation = { nextProfile: 'EURUSD_R1' as const, cohort: 'MOCK', state: 'BLOCKED', globalStop: null }; applySnapshot({ ...structuredClone(mockSnapshot), rotation }); expect(useSystemStore().rotation?.nextProfile).toBe('EURUSD_R1'); applyEvent({ sequence: 1, type: 'rotation.updated', at: 'MOCK', data: { ...rotation, nextProfile: 'EURUSD_R5' } }); expect(useSystemStore().rotation?.nextProfile).toBe('EURUSD_R5'); expect(useSystemStore().status?.ordersSupported).toBe(false) })
 it('Paper card separates zero real fills from old Shadow metrics', () => { const experiment = { ...mockSnapshot.experiments[0]!, executionRole: 'BLOCKED', paperEquity: 100, paperReserved: 0, paperBlockers: ['COMMISSION_EXCEEDS_RISK_BUDGET'], brokerMetrics: { trades: 0, netPnl: 0, fees: 0 } }; const w = mount(ExperimentCard, { props: { experiment }, global: { stubs: { EquityChart: true } } }); expect(w.text()).toContain('IBKR PAPER: 0 cierres'); expect(w.text()).toContain('EXPLORATORY_NOT_VALIDATED'); expect(w.text()).toContain('COMMISSION_EXCEEDS_RISK_BUDGET') })
})
