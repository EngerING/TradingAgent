<script setup lang="ts">
import { computed } from 'vue'
import AdvancedPage from '../../app/AdvancedPage.vue'
import { useAggressiveGrowthStore } from '../../stores/aggressiveGrowth'
import { useSystemStore } from '../../stores'
import { decimalValue } from './contracts'
import { money, number, percent, date } from '../../format'
const store = useAggressiveGrowthStore(); const system = useSystemStore()
const view = computed(() => store.view)
const stale = computed(() => system.connection !== 'CONNECTED' || !!system.error || !!store.error)
const usd = (value: unknown) => money(decimalValue(value))
const ratio = (value: unknown) => percent(decimalValue(value))
const leverage = (value: unknown) => decimalValue(value) === null ? 'No evaluable' : `${number(decimalValue(value))}×`
const performance = computed(() => view.value ? [
  { label: 'P&L bruto', value: usd(view.value.grossPnl) }, { label: 'P&L neto', value: usd(view.value.netPnl), test: 'r20-net-pnl' },
  { label: 'Operaciones Shadow', value: view.value.shadowTrades }, { label: 'Win rate', value: ratio(view.value.winRate) },
  { label: 'Expectancy', value: usd(view.value.expectancy) }, { label: 'Drawdown actual · USD', value: usd(view.value.drawdown), test: 'r20-drawdown' },
  { label: 'Drawdown máximo · USD', value: usd(view.value.maxDrawdown) }, { label: 'Pérdida realizada', value: usd(view.value.realizedLoss) },
] : [])
const costs = computed(() => view.value ? [
  { label: 'Riesgo previsto por precio', value: usd(view.value.priceRisk) }, { label: 'Comisiones', value: usd(view.value.commissions) },
  { label: 'Spread', value: usd(view.value.spread) }, { label: 'Slippage', value: usd(view.value.slippage) },
  { label: 'Margen modelado', value: usd(view.value.margin) }, { label: 'Financiación', value: usd(view.value.financing), test: 'r20-financing' },
  { label: 'Pérdida total prevista', value: usd(view.value.anticipatedTotalLoss) }, { label: 'Riesgo de liquidación', value: view.value.liquidationRisk },
] : [])
const recentTrades = computed(() => [...(view.value?.trades ?? [])].sort((a,b) => Date.parse(b.at) - Date.parse(a.at)).slice(0,25))
const recentSignals = computed(() => [...(view.value?.recentSignals ?? [])].sort((a,b) => Date.parse(b.at) - Date.parse(a.at)).slice(0,20))
</script>
<template>
  <AdvancedPage title="AGGRESSIVE GROWTH" description="R20 · laboratorio de investigación independiente · EUR/USD · 1H y 4H.">
    <div class="r20-workspace" data-testid="aggressive-growth">
      <p v-if="store.error" class="error-banner" role="alert">{{ store.error }}</p>
      <section v-if="!view" class="card" role="status"><h2>DATA_UNAVAILABLE</h2><p>No hay un snapshot R20 confirmado. Equity, señales y resultados requieren evidencia del journal.</p><p>Perfil previsto: US$100 lógicos, riesgo por precio hasta 20% del equity y exposición máxima 1:10. IBKR_PAPER permanece bloqueado.</p></section>
      <template v-else>
        <section class="card r20-capital" aria-labelledby="r20-capital-title">
          <div class="panel-heading"><div><span class="eyebrow">{{ view.classification }} · {{ view.runKind }}</span><h2 id="r20-capital-title">Capital experimental</h2></div><span class="pill" data-testid="r20-freshness">{{ stale ? 'STALE · datos conservados' : view.evidenceQuality }} · {{ view.status }}</span></div>
          <dl class="r20-metrics r20-primary"><div><dt>Capital inicial</dt><dd>{{ usd(view.initialCapital) }}</dd></div><div><dt>Equity actual</dt><dd>{{ usd(view.equity) }}</dd></div><div><dt>R20 · riesgo por precio</dt><dd>{{ ratio(view.priceRiskFraction) }}</dd></div><div><dt>Límite de apalancamiento</dt><dd>{{ decimalValue(view.maxLeverage) === null ? 'No evaluable' : `1:${number(decimalValue(view.maxLeverage))}` }}</dd></div></dl>
          <dl class="r20-metrics"><div><dt>Exposición nominal actual</dt><dd>{{ usd(view.exposure) }}</dd></div><div><dt>Apalancamiento efectivo</dt><dd>{{ leverage(view.effectiveLeverage) }}</dd></div><div><dt>Oportunidades evaluadas</dt><dd>{{ view.opportunities }}</dd></div><div><dt>Señales auténticas registradas</dt><dd>{{ view.signals }}</dd></div></dl>
          <p class="r20-warning">El stop no garantiza una pérdida máxima. Comisiones, gaps y slippage pueden superar el riesgo previsto por precio.</p>
          <p class="small muted">Equity lógico de la cohorte; no utiliza el BuyingPower de IBKR. Actualizado {{ date(view.updatedAt) }}.</p>
        </section>

        <div class="r20-columns">
          <section class="card" aria-labelledby="r20-results-title"><span class="eyebrow">SHADOW_SIMULATED · {{ view.runKind }}</span><h2 id="r20-results-title">Resultados observados</h2><dl class="r20-metrics r20-pairs"><div v-for="item in performance" :key="item.label" :data-testid="item.test"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div></dl><p class="small muted">Las métricas sin evidencia permanecen desconocidas. No acreditan rentabilidad ni validación estadística.</p></section>
          <section class="card" aria-labelledby="r20-costs-title"><span class="eyebrow">MODELO DE COSTOS · USD</span><h2 id="r20-costs-title">Riesgo y costos separados</h2><dl class="r20-metrics r20-pairs"><div v-for="item in costs" :key="item.label" :data-testid="item.test"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div></dl><p class="small muted">El margen es una reserva; no es una comisión. La pérdida total prevista es una estimación.</p></section>
        </div>

        <section class="card" aria-labelledby="r20-eligibility-title"><h2 id="r20-eligibility-title">Elegibilidad experimental</h2><dl class="r20-metrics"><div><dt>RESEARCH_ELIGIBLE</dt><dd>{{ view.eligibility.researchEligible ? 'Sí' : 'No' }}</dd></div><div><dt>ECONOMICALLY_VIABLE</dt><dd>{{ view.eligibility.economicallyViable }}</dd></div><div><dt>STATISTICALLY_VALIDATED</dt><dd>No</dd></div><div><dt>PAPER_EXECUTION_ELIGIBLE</dt><dd>No</dd></div></dl><p class="small muted">Shadow puede registrar expectativa negativa o desconocida. Las advertencias económicas siguen visibles.</p></section>

        <div class="r20-columns">
          <section class="card" aria-labelledby="r20-market-title"><h2 id="r20-market-title">Mercado y NO_TRADE</h2><p><b>{{ stale ? 'STALE' : view.market.status }}</b> · {{ view.market.source }}</p><p class="small muted">Observado {{ date(view.market.at) }} · XAU/USD: {{ view.xauStatus }}</p><div class="r20-rejection"><span class="eyebrow">ÚLTIMA OPORTUNIDAD RECHAZADA</span><p>{{ view.lastNoTrade?.reason ?? 'Sin rechazo registrado' }}</p><small>{{ date(view.lastNoTrade?.at) }}</small></div></section>
          <section class="card" aria-labelledby="r20-kronos-title"><h2 id="r20-kronos-title">Kronos · observador independiente</h2><p><b>{{ view.kronos.status }}</b> · {{ view.kronos.calibration }}</p><p>Probabilidad calibrada: No evaluable</p><p>Acuerdo registrado: {{ view.kronos.agreement ?? 'UNKNOWN' }} · {{ view.kronos.reason ?? 'Sin motivo registrado' }}</p><p class="small muted">{{ view.kronos.predictionId ?? 'Sin forecast vinculado' }} · {{ date(view.kronos.createdAt) }}. Las frecuencias brutas no autorizan entradas.</p></section>
        </div>

        <section class="card" data-testid="r20-paper" aria-labelledby="r20-paper-title"><div class="panel-heading"><div><span class="eyebrow">{{ view.paper.classification }}</span><h2 id="r20-paper-title">Preparación diagnóstica supervisada</h2></div><span class="pill">{{ view.paper.state }} · SIN AUTORIZACIÓN</span></div><p><b>{{ view.paperTrades }} operaciones</b> de esta cohorte. <span v-if="view.paperTrades === 0">Sin resultados realizados ni fills del bróker.</span></p><p>La primera ejecución futura requiere consentimiento específico de un solo uso y condiciones efectivas verificadas.</p><ul class="r20-blockers"><li v-for="reason in view.paper.blockers" :key="reason">{{ reason }}</li></ul><details><summary>Condiciones de ejecución y protección</summary><ul class="r20-blockers"><li v-for="condition in view.paper.conditions" :key="condition">{{ condition }}</li></ul></details></section>

        <section class="card" aria-labelledby="r20-baseline-title"><span class="eyebrow">COMPARACIÓN EXPLORATORIA · MISMAS OPORTUNIDADES</span><h2 id="r20-baseline-title">Baseline sin apalancamiento · 1:1</h2><dl class="r20-metrics"><div><dt>Equity baseline</dt><dd>{{ usd(view.baseline.equity) }}</dd></div><div><dt>P&L neto baseline</dt><dd>{{ usd(view.baseline.netPnl) }}</dd></div><div><dt>Operaciones cerradas baseline</dt><dd>{{ view.baseline.closedTrades }}</dd></div><div><dt>Apalancamiento máximo</dt><dd>{{ view.baseline.leverage }}×</dd></div></dl><p class="small muted">{{ view.baseline.description }}</p></section>

        <section class="card" aria-labelledby="r20-signals-title"><h2 id="r20-signals-title">Señales y oportunidades recientes</h2><p v-if="!recentSignals.length" class="muted">Todavía no hay señales ni evaluaciones registradas.</p><template v-else><p class="small muted">{{ recentSignals.length }} de {{ view.recentSignals.length }} filas del snapshot. Historial íntegro en el journal.</p><div class="table-scroll" tabindex="0" aria-label="Señales R20, desplazamiento horizontal"><table><thead><tr><th>Timestamp</th><th>Temporalidad</th><th>Lado</th><th>Estado</th><th>Motivo</th></tr></thead><tbody><tr v-for="signal in recentSignals" :key="signal.id"><td>{{ date(signal.at) }}</td><td>{{ signal.timeframe }} min</td><td>{{ signal.side ?? '—' }}</td><td>{{ signal.status }}</td><td>{{ signal.reason ?? 'Sin motivo registrado' }}</td></tr></tbody></table></div></template></section>

        <section class="card" aria-labelledby="r20-trades-title"><h2 id="r20-trades-title">Operaciones Shadow</h2><p class="small muted">Entradas y salidas virtuales; no son fills IBKR. {{ recentTrades.length }} de {{ view.trades.length }} operaciones del snapshot.</p><p v-if="!recentTrades.length" class="muted">Sin operaciones Shadow registradas. No se fabrican fills para completar una muestra.</p><details v-for="trade in recentTrades" :key="trade.id" class="r20-trade"><summary>{{ trade.classification }} · {{ trade.runKind }} · {{ trade.side }} · {{ trade.timeframe }} min · {{ date(trade.at) }} · {{ trade.closedAt ? 'CERRADA' : 'ABIERTA' }}</summary><dl class="r20-metrics"><div><dt>Entrada / salida</dt><dd>{{ trade.entry ?? 'No evaluable' }} / {{ trade.exit ?? 'No evaluable' }}</dd></div><div><dt>Cantidad EUR</dt><dd>{{ trade.quantity ?? 'No evaluable' }}</dd></div><div><dt>Exposición / leverage</dt><dd>{{ usd(trade.exposure) }} / {{ leverage(trade.leverage) }}</dd></div><div><dt>Stop / target</dt><dd>{{ trade.stop ?? 'No evaluable' }} / {{ trade.target ?? 'No evaluable' }}</dd></div><div><dt>Riesgo por precio</dt><dd>{{ usd(trade.priceRisk) }}</dd></div><div><dt>Comisiones</dt><dd>{{ usd(trade.commissions) }}</dd></div><div><dt>Pérdida total prevista</dt><dd>{{ usd(trade.totalExpectedLoss) }}</dd></div><div><dt>P&L bruto / neto</dt><dd>{{ usd(trade.grossPnl) }} / {{ usd(trade.netPnl) }}</dd></div></dl><p>{{ trade.reason ?? 'Sin motivo de salida registrado' }} · {{ date(trade.closedAt) }}</p><p class="small muted">{{ trade.id }}</p></details></section>

        <details class="card"><summary>Estrategia y procedencia de la cohorte</summary><p>{{ view.profile }} · {{ view.strategy }} · versión {{ view.version }}</p><p>EMA20 / EMA50 · ruptura de 20 velas cerradas · ATR14 × 1.5 · target 2R · LONG / SHORT.</p><p>{{ view.experiment }} · inicio {{ date(view.startedAt) }} · {{ view.runKind }} · {{ view.evidenceQuality }}</p><p>CAPITAL_PROTECTION_R3 archivado para esta cohorte. Las políticas y evidencias históricas permanecen independientes.</p><pre v-if="view.lastAssessment" class="r20-assessment">{{ JSON.stringify(view.lastAssessment, null, 2) }}</pre></details>
      </template>
    </div>
  </AdvancedPage>
