import { computed } from 'vue'
import { useMarketStore, useKronosStore, useTradeStore } from '../stores'

// Presentation metadata comes from the read model, never from a sizing decision.
export function useInstrument() {
  const market = useMarketStore(); const kronos = useKronosStore(); const trades = useTradeStore()
  return {
    symbol: computed(() => market.quote?.symbol ?? trades.open[0]?.symbol ?? 'DATA_UNAVAILABLE'),
    timeframe: computed(() => kronos.view?.latest?.timeframe ?? 'UNKNOWN'),
  }
}
