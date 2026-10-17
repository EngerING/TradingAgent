import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { applySnapshot, applyEvent, useSystemStore, useTradeStore, useInterfaceStore, useKronosStore, useExperimentStore } from '../stores'
import { mockSnapshot } from './fixtures'
import { forecastCloseAt, visibleForecast, kronosOptions } from '../chart-options'
import type { KronosPrediction, KronosView, Trade } from '../types'
import AgentStatus from '../modules/dashboard/AgentStatus.vue'
import OpenInventory from '../modules/trading/OpenInventory.vue'
import ProfileQuickCards from '../modules/experiments/ProfileQuickCards.vue'
import SolChat from '../components/SolChat.vue'
import { useActivityStore } from '../stores/activity'

beforeEach(()=>{setActivePinia(createPinia());applySnapshot(structuredClone(mockSnapshot))})
const prediction:KronosPrediction={invalid_frequency:0,model:'MOCK_TEST_ONLY',created_at:'2026-10-07T13:00:00Z',lookback:1,pred_len:2,sample_count:0,raw_tp_frequency:null,raw_sl_frequency:null,neither_frequency:null,calibrated_probability:null,predicted_return_median:0,predicted_volatility:0,telemetry:{},prediction_id:'MOCK_TEST_ONLY',consensus:{kronos_direction:'UNKNOWN',technical_signal:null,consensus:'NO_SIGNAL',disagreements:[],economic_profiles:{}},timeframe:'1H',historical:[{at:'2026-10-07T12:00:00Z',open:1.12,high:1.13,low:1.11,close:1.125}],quantiles:[{at:'2026-10-07T13:00:00Z',median:1.126,p05:1.11,p95:1.14},{at:'2026-10-07T14:00:00Z',median:1.127,p05:1.10,p95:1.15}]}
describe('Truthful forecast display coordinates',()=>{
 it('plots a forecast CLOSE at its actual bar end, without altering the evidence',()=>{const before=structuredClone(prediction);expect(forecastCloseAt(prediction,prediction.quantiles[0]!.at)).toBe(Date.parse('2026-10-07T14:00:00Z'));expect(prediction).toEqual(before)})
 it('hides elapsed forecast points from the future segment without replacing them with observations',()=>{const rows=visibleForecast(prediction,Date.parse('2026-10-07T14:30:00Z'));expect(rows).toHaveLength(1);expect(rows[0]!.median).toBe(1.127);expect(prediction.historical).toHaveLength(1);expect(prediction.quantiles).toHaveLength(2)})
 it('unknown timeframe cannot silently become a one-hour forecast',()=>{expect(visibleForecast({...prediction,timeframe:'UNKNOWN'},0)).toEqual([])})
 it('retains NOW after the full forecast has expired and renders no fabricated future',()=>{const now=Date.parse('2026-10-08T00:00:00Z');const o=kronosOptions(prediction,now) as {series:{id?:string;data:unknown[];markLine?:{data:{name:string;xAxis:number}[]}}[]};const f=o.series.find(s=>s.id==='forecast')!;expect(f.data).toHaveLength(0);expect(f.markLine!.data.find(m=>m.name==='NOW · UTC')?.xAxis).toBe(now)})
})
describe('Operational research workspace',()=>{
 it('labels active Shadow separately from unknown IBKR availability',()=>{useSystemStore().studyStatus='SHADOW_RESEARCH_RUNNING';useSystemStore().connection='CONNECTED';const w=mount(AgentStatus,{global:{stubs:{RouterLink:true}}});expect(w.text()).toContain('Observando');expect(w.text()).toContain('SHADOW');expect(w.text()).not.toContain('IBKR CONNECTED')})
 it('stale source or disconnected UI cannot claim active observation',()=>{useSystemStore().studyStatus='SHADOW_RESEARCH_RUNNING';useSystemStore().connection='DISCONNECTED';expect(mount(AgentStatus,{global:{stubs:{RouterLink:true}}}).text()).toContain('Conexión interrumpida');useSystemStore().connection='CONNECTED';useSystemStore().error='DATA_UNAVAILABLE';expect(mount(AgentStatus,{global:{stubs:{RouterLink:true}}}).text()).toContain('Evidencia no disponible')})
 it('empty inventory states the last decision and exposes unknown next evaluation time',()=>{const w=mount(OpenInventory);expect(w.text()).toContain('Sin operación abierta');expect(w.text()).toContain('horario no expuesto');expect(w.text()).toContain('no sustituye la conciliación');expect(w.findAll('button')).toHaveLength(0)})
 it('profile risk and commissions come from the backend, while null win rate stays insufficient',()=>{const w=mount(ProfileQuickCards);expect(w.text()).toContain('Riesgo previsto');expect(w.text()).toContain('Comisiones');expect(w.text()).toContain('Wins / Losses');expect(w.text()).toContain('No evaluable')})
 it('missing metrics are not converted to a positive portfolio result',()=>{useExperimentStore().experiments[0]!.metrics=null;expect(mount(ProfileQuickCards).text()).toContain('DATA_UNAVAILABLE')})
 it('Sol suggestions follow the selected portfolio and explicitly say GPT is inactive',()=>{useInterfaceStore().profile='EURUSD_R10';useSystemStore().status={...mockSnapshot.system,solBudget:0};const w=mount(SolChat);expect(w.text()).toContain('Dame los resultados de R10');expect(w.text()).toContain('LOCAL EVIDENCE · GPT inactivo')})
 it('cost rejections and source errors have distinct truthful feed categories',()=>{applyEvent({sequence:3,type:'prediction.updated',at:mockSnapshot.at,data:{...mockSnapshot.prediction,decisions:{EURUSD_R1:{decision:'NO_TRADE',reason:'COMMISSION_EXCEEDS_RISK_BUDGET'}}}});applyEvent({sequence:4,type:'source.unavailable',data:{},at:mockSnapshot.at});expect(useActivityStore().items.some(i=>i.kind==='COST_REJECTION')).toBe(true);expect(useActivityStore().items.some(i=>i.kind==='ERROR')).toBe(true);expect(useTradeStore().open).toHaveLength(0)})
 it('a reconciled position delta updates displayed P&L without recalculating it in Vue',async()=>{
 const t={id:'MOCK_TEST_ONLY',profile:'EURUSD_R5',symbol:'EUR/USD',direction:'LONG',quantity:10,entry:1.12,currentPrice:1.121,stop:1.11,target:1.14,exit:null,openedAt:'2026-10-08T03:00:00Z',closedAt:null,durationSeconds:60,grossPnl:.01,netPnl:null,commission:null,commissionStatus:'PENDING',spread:null,slippage:null,probability:null,expectedValue:null,regime:'UNKNOWN',entryReason:'MOCK_TEST_ONLY',exitReason:'',signalId:'MOCK',strategyVersion:'MOCK',classification:'SIMULATED_SHADOW',environment:'SHADOW',protection:'UNKNOWN',status:'PENDING',outcome:null,exitCategory:null} as Trade
 applyEvent({sequence:11,type:'position.updated',data:[t],at:mockSnapshot.at});const w=mount(OpenInventory);expect(w.text()).toContain('PENDING')
 applyEvent({sequence:12,type:'position.updated',data:[{...t,commission:2,commissionStatus:'CONFIRMED',netPnl:-1.99,currentPrice:1.122}],at:mockSnapshot.at});await nextTick();expect(w.text()).toContain('-US$1.99');expect(w.text()).toContain('CONFIRMED');expect(useSystemStore().status?.ordersSupported).toBe(false)
 })
 it('a forecast update does not manufacture trade P&L or authorize execution',()=>{applyEvent({sequence:9,type:'kronos.updated',data:{latest:prediction,status:'KRONOS_DEGRADED',calibrationState:'RAW_ONLY'} as KronosView,at:mockSnapshot.at});expect(useKronosStore().view?.latest?.quantiles).toHaveLength(2);expect(useTradeStore().open as Trade[]).toHaveLength(0);expect(useSystemStore().status?.ordersSupported).toBe(false)})
})
