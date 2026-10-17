// MOCK_TEST_ONLY: browser/unit fixture; never written to a journal or imported by production.
import type { AggressiveGrowthView } from '../modules/aggressive-growth/contracts'
export const mockAggressiveGrowth: AggressiveGrowthView = {
  experiment: 'MOCK_R20', profile: 'AGGRESSIVE_GROWTH_R20', strategy: 'AGGRESSIVE_TREND_BREAKOUT_V1', version: 'MOCK_V1',
  classification: 'SHADOW_SIMULATED', runKind: 'FORWARD', status: 'RUNNING', evidenceQuality: 'MOCK_TEST_ONLY',
  startedAt: '2026-10-09T12:00:00Z', updatedAt: '2026-10-09T12:05:00Z', initialCapital: '100', equity: '98.25',
  priceRiskFraction: '0.20', maxLeverage: '10', exposure: '850.25', effectiveLeverage: '8.653944', priceRisk: '13.5',
  commissions: '4', spread: '0.08', slippage: '0.6', margin: '85.025', financing: null, anticipatedTotalLoss: '18.18',
  realizedLoss: null, liquidationRisk: 'MODELED_ONLY', grossPnl: null, netPnl: null, shadowTrades: 0, paperTrades: 0,
  winRate: null, expectancy: null, drawdown: '1.75', maxDrawdown: '1.75', opportunities: 5, signals: 1,
  eligibility: { researchEligible: true, economicallyViable: 'UNKNOWN', statisticallyValidated: false, paperExecutionEligible: false },
  market: { status: 'LIVE', at: '2026-10-09T12:05:00Z', source: 'MOCK_TEST_ONLY' },
  kronos: { status: 'UNAVAILABLE', calibration: 'RAW_ONLY', calibratedProbability: null, predictionId: null, createdAt: null, agreement: null, reason: 'FORECAST_EXPIRED' },
  baseline: { equity: '100', netPnl: null, closedTrades: 0, leverage: '1', description: 'Mismas oportunidades, límite 1:1.' },
  lastNoTrade: { at: '2026-10-09T12:05:00Z', reason: 'BROKER_MINIMUM_EXCEEDS_BUDGET' }, lastAssessment: null,
  recentSignals: [{ id: 'MOCK_SIGNAL', at: '2026-10-09T12:00:00Z', timeframe: 60, side: 'LONG', reason: 'BROKER_MINIMUM_EXCEEDS_BUDGET', status: 'NO_TRADE' }],
  trades: [], paper: { classification: 'IBKR_PAPER', state: 'BLOCKED', blockers: ['SPECIFIC_ONE_USE_CONSENT_REQUIRED'], conditions: ['MARGIN_UNKNOWN'], authorizationGranted: false },
  xauStatus: 'PENDING_VERIFIED_DATA_AND_CONDITIONS',
}
