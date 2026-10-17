import { z } from 'zod'

const decimalPattern = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/
/** Conversion for display only; all sizing and accounting remain on the server. */
export function decimalValue(value: unknown): number | null {
  if (typeof value !== 'string' || !decimalPattern.test(value)) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}
const decimal = z.string().refine(value => decimalValue(value) !== null).nullable()
const count = z.number().int().nonnegative()
const runKind = z.enum(['FORWARD', 'HISTORICAL'])
const nullableText = z.string().nullable()
const trade = z.object({
  id: z.string(), classification: z.literal('SHADOW_SIMULATED'), runKind,
  side: z.string(), timeframe: z.number(), at: z.string(), closedAt: nullableText,
  entry: decimal, quantity: decimal, exposure: decimal, leverage: decimal, stop: decimal, target: decimal,
  priceRisk: decimal, commissions: decimal, totalExpectedLoss: decimal, exit: decimal,
  grossPnl: decimal, netPnl: decimal, reason: nullableText,
})
export const aggressiveGrowthSchema = z.object({
  experiment: z.string(), profile: z.literal('AGGRESSIVE_GROWTH_R20'), strategy: z.literal('AGGRESSIVE_TREND_BREAKOUT_V1'),
  version: z.string(), classification: z.literal('SHADOW_SIMULATED'), runKind, status: z.string(), evidenceQuality: z.string(),
  startedAt: z.string(), updatedAt: z.string(), initialCapital: decimal, equity: decimal, priceRiskFraction: decimal,
  maxLeverage: decimal, exposure: decimal, effectiveLeverage: decimal, priceRisk: decimal, commissions: decimal,
  spread: decimal, slippage: decimal, margin: decimal, financing: decimal, anticipatedTotalLoss: decimal,
  realizedLoss: decimal, liquidationRisk: z.string(), grossPnl: decimal, netPnl: decimal,
  shadowTrades: count, paperTrades: count, winRate: decimal, expectancy: decimal, drawdown: decimal, maxDrawdown: decimal,
  opportunities: count, signals: count,
  eligibility: z.object({ researchEligible: z.boolean(), economicallyViable: z.enum(['UNKNOWN', 'POSITIVE_TARGET_AFTER_ESTIMATED_COSTS', 'NEGATIVE_TARGET_AFTER_ESTIMATED_COSTS']), statisticallyValidated: z.literal(false), paperExecutionEligible: z.literal(false) }),
  market: z.object({ status: z.string(), at: nullableText, source: z.string() }),
  kronos: z.object({ status: z.string(), calibration: z.literal('RAW_ONLY'), calibratedProbability: z.null(), predictionId: nullableText, createdAt: nullableText, agreement: nullableText, reason: nullableText }),
  baseline: z.object({ equity: decimal, netPnl: decimal, closedTrades: count, leverage: z.literal('1'), description: z.string() }),
  lastNoTrade: z.object({ at: z.string(), reason: z.string() }).nullable(), lastAssessment: z.record(z.string(), z.unknown()).nullable(),
  recentSignals: z.array(z.object({ id: z.string(), at: z.string(), timeframe: z.number(), side: nullableText, reason: nullableText, status: z.string() })),
  trades: z.array(trade),
  paper: z.object({ classification: z.literal('IBKR_PAPER'), state: z.literal('BLOCKED'), blockers: z.array(z.string()), conditions: z.array(z.string()), authorizationGranted: z.literal(false) }),
  xauStatus: z.string(),
})
export type AggressiveGrowthView = z.infer<typeof aggressiveGrowthSchema>
