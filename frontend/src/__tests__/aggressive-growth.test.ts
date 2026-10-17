import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { applyEvent, applySnapshot, useExperimentStore, useSystemStore } from '../stores'
import { useAggressiveGrowthStore } from '../stores/aggressiveGrowth'
import { useActivityStore } from '../stores/activity'
import { money } from '../format'
import { decimalValue } from '../modules/aggressive-growth/contracts'
import AggressiveGrowthPage from '../modules/aggressive-growth/AggressiveGrowthPage.vue'
import { SequencedEvents } from '../realtime'
import { mockSnapshot } from './fixtures'
import { mockAggressiveGrowth } from './aggressive-growth-fixture'

beforeEach(() => { setActivePinia(createPinia()); useSystemStore().connection = 'CONNECTED' })
const render = () => mount(AggressiveGrowthPage)
describe('R20 independent read model', () => {
  it('hydrates and updates R20 without changing historical cohorts', async () => {
    applySnapshot({ ...structuredClone(mockSnapshot), aggressiveGrowth: structuredClone(mockAggressiveGrowth) })
    const history = useExperimentStore().experiments
    const events = new SequencedEvents(async () => {}, applyEvent)
    await events.receive({ sequence: 1, type: 'aggressiveGrowth.updated', at: 'MOCK', data: { ...mockAggressiveGrowth, equity: '97.5' } })
    await events.receive({ sequence: 1, type: 'aggressiveGrowth.updated', at: 'MOCK', data: { ...mockAggressiveGrowth, equity: '999' } })
    expect(useAggressiveGrowthStore().view?.equity).toBe('97.5')
    expect(useExperimentStore().experiments).toBe(history)
  })
  it('clears an absent R20 snapshot instead of retaining another experiment', () => {
    applySnapshot({ ...structuredClone(mockSnapshot), aggressiveGrowth: mockAggressiveGrowth })
    applySnapshot(structuredClone(mockSnapshot))
    expect(useAggressiveGrowthStore().view).toBeNull()
  })
  it('rejects an authority-bearing or misclassified R20 payload', () => {
    const store = useAggressiveGrowthStore()
    store.update({ ...mockAggressiveGrowth, classification: 'IBKR_PAPER' })
    expect(store.view).toBeNull(); expect(store.error).toContain('DATA_UNAVAILABLE')
    store.update({ ...mockAggressiveGrowth, paper: { ...mockAggressiveGrowth.paper, authorizationGranted: true } })
    expect(store.view).toBeNull()
  })
  it('attributes and deduplicates R20 signals in the existing activity feed', () => {
    applySnapshot({ ...structuredClone(mockSnapshot), aggressiveGrowth: mockAggressiveGrowth })
    applyEvent({ sequence: 2, type: 'aggressiveGrowth.updated', at: 'MOCK', data: mockAggressiveGrowth })
    const rows = useActivityStore().items.filter(row => row.origin === 'SHADOW_SIMULATED')
    expect(rows).toHaveLength(1)
    expect(rows[0]?.kind).toBe('NO_TRADE')
    expect(rows[0]?.detail).toContain('BROKER_MINIMUM_EXCEEDS_BUDGET')
  })
  it.each([null, undefined, '', ' ', 'NaN', 'Infinity', '0x10'])('does not turn missing or invalid decimal %s into zero', value => {
    expect(decimalValue(value)).toBeNull()
  })
  it('preserves authentic zero and signed decimal values', () => {
    expect(decimalValue('0')).toBe(0); expect(decimalValue('-3.938')).toBe(-3.938)
  })
})
describe('R20 honest presentation', () => {
  it('explains the absence of evidence', () => {
    const page = render()
    expect(page.text()).toContain('DATA_UNAVAILABLE')
    expect(page.text()).toContain('No hay un snapshot R20')
  })
  it('separates price risk, costs, unknown performance and blocked Paper', () => {
    useAggressiveGrowthStore().update(mockAggressiveGrowth)
    const page = render()
    expect(page.text()).toContain('20%'); expect(page.text()).toContain('1:10')
    expect(page.text()).toContain('SHADOW_SIMULATED'); expect(page.text()).toContain('IBKR_PAPER')
    expect(page.text()).toContain('El stop no garantiza una pérdida máxima')
    expect(page.get('[data-testid="r20-financing"]').text()).toContain('No evaluable')
    expect(page.get('[data-testid="r20-net-pnl"]').text()).toContain('No evaluable')
    expect(page.get('[data-testid="r20-drawdown"]').text()).toContain(money(1.75))
    expect(page.get('[data-testid="r20-drawdown"]').text()).not.toContain('%')
    expect(page.get('[data-testid="r20-paper"]').text()).toContain('0 operaciones')
    expect(page.get('[data-testid="r20-paper"]').text()).toContain('Sin resultados realizados')
    expect(page.text()).toContain('BROKER_MINIMUM_EXCEEDS_BUDGET')
    expect(page.text()).toContain('RAW_ONLY'); expect(page.text()).toContain('Probabilidad calibrada: No evaluable')
    expect(page.findAll('button')).toHaveLength(0)
  })
  it('marks retained data STALE on disconnection and source errors', async () => {
    useAggressiveGrowthStore().update(mockAggressiveGrowth)
    const page = render(); useSystemStore().connection = 'DISCONNECTED'; await nextTick()
    expect(page.get('[data-testid="r20-freshness"]').text()).toContain('STALE')
    useSystemStore().connection = 'CONNECTED'; useSystemStore().error = 'DATA_UNAVAILABLE'; await nextTick()
    expect(page.get('[data-testid="r20-freshness"]').text()).toContain('STALE')
  })
  it('labels historical evidence explicitly and does not infer calibrated support', () => {
    useAggressiveGrowthStore().update({ ...mockAggressiveGrowth, runKind: 'HISTORICAL' })
    expect(render().text()).toContain('HISTORICAL'); expect(render().text()).toContain('FORECAST_EXPIRED')
  })
})
