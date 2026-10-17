import { beforeEach,expect,it } from 'vitest'
import { createPinia,setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import PriceRiskExperiment from '../components/PriceRiskExperiment.vue'
import { useSystemStore,applyEvent } from '../stores'
import { useActivityStore } from '../stores/activity'
import type { PriceRiskView } from '../types'
beforeEach(()=>setActivePinia(createPinia()))
const state=():PriceRiskView=>({experiment:'test',classification:'SIMULATED_SHADOW',status:'SHADOW_RUNNING',equity:'100',updated_at:'2026-10-08T12:00:00Z',last_assessment:null,active:null,trades:[],paper:{state:'BLOCKED',blockers:['UNKNOWN']},events:[{id:'one',kind:'NO_TRADE',at:'2026-10-08T12:00:00Z',classification:'SIMULATED_SHADOW',detail:{reason:'NO_SIGNAL'}}]})
it('does not fabricate an unprepared experiment',()=>expect(mount(PriceRiskExperiment).find('section').exists()).toBe(false))
it('keeps costs unknown and paper blocked',()=>{useSystemStore().priceRisk=state();const text=mount(PriceRiskExperiment).text();expect(text).toContain('Paper BLOCKED');expect(text).toContain('R10 original');expect(text).not.toContain('NaN');expect(text).toContain('0 cierres virtuales')})
it('receives realtime evidence and deduplicates shadow lifecycle',()=>{const s=state();const e={sequence:1,type:'priceRisk.updated',at:s.updated_at,data:s};applyEvent(e);applyEvent(e);expect(useSystemStore().priceRisk?.experiment).toBe('test');expect(useActivityStore().items).toHaveLength(1);expect(useActivityStore().items[0]?.origin).toBe('SIMULATED_SHADOW')})
