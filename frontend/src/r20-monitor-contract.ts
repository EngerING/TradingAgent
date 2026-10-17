import { z } from 'zod'
const decimal=z.string().regex(/^-?\d+(\.\d+)?$/)
const position=z.object({position_id:z.string(),side:z.enum(['LONG','SHORT']),quantity:decimal,entry_price:decimal,stop:decimal,target:decimal,opened_at:z.string(),cost_total:decimal,
 purpose:z.enum(['NORMAL','TECHNICAL_VALIDATION']).optional(),economically_viable:z.boolean().optional(),
 sizing:z.object({exposure:decimal,initial_margin:decimal,net_target:decimal,net_stop:decimal,leverage_after_costs:decimal}).optional()})
export const monitorSchema=z.object({classification:z.literal('SYNTHETIC_VIRTUAL_LAB'),cohortStarted:z.literal(false),brokerOrders:z.literal(0),liveEnabled:z.literal(false),
 status:z.enum(['NOT_PREREGISTERED','PREPARED_REPLAY','STOPPING_MANAGING_SHADOW','STOPPED']),stopRequested:z.boolean(),
 positions:z.array(position),trades:z.array(z.object({position_id:z.string(),closed_at:z.string(),exit_price:decimal,reason:z.string(),gross:decimal,cost:decimal,net:decimal})),
 signals:z.array(z.object({at:z.string(),reason:z.string().nullable(),decision:z.object({side:z.string().nullable(),reason:z.string().nullable()}).nullable()})),
 equity:decimal.nullable(),realizedGross:decimal.nullable(),openGross:decimal.nullable(),exposure:decimal.nullable(),margin:decimal.nullable(),priceRisk:decimal.nullable(),
 costs:z.array(z.object({costId:z.string(),amount:decimal,status:z.string(),provenance:z.string()})),
 daily:z.object({remaining:decimal,used_loss:decimal,open_risk:decimal,pending_risk:decimal,loss_blocked:z.boolean(),operational_blocks:z.array(z.string())}).nullable(),
 accountingRevision:z.number().int().nullable(),accountingHash:z.string().nullable(),lifecycleRevision:z.number().int(),
 dataStatus:z.string(),lastObservation:z.string().nullable(),integrity:z.string(),
 purpose:z.enum(['NORMAL','TECHNICAL_VALIDATION']).nullable().optional(),
 effectiveProfile:z.object({configuration_hash:z.string(),risk_per_trade_pct:decimal,daily_loss_limit_pct:decimal,max_leverage:decimal,max_open_positions:z.number().int()}).nullable().optional(),
 netPnl:decimal.nullable().optional(),aggregateLeverage:decimal.nullable().optional(),intrabarProtection:z.string().optional(),
 lastAuthenticRead:z.object({at:z.string(),quoteAt:z.string(),bid:decimal,ask:decimal,sourceHash:z.string(),timestampBasis:z.string(),account:z.string(),
 classification:z.literal('AUTHENTIC_READ_ONLY_HISTORICAL_CUTOFF'),continuousFeed:z.literal(false)}).nullable().optional()})
export type Monitor=z.infer<typeof monitorSchema>
