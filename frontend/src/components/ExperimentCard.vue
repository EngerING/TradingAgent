<script setup lang="ts">
import { computed } from 'vue'
import type { Experiment } from '../types'
import { money, number, percent } from '../format'
import StatusBadge from './StatusBadge.vue'
import EquityChart from './EquityChart.vue'
const props = defineProps<{ experiment: Experiment }>()
const chart = computed(() => ({ title: `Equity ${props.experiment.id}`, unit: 'USD', series: [{ name: props.experiment.id, points: props.experiment.equityCurve.map(p => ({ at: p.at, value: p.equity })) }] }))
</script>
<template><article class="card experiment-card" :class="experiment.id.toLowerCase()">
  <div class="flex items-center justify-between gap-2"><div class="flex items-center gap-3"><span class="profile-icon">{{ experiment.id.slice(7) }}</span><div><h3>{{ experiment.id }}</h3><small>{{ experiment.executionRole ?? 'SIMULATED SHADOW' }} · capital aislado</small></div></div><StatusBadge :value="experiment.executionRole ?? experiment.status" /></div>
  <div class="equity-head"><div><span class="eyebrow">EQUITY CONTABLE</span><strong>{{ money(experiment.metrics?.equity) }}</strong></div><span class="risk-label">{{ percent(experiment.risk?.fraction) }} riesgo</span></div>
  <div class="profile-next"><span>Presupuesto próximo</span><b>{{ money(experiment.risk?.nextBudget) }}</b></div>
  <EquityChart :chart="chart" :height="66" compact />
  <div class="stats-grid"><div><span>P&L neto</span><b :class="{ negative: (experiment.metrics?.netPnl ?? 0) < 0 }">{{ money(experiment.metrics?.netPnl) }}</b></div><div><span>Acierto neto</span><b>{{ percent(experiment.metrics?.winRate) }}</b></div><div><span>Operaciones</span><b>{{ number(experiment.metrics?.trades, 0) }}</b></div><div><span>Drawdown actual</span><b>{{ money(experiment.metrics?.currentDrawdown) }}</b></div><div><span>Profit factor</span><b>{{ number(experiment.metrics?.profitFactor) }}</b></div><div><span>Expectativa</span><b>{{ money(experiment.metrics?.expectancy) }}</b></div></div>
  <div class="profile-policy"><span>SIMULATED SHADOW</span><StatusBadge :value="experiment.status" /></div><dl class="profile-foot"><dt>Stop del día</dt><dd>{{ experiment.stoppedForDay == null ? 'UNKNOWN' : experiment.stoppedForDay ? 'DETENIDO' : 'Sin stop registrado' }}</dd><dt>Probabilidad media calibrada</dt><dd>{{ percent(experiment.metrics?.confidence) }}</dd></dl>
  <details v-if="experiment.brokerMetrics" class="broker-summary"><summary>IBKR PAPER: {{ number(experiment.brokerMetrics.trades, 0) }} cierres</summary><p>Equity lógico: {{ money(experiment.paperEquity) }} · reserva: {{ money(experiment.paperReserved) }}</p><p>P&amp;L broker: {{ money(experiment.brokerMetrics.netPnl) }} · comisiones: {{ money(experiment.brokerMetrics.fees) }}</p><p>{{ experiment.paperBlockers?.join(', ') }}</p><small>EXPLORATORY_NOT_VALIDATED · independiente de las métricas Shadow.</small></details>
  <details><summary>Riesgo y evidencia</summary><dl class="detail-list"><dt>Capital inicial</dt><dd>{{ money(experiment.metrics?.initialCapital) }}</dd><dt>Presupuesto próxima operación</dt><dd>{{ money(experiment.risk?.nextBudget) }}</dd><dt>P&L bruto</dt><dd>{{ money(experiment.metrics?.grossPnl) }}</dd><dt>Probabilidad media calibrada</dt><dd>{{ percent(experiment.metrics?.confidence) }}</dd><dt>Costo / beneficio bruto</dt><dd>{{ percent(experiment.metrics?.costRatio) }}</dd><dt>Pérdidas restantes</dt><dd>{{ money(experiment.risk?.remainingLossBudget) }}</dd></dl><p class="muted">{{ experiment.reason }}</p></details>
</article></template>
