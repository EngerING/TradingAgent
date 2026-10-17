import { describe,it,expect } from 'vitest'
import { mount } from '@vue/test-utils'
import R20ShadowMonitor from './modules/r20-configuration/R20ShadowMonitor.vue'
import { monitorSchema } from './r20-monitor-contract'

describe('R20 read-only monitoring',()=>{
 it('shows unavailable without inventing equity or activity',()=>{
  const w=mount(R20ShadowMonitor,{props:{snapshot:null,error:''}})
  expect(w.text()).toContain('Sin evidencia del ciclo')
  expect(w.text()).not.toContain('100 USD')
 })
 it('rejects broker authority and unlabelled data',()=>{
  expect(monitorSchema.safeParse({brokerOrders:1,liveEnabled:true}).success).toBe(false)
 })
 it('keeps prior evidence visibly stale on error',()=>{
  const w=mount(R20ShadowMonitor,{props:{snapshot:null,error:'UNAVAILABLE'}})
  expect(w.text()).toContain('STALE')
 })
})
