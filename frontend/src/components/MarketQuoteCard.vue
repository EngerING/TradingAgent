<script setup lang="ts">
import type { MarketQuote } from '../types'
import { number, date } from '../format'
import StatusBadge from './StatusBadge.vue'
defineProps<{ quote: MarketQuote | null }>()
</script>
<template><section class="card"><div class="panel-heading"><div><span class="eyebrow">MERCADO · IBKR PAPER</span><h3>{{ quote?.symbol ?? 'DATA_UNAVAILABLE' }} <small>{{ quote?.source ?? 'UNKNOWN' }}</small></h3></div><StatusBadge :value="quote?.quality ?? 'MISSING'" /></div><div class="quote-grid"><div><span>Bid</span><strong>{{ number(quote?.bid, 5) }}</strong></div><div><span>Ask</span><strong>{{ number(quote?.ask, 5) }}</strong></div><div><span>Spread</span><strong>{{ number(quote?.spread, 5) }}</strong></div></div><div class="quote-footer"><StatusBadge :value="quote?.marketStatus ?? 'UNKNOWN'" /><span>{{ date(quote?.at) }}</span></div><p class="small muted">Timestamp de recepción del callback · {{ quote?.source ?? 'DATA_UNAVAILABLE' }}. Cotizaciones obsoletas no habilitan ejecución.</p></section></template>
