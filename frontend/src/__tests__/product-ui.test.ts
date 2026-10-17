import { beforeEach,describe,it,expect,vi } from 'vitest'
import { createPinia,setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { applySnapshot,useSystemStore,useExperimentStore } from '../stores'
import SystemOverview from '../components/SystemOverview.vue'
import PaperReadiness from '../components/PaperReadiness.vue'
import ActivityPanel from '../components/ActivityPanel.vue'
import ExperimentCard from '../components/ExperimentCard.vue'
import TradesTable from '../components/TradesTable.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { SequencedEvents,QuoteBatcher } from '../realtime'
import { kronosOptions } from '../chart-options'
import { mockSnapshot } from './fixtures'
import type { Trade,RealtimeEvent,KronosPrediction } from '../types'
beforeEach(()=>{setActivePinia(createPinia());applySnapshot(structuredClone(mockSnapshot))})
const trade=(id:string,classification:Trade['classification']='SIMULATED_SHADOW'):Trade=>({id,profile:'EURUSD_R5',symbol:'EUR/USD',direction:'LONG',quantity:1,entry:1.12,currentPrice:null,stop:1.11,target:1.14,exit:null,openedAt:'2026-10-07T12:00:00Z',closedAt:null,durationSeconds:null,grossPnl:null,netPnl:null,commission:null,commissionStatus:'PENDING',spread:null,slippage:null,probability:null,expectedValue:null,regime:'UNKNOWN',entryReason:'MOCK_TEST_ONLY',exitReason:'',signalId:id,strategyVersion:'MOCK',classification,environment:'PAPER',protection:'UNKNOWN',status:'PENDING',outcome:null,exitCategory:null})
describe('Evidence-first product UI',()=>{
 it('connected realtime cannot claim IBKR availability',()=>{useSystemStore().connection='CONNECTED';const w=mount(SystemOverview);expect(w.text()).toContain('DATA UNAVAILABLE');expect(w.text()).toContain('CONNECTED');expect(w.text()).toContain('LOCAL');expect(w.text()).toContain('BLOCKED')})
 it('degraded and stale are warning states',()=>{for(const value of ['KRONOS_DEGRADED','STALE'])expect(mount(StatusBadge,{props:{value}}).classes()).toContain('warn')})
 it('Paper readiness exposes blockers without authorization controls',()=>{useSystemStore().rotation={nextProfile:'EURUSD_R5',cohort:'MOCK',state:'BLOCKED',globalStop:null};useExperimentStore().experiments[0]!.paperBlockers=['UNKNOWN_MARGIN'];const w=mount(PaperReadiness,{global:{stubs:{RouterLink:true}}});expect(w.text()).toContain('Próximo perfil Paper: R5');expect(w.text()).toContain('UNKNOWN_MARGIN');expect(w.findAll('button')).toHaveLength(0)})
 it('pending broker inventory remains separate from Shadow',()=>{const w=mount(ActivityPanel,{props:{trades:[trade('paper','BROKER_PAPER_EXECUTION'),trade('shadow')],open:true},global:{stubs:{TradesTable:true,RouterLink:true}}});const tables=w.findAllComponents(TradesTable);expect(tables).toHaveLength(2);expect(tables[0]!.props('trades')[0].id).toBe('paper');expect(tables[1]!.props('trades')[0].id).toBe('shadow')})
 it('profile displays real risk budget and unknown daily status',()=>{const w=mount(ExperimentCard,{props:{experiment:mockSnapshot.experiments[0]!},global:{stubs:{EquityChart:true}}});expect(w.text()).toContain('Presupuesto próximo');expect(w.text()).toContain('UNKNOWN');expect(w.text()).toContain('5%')})
 it('large trade histories render bounded pages',async()=>{const w=mount(TradesTable,{props:{trades:Array.from({length:60},(_,i)=>trade(String(i)))}});expect(w.findAll('tbody tr')).toHaveLength(25);await w.findAll('.table-pagination button')[1]!.trigger('click');expect(w.text()).toContain('26–50 de 60')})
 it('forecast never becomes historical candles and NOW is a separate clock marker',()=>{const p={timeframe:'1H',historical:[{at:'2026-10-07T12:00:00Z',open:1.12,high:1.13,low:1.11,close:1.125}],quantiles:[{at:'2026-10-07T13:00:00Z',median:1.126,p05:1.11,p95:1.14},{at:'2026-10-07T14:00:00Z',median:1.127,p05:1.10,p95:1.15}]} as KronosPrediction;const o=kronosOptions(p,Date.parse('2026-10-07T13:30:00Z')) as {series:{name:string;data:unknown[];markLine?:{data:{name:string;xAxis:number}[]}}[]};expect(o.series[0]!.data).toHaveLength(1);const f=o.series.find(s=>s.name==='KRONOS FORECAST')!;expect(f.data).toHaveLength(2);expect(f.markLine!.data.map(d=>d.xAxis)).toEqual([Date.parse('2026-10-07T13:00:00Z'),Date.parse('2026-10-07T13:30:00Z')])})
})
describe('Realtime ordering and render throttling',()=>{
 const event=(sequence:number,type='MOCK'):RealtimeEvent=>({sequence,type,data:{},at:'MOCK'})
 it('later delta waits for a gap snapshot before applying',async()=>{let release:()=>void=()=>{};const refresh=vi.fn(()=>new Promise<void>(r=>{release=r}));const applied:number[]=[];const s=new SequencedEvents(refresh,e=>applied.push(e.sequence));await s.receive(event(1));const gap=s.receive(event(3));await Promise.resolve();const next=s.receive(event(4));await Promise.resolve();expect(applied).toEqual([1]);release();await gap;await next;expect(applied).toEqual([1,4])})
 it('failed gap refresh does not advance sequence or suppress recovery',async()=>{let fail=true;const refresh=vi.fn(async()=>{if(fail)throw Error('MOCK')});const apply=vi.fn();const s=new SequencedEvents(refresh,apply);await s.receive(event(1));await expect(s.receive(event(3))).rejects.toThrow('MOCK');fail=false;await s.receive(event(3));expect(refresh).toHaveBeenCalledTimes(2);await s.receive(event(4));expect(apply).toHaveBeenCalledTimes(2)})
 it('quote bursts coalesce while position and commission events are delivered',()=>{let frame:FrameRequestCallback=()=>{};const apply=vi.fn();const schedule=vi.fn((f:FrameRequestCallback)=>{frame=f;return 1});const b=new QuoteBatcher(apply,schedule,vi.fn());b.receive(event(1,'market.quote.updated'));b.receive(event(2,'market.quote.updated'));b.receive(event(3,'position.updated'));b.receive(event(4,'trade.completed'));expect(schedule).toHaveBeenCalledTimes(1);frame(0);expect(apply.mock.calls.map(c=>c[0].sequence)).toEqual([3,4,2])})
 it('source loss cancels a scheduled quote before stale state',()=>{let frame:FrameRequestCallback=()=>{};const apply=vi.fn();const cancel=vi.fn();const b=new QuoteBatcher(apply,f=>{frame=f;return 1},cancel);b.receive(event(1,'market.quote.updated'));b.receive(event(2,'source.unavailable'));frame(0);expect(cancel).toHaveBeenCalledWith(1);expect(apply).toHaveBeenCalledTimes(1);expect(apply.mock.calls[0]![0].type).toBe('source.unavailable')})
})
