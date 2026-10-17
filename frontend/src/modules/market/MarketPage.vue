<script setup lang="ts">
import AdvancedPage from '../../app/AdvancedPage.vue'
import { number, date } from '../../format'
import StatusBadge from '../../components/StatusBadge.vue'
import { computed, defineAsyncComponent } from 'vue'
import { useMarketStore,usePredictionStore } from '../../stores'
import type { Json } from '../../types'
import { useInstrument } from '../../composables/useInstrument'
import MarketQuoteCard from '../../components/MarketQuoteCard.vue'
import SignalCard from '../../components/SignalCard.vue'
import MetricCard from '../../components/MetricCard.vue'
import KronosCard from '../../components/KronosCard.vue'
const EquityChart=defineAsyncComponent(()=>import('../../components/EquityChart.vue'))
const market=useMarketStore();const prediction=usePredictionStore();const {symbol}=useInstrument()
const features=computed(()=>{const f=market.quote?.features;const v=f?.indicators;return v&&typeof v==='object'&&!Array.isArray(v)?f!:prediction.current?.features ?? {}})
const featureOrigin=computed(()=>Object.keys(features.value).length?features.value===market.quote?.features?'QUOTE_FEATURES':'SHADOW_SIGNAL_FEATURES':'UNKNOWN')
const indicators=computed(()=>{const v=features.value.indicators;return v&&typeof v==='object'&&!Array.isArray(v)?v:{}})
const featureAt=computed(()=>typeof features.value.at==='string'?features.value.at:null)
function display(v:Json|undefined){return v==null?'DATA_UNAVAILABLE':typeof v==='number'?number(v,5):String(v)}
</script>
<template><AdvancedPage title="Mercado" description="Cotizaciones y forecasts separados; procedencia y calidad visibles."><div class="two-column"><MarketQuoteCard :quote="market.quote" /><SignalCard :prediction="prediction.current" /></div><section class="card"><h3>Precio observado</h3><EquityChart :chart="{ title: symbol + ' observado', unit: typeof market.quote?.features.price_unit==='string'?market.quote.features.price_unit:'Unidad no expuesta', series: [{ name: symbol, points: market.quote?.series ?? [] }] }" /><p class="small muted">El contrato de serie está preparado; sin archivo temporal utilizable no se fabrica una curva.</p></section><section class="card"><div class="panel-heading"><h3>Features calculadas por Python</h3><StatusBadge :value="prediction.current?.regime ?? 'DATA_UNAVAILABLE'" /></div><p class="small muted feature-provenance">{{ featureOrigin }} · {{ features.feature_source ?? 'UNKNOWN' }} · {{ date(featureAt) }}. Valores registrados; sin recalcular indicadores en Vue.</p><div class="features-grid"><MetricCard v-for="key in ['ema20', 'ema50', 'ema_fast', 'ema_slow', 'rsi', 'macd', 'macd_signal', 'macd_histogram', 'atr', 'log_return_std', 'atr_ratio', 'trend', 'volatility']" :key="key" :label="key" :value="display(indicators[key])" /><MetricCard label="Momentum 4 velas" :value="display(features.momentum_4_bars)" /><MetricCard label="Soporte" :value="display(features.support)" /><MetricCard label="Resistencia" :value="display(features.resistance)" /><MetricCard label="Liquidez" value="UNKNOWN" note="CASH midpoint no acredita volumen negociado" /></div></section><KronosCard /></AdvancedPage></template>
