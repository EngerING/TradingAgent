import { z } from 'zod'
const decimal=z.string().regex(/^-?\d+(\.\d+)?$/)
const hash=z.string().regex(/^[a-f0-9]{64}$/)
export const fieldKeys=['risk_per_trade_pct','capital_allocation_pct','max_leverage','daily_loss_limit_pct','max_open_positions'] as const
export type Field=typeof fieldKeys[number]
export type Values=Record<Field,string>
const profile=z.object({configuration_version:z.number().int(),configuration_hash:hash,
 risk_per_trade_pct:decimal,capital_allocation_pct:decimal,max_leverage:decimal,daily_loss_limit_pct:decimal,max_open_positions:z.number().int(),
 effective_from:z.string(),effective_until:z.string(),economic_timezone:z.literal('America/Santo_Domingo')}).passthrough()
const daily=z.object({current_equity:decimal,reference:decimal,budget:decimal,used_loss:decimal,open_risk:decimal,pending_risk:decimal,remaining:decimal,
 loss_blocked:z.boolean(),inventory_verified:z.boolean(),operational_blocks:z.array(z.string()),open_terms:z.array(z.unknown()),pending_terms:z.array(z.unknown())}).passthrough()
const costs=z.object({spread:z.string(),tariff:z.string(),commissions:z.string(),slippage:z.string(),financing:z.string(),evidence:z.string(),brokerConfirmed:z.literal(false)})
const event=z.object({revision:z.number().int(),hash,previous:z.string(),actor:z.string(),at:z.string(),day:z.string(),
 lifecycle:z.enum(['DRAFT','VALIDATED','ACTIVATED_FOR_SHADOW']),values:z.record(z.string(),z.string()),profile:profile.nullable(),contextHash:hash,accountingHash:hash}).passthrough()
export const configurationSchema=z.object({revision:z.number().int(),lifecycle:z.string().nullable(),status:z.enum(['DRAFT','VALIDATED','ACTIVATED_FOR_SHADOW','EXPIRED','BLOCKED']),
 day:z.string(),timezone:z.literal('America/Santo_Domingo'),at:z.string(),currentProfile:profile.nullable(),latest:event.nullable(),history:z.array(event),daily:daily.nullable(),blockers:z.array(z.string()),
 accountingRevision:z.number().nullable(),accountingHash:hash.nullable(),classification:z.literal('SYNTHETIC_TEST_ONLY'),costProvenance:costs,executionEnabled:z.literal(false),cohortStarted:z.literal(false),ordersSupported:z.literal(false)})
const assessment=z.object({admitted:z.boolean(),reasons:z.array(z.string()),profile_hash:hash,input_hash:hash,quantity:decimal,
 price_risk:decimal,price_risk_budget:decimal,allocation:decimal,exposure:decimal,initial_margin:decimal,estimated_costs:decimal,net_target:decimal,net_stop:decimal,
 effective_risk_pct:decimal,leverage_after_costs:decimal,headroom:decimal,required_headroom:decimal,paper_execution_eligible:z.literal(false),statistically_validated:z.literal(false)}).passthrough()
export const previewSchema=z.object({profile:profile.nullable(),assessment:assessment.nullable(),blockers:z.array(z.string()),daily:daily.nullable(),classification:z.literal('SYNTHETIC_TEST_ONLY'),executionEnabled:z.literal(false),cohortStarted:z.literal(false),costProvenance:costs})
export type Configuration=z.infer<typeof configurationSchema>
export type Preview=z.infer<typeof previewSchema>
// Display only. Preserve the exact decimal in the response and accessible tooltip.
export function displayDecimal(value:string):string {
 const [whole,fraction='']=value.split('.')
 return fraction.length>6?`≈${whole}.${fraction.slice(0,6)}`:value
}

export async function configRequest(path:string,body?:unknown):Promise<unknown>{
 const response=await fetch('/api/r20-v2/'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',
  headers:body===undefined?{}:{'Content-Type':'application/json','X-R20-Configuration':'1'},body:body===undefined?undefined:JSON.stringify(body)})
 const payload:unknown=await response.json()
 if(!response.ok){const error=z.object({error:z.string()}).safeParse(payload);throw new Error(error.success?error.data.error:`HTTP_${response.status}`)}
 return payload
}
