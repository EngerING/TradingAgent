import { describe,it,expect } from 'vitest'
import { preparationPreviewSchema,preparationSchema,preparationFields } from './r20-preparation-contract'
describe('Phase 2 preparation contracts',()=>{
 it('has six explicit economic controls, with allocation distinct from leverage',()=>{
  expect(preparationFields).toHaveLength(6)
  expect(preparationFields).toContain('allocation_usd')
  expect(preparationFields).toContain('requested_allocation_leverage')
  expect(preparationFields).not.toContain('max_leverage')
 })
 it('preserves unknown values and rejects claims of execution authority',()=>{
  const p={contractVersion:2,classification:'SYNTHETIC_TEST_ONLY',structurallyValid:false,
   validationErrors:['EXPLICIT_VALUES_REQUIRED'],unknowns:['MARGIN_POLICY_UNKNOWN'],
   exposure_target_usd:'400',target_account_leverage:'4',account_leverage:null,aggregate_leverage_cap:null,
   assessment:null,solverProfile:null,confirmed_margin_usd:null,executionEnabled:false,ordersSupported:false,cohortStarted:false}
  expect(preparationPreviewSchema.parse(p).confirmed_margin_usd).toBeNull()
  expect(preparationPreviewSchema.safeParse({...p,executionEnabled:true}).success).toBe(false)
  expect(preparationPreviewSchema.safeParse({...p,exposure_target_usd:400}).success).toBe(false)
 })
 it('never accepts an activated profile or enabled control in phase 2',()=>{
  expect(preparationSchema.safeParse({activeProfile:{},executionEnabled:true}).success).toBe(false)
 })
})
