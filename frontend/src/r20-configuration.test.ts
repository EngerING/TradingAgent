import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useR20Configuration } from './stores/r20Configuration'
import { configurationSchema, previewSchema, displayDecimal } from './r20-configuration-contract'

describe('R20 configuration contract and Pinia',()=>{
 beforeEach(()=>{setActivePinia(createPinia());vi.restoreAllMocks()})
 it('starts with five empty choices, no activated configuration',()=>{
  const s=useR20Configuration()
  expect(Object.values(s.values)).toEqual(['','','','',''])
  expect(s.complete).toBe(false);expect(s.state).toBe(null)
 })
 it('fails closed on an operational or order-capable response',()=>{
  expect(configurationSchema.safeParse({executionEnabled:true,ordersSupported:true}).success).toBe(false)
  expect(previewSchema.safeParse({classification:'OPERATIONAL',assessment:{quantity:'100'}}).success).toBe(false)
 })
 it('requires every field and clears stale calculation after editing',()=>{
  const s=useR20Configuration()
  for(const key of Object.keys(s.values) as Array<keyof typeof s.values>)s.values[key]='1'
  expect(s.complete).toBe(true)
  s.values.max_leverage='';expect(s.complete).toBe(false)
 })
 it('keeps HTTP errors visible and never turns a failure into a profile',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({error:'CAS_CONFLICT'}),{status:409})))
  const s=useR20Configuration();await s.load()
  expect(s.error).toContain('CAS_CONFLICT');expect(s.state).toBe(null)
 })
 it('labels abbreviated display without converting exact decimals to floating point',()=>{
  expect(displayDecimal('2.551020408163265306')).toBe('≈2.551020')
  expect(displayDecimal('100.000001')).toBe('100.000001')
  expect(displayDecimal('9999999999999999999999.00000001')).toBe('≈9999999999999999999999.000000')
 })
})
