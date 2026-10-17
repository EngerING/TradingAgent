import {describe,it,expect} from 'vitest'
import {createPinia,setActivePinia} from 'pinia'
import {useR20Preparation} from './stores/r20Preparation'
import {purposeSchema} from './r20-preparation-contract'
describe('Technical Shadow preparation',()=>{
 it('accepts only explicit purposes',()=>{
  expect(purposeSchema.parse('TECHNICAL_VALIDATION')).toBe('TECHNICAL_VALIDATION')
  expect(purposeSchema.safeParse('PAPER_TECHNICAL').success).toBe(false)
 })
 it('does not select missing operating limits or technical mode implicitly',()=>{
  setActivePinia(createPinia());const s=useR20Preparation()
  expect(s.purpose).toBe('NORMAL')
  expect(s.values.risk_per_trade_pct).toBe('')
  expect(s.values.daily_loss_limit_pct).toBe('')
  expect(s.values.max_open_positions).toBe('')
  expect(s.complete).toBe(false)
 })
})
