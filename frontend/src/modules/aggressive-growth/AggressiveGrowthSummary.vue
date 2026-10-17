<script setup lang="ts">
import { computed } from 'vue'
import { useAggressiveGrowthStore } from '../../stores/aggressiveGrowth'
import { useSystemStore } from '../../stores'
import { decimalValue } from './contracts'
import { money, number } from '../../format'
const store = useAggressiveGrowthStore(); const system = useSystemStore()
const stale = computed(() => system.connection !== 'CONNECTED' || !!system.error || !!store.error)
</script>
<template>
  <section class="card r20-summary" data-testid="r20-summary" aria-labelledby="r20-summary-title">
    <div class="panel-heading"><div><span class="eyebrow">LABORATORIO INDEPENDIENTE · SHADOW_SIMULATED</span><h2 id="r20-summary-title">AGGRESSIVE GROWTH</h2></div><RouterLink to="/aggressive-growth">Ver R20 →</RouterLink></div>
    <p>Capital lógico inicial US$100 · R20 hasta 20% del equity por precio · límite 1:10.</p>
    <div v-if="store.view" class="r20-summary-values"><span>Equity <b>{{ money(decimalValue(store.view.equity)) }}</b></span><span>Exposición <b>{{ money(decimalValue(store.view.exposure)) }}</b></span><span>Apalancamiento <b>{{ number(decimalValue(store.view.effectiveLeverage)) }}×</b></span><span>Shadow / Paper <b>{{ store.view.shadowTrades }} / {{ store.view.paperTrades }}</b></span></div>
    <p v-else>DATA_UNAVAILABLE · Sin snapshot R20 confirmado.</p>
    <p class="small muted">{{ stale ? 'STALE · datos conservados' : store.view?.evidenceQuality ?? 'DATA_UNAVAILABLE' }} · {{ store.view?.runKind ?? 'Sin ejecución observada' }} · IBKR_PAPER BLOCKED.</p>
  </section>
</template>
<style scoped>
.r20-summary{margin-block:24px;overflow-wrap:anywhere;border-inline-start:3px solid var(--cyan)}.r20-summary .panel-heading{flex-wrap:wrap;gap:12px}.r20-summary a{color:var(--green);font-weight:600}.r20-summary p{font-size:12px}.r20-summary-values{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:20px 0}.r20-summary-values span{font-size:11px;color:var(--muted)}.r20-summary-values b{display:block;font-size:19px;color:var(--ink);margin-top:6px;font-variant-numeric:tabular-nums}@media(max-width:600px){.r20-summary-values{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
