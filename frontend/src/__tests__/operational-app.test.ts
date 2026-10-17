import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { applySnapshot, applyEvent, useTradeStore, useMarketStore, useExperimentStore, useInterfaceStore } from '../stores'
import { useActivityStore } from '../stores/activity'
import AccountCard from '../modules/dashboard/AccountCard.vue'
import AgentCard from '../modules/dashboard/AgentCard.vue'
import OpenInventory from '../modules/trading/OpenInventory.vue'
import OpenTradeCard from '../modules/trading/OpenTradeCard.vue'
import TradeFeed from '../modules/trading/TradeFeed.vue'
import ProfileQuickCards from '../modules/experiments/ProfileQuickCards.vue'
import { useInstrument } from '../composables/useInstrument'
import { mockSnapshot } from './fixtures'
import type { Trade } from '../types'

const trade=(id:string,classification:Trade['classification']='SIMULATED_SHADOW'):Trade=>({id,profile:'EURUSD_R5',symbol:'EUR/USD',direction:'LONG',quantity:10,entry:1.12,currentPrice:null,stop:1.11,target:1.14,exit:null,openedAt:'2026-10-07T12:00:00Z',closedAt:null,durationSeconds:null,grossPnl:null,netPnl:null,commission:null,commissionStatus:'PENDING',spread:null,slippage:null,probability:null,expectedValue:null,regime:'UNKNOWN',entryReason:'MOCK_TEST_ONLY',exitReason:'',signalId:id,strategyVersion:'MOCK',classification,environment:'PAPER',protection:'UNKNOWN',status:'PENDING',outcome:null,exitCategory:null})
beforeEach(()=>{setActivePinia(createPinia());applySnapshot(structuredClone(mockSnapshot));useInterfaceStore().profile='EURUSD_R5'})
describe('Operational Home contracts',()=>{
  it('balance belongs to one selected virtual portfolio, not the broker account',()=>{const w=mount(AccountCard);expect(w.text()).toContain('EURUSD_R5');expect(w.text()).toContain('US$100.00');expect(w.text()).toContain('DATA_UNAVAILABLE');expect(w.text()).toContain('No es el saldo de IBKR')})
  it('missing portfolio metrics cannot become a fabricated equity',()=>{useExperimentStore().experiments=[];expect(mount(AccountCard).text()).toContain('DATA_UNAVAILABLE')})
  it('agent actions only navigate or open Sol; they cannot start or authorize trading',async()=>{const w=mount(AgentCard,{global:{stubs:{RouterLink:true}}});expect(w.text()).toContain('UNKNOWN');expect(w.findAll('button')).toHaveLength(1);await w.get('button').trigger('click');expect(useInterfaceStore().solRequested).toBe(1);expect(w.text()).toContain('UI NOT AUTHORIZED')})
  it('instrument metadata follows the read model instead of a hardcoded Forex label',()=>{useMarketStore().quote={...mockSnapshot.market,symbol:'F'};expect(useInstrument().symbol.value).toBe('F')})
  it('selecting a quick card changes presentation without altering risk',async()=>{const w=mount(ProfileQuickCards);const before=structuredClone(useExperimentStore().experiments[0]!.risk);await w.get('button').trigger('click');expect(useInterfaceStore().profile).toBe('EURUSD_R5');expect(useExperimentStore().experiments[0]!.risk).toEqual(before)})
  it('open positions retain Paper and Shadow in separate inventory columns',()=>{useTradeStore().open=[trade('paper','BROKER_PAPER_EXECUTION'),trade('shadow')];const w=mount(OpenInventory,{global:{stubs:{OpenTradeCard:true}}});const cards=w.findAllComponents(OpenTradeCard);expect(cards[0]!.props('trade').id).toBe('paper');expect(cards[1]!.props('trade').id).toBe('shadow')})
  it('pending commissions and unknown P&L are never presented as a completed win',()=>{const w=mount(OpenTradeCard,{props:{trade:trade('pending')}});expect(w.text()).toContain('PENDING');expect(w.text()).toContain('No evaluable');expect(w.text()).toContain('UNKNOWN · sin vínculo registrado')})
})
describe('Event feed and themes',()=>{
  it('snapshot provenance is explicit and NO_TRADE does not create a position',()=>{const feed=useActivityStore();expect(feed.items.some(i=>i.snapshot&&i.kind==='NO_TRADE')).toBe(true);expect(useTradeStore().open).toHaveLength(0)})
  it('quote updates coalesce one market row without deleting trade events',()=>{const feed=useActivityStore();applyEvent({sequence:2,type:'position.updated',data:[trade('1')],at:'2026-10-07T12:00:00Z'});for(let i=3;i<30;i++)applyEvent({sequence:i,type:'market.quote.updated',data:mockSnapshot.market,at:mockSnapshot.at});expect(feed.items.filter(i=>i.kind==='MARKET')).toHaveLength(1);expect(feed.items.some(i=>i.kind==='TRADE_OPEN')).toBe(true)})
  it('retains fills and commissions as trade updates with origin and pending state',()=>{const t=trade('1');applyEvent({sequence:2,type:'position.updated',data:[t],at:mockSnapshot.at});applyEvent({sequence:3,type:'position.updated',data:[{...t,quantity:5}],at:mockSnapshot.at});expect(useActivityStore().items.some(i=>i.kind==='TRADE_UPDATE'&&i.origin==='SIMULATED_SHADOW'&&i.detail.includes('PENDING'))).toBe(true)})
  it('bounded storage and virtual rows avoid rendering the whole feed',()=>{const feed=useActivityStore();for(let i=0;i<500;i++)feed.add({id:String(i),kind:'SYSTEM',title:'MOCK',detail:'MOCK',at:mockSnapshot.at,origin:'MOCK_TEST_ONLY'});const w=mount(TradeFeed);expect(feed.items).toHaveLength(300);expect(w.findAll('li')).toHaveLength(9)})
  it('reconnect snapshots do not duplicate unchanged fills',()=>{const s={...mockSnapshot,openPositions:[trade('1')]};applySnapshot(s);applySnapshot({...s,revision:2});expect(useActivityStore().items.filter(i=>i.tradeId==='1')).toHaveLength(1)})
  it('switching source studies cannot mix prior inventory into the event feed',()=>{applyEvent({sequence:2,type:'position.updated',data:[trade('prior')],at:mockSnapshot.at});applySnapshot({...mockSnapshot,studyId:'MOCK_OTHER_STUDY'});expect(useActivityStore().items.some(i=>i.tradeId==='prior')).toBe(false)})
  it('feed filtering preserves the stored audit origins',async()=>{const w=mount(TradeFeed);await w.get('select').setValue('NO_TRADE');expect(w.findAll('li').every(i=>i.attributes('data-kind')==='NO_TRADE')).toBe(true)})
  it('theme preference persists independently of trading controls',()=>{const ui=useInterfaceStore();ui.setTheme('light');expect(document.documentElement.dataset.theme).toBe('light');expect(localStorage.getItem('tradingagent-theme')).toBe('light');ui.setTheme('dark');expect(document.documentElement.dataset.theme).toBe('dark');expect(mockSnapshot.system.liveEnabled).toBe(false)})
})
