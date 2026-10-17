import { z } from 'zod'
import { previewSchema } from './r20-configuration-contract'
const decimal=z.string().regex(/^-?\d+(\.\d+)?$/)
const hash=z.string().regex(/^[a-f0-9]{64}$/)
export const purposeSchema=z.enum(['NORMAL','TECHNICAL_VALIDATION'])
export const preparationFields=['logical_capital_usd','allocation_usd','requested_allocation_leverage',
 'risk_per_trade_pct','daily_loss_limit_pct','max_open_positions'] as const
export type PreparationField=typeof preparationFields[number]
export type PreparationValues=Record<PreparationField,string>&{environment:'SHADOW'|'IBKR_PAPER'}
const values=z.object({logical_capital_usd:decimal,allocation_usd:decimal,requested_allocation_leverage:decimal,
 risk_per_trade_pct:decimal,daily_loss_limit_pct:decimal,max_open_positions:z.string().regex(/^\d+$/),environment:z.enum(['SHADOW','IBKR_PAPER'])}).strict()
const profile=z.object({contract_version:z.literal(2),configuration_version:z.number().int(),profile_id:z.string(),scope:z.string(),values,
 effective_from:z.string(),effective_until:z.string(),created_at:z.string(),economic_timezone:z.literal('America/Santo_Domingo'),
 purpose:purposeSchema,activation:z.literal('NOT_ACTIVATED'),configuration_hash:hash}).strict()
const event=z.object({revision:z.number().int(),previous:z.string(),requestId:z.string(),requestHash:hash,actor:z.string(),at:z.string(),
 lifecycle:z.enum(['GUARDADO','VALIDO']),profile,contextHash:hash,hash,executionEnabled:z.literal(false),activation:z.literal('NOT_ACTIVATED')}).strict()
export const preparationSchema=z.object({contractVersion:z.literal(2),classification:z.literal('SYNTHETIC_TEST_ONLY'),revision:z.number().int(),
 latest:event.nullable(),history:z.array(event),status:z.enum(['GUARDADO','VALIDO','NO_ACTIVADO','EXPIRED']),activeProfile:z.null(),
 executionEnabled:z.literal(false),ordersSupported:z.literal(false),cohortStarted:z.literal(false),
 timezone:z.literal('America/Santo_Domingo'),at:z.string(),day:z.string(),
 controls:z.object({start:z.literal(false),stop:z.literal(false),switchEnvironment:z.literal(false),effectiveEnvironment:z.null(),reason:z.string()}).strict(),
 readiness:z.object({shadow:z.literal('BLOCKED'),paper:z.literal('BLOCKED'),live:z.literal('BLOCKED'),reasons:z.array(z.string())}).strict(),
 safety:z.object({emergency:z.string(),live:z.string(),ibkr:z.string(),observedAt:z.string().nullable(),provenance:z.string()}).strict(),
 costProvenance:z.object({commissions:z.string(),slippage:z.string(),financing:z.string(),evidence:z.string()}).passthrough()}).strict()
export const preparationPreviewSchema=z.object({contractVersion:z.literal(2),classification:z.literal('SYNTHETIC_TEST_ONLY'),
 structurallyValid:z.boolean(),validationErrors:z.array(z.string()),unknowns:z.array(z.string()),
 exposure_target_usd:decimal.nullable(),target_account_leverage:decimal.nullable(),account_leverage:decimal.nullable(),
 aggregate_leverage_cap:decimal.nullable(),assessment:previewSchema.shape.assessment,solverProfile:previewSchema.shape.profile,
 confirmed_margin_usd:decimal.nullable(),executionEnabled:z.literal(false),ordersSupported:z.literal(false),cohortStarted:z.literal(false)}).strict()
export type Preparation=z.infer<typeof preparationSchema>
export type PreparationPreview=z.infer<typeof preparationPreviewSchema>