</template>
<style scoped>
.r20-workspace{display:grid;gap:20px;overflow-wrap:anywhere}.r20-workspace .card{margin:0;min-width:0}.r20-workspace h2{font-size:19px;margin-block:8px 16px}.r20-workspace p{font-size:12px;line-height:1.7}.r20-workspace .panel-heading{flex-wrap:wrap;gap:12px}.r20-capital{border-inline-start:3px solid var(--cyan)}.r20-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:20px 16px;margin:20px 0}.r20-metrics dt{font-size:10px;color:var(--muted)}.r20-metrics dd{margin:6px 0 0;font-size:15px;font-weight:650;font-variant-numeric:tabular-nums}.r20-primary dd{font-size:27px}.r20-pairs{grid-template-columns:repeat(2,minmax(0,1fr))}.r20-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.r20-warning,.r20-rejection{border-inline-start:3px solid var(--warn);padding:10px 14px;background:var(--surface-raised)}.r20-rejection{margin-top:20px}.r20-rejection small{color:var(--muted)}.r20-blockers{font-size:12px;padding-left:20px;line-height:1.8}.r20-trade{padding-block:16px;border-top:1px solid var(--border)}.r20-workspace summary{cursor:pointer;font-size:12px;line-height:1.7}.r20-workspace th,.r20-workspace td{font-size:11px;max-width:360px;white-space:normal}.r20-assessment{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;max-height:300px;overflow:auto}.r20-workspace .pill{font-size:10px;white-space:normal}@media(max-width:1000px){.r20-columns{grid-template-columns:1fr}}@media(max-width:600px){.r20-metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:18px 12px}.r20-primary dd{font-size:24px}.r20-workspace h2{font-size:18px}}
</style>
