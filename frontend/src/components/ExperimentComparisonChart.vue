<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Experiment, ChartResponse } from '../types'
import EquityChart from './EquityChart.vue'
const props = defineProps<{ experiments: Experiment[] }>()
const period = ref('Todo'); const enabled = ref(['EURUSD_R1', 'EURUSD_R5', 'EURUSD_R10']); const selectedMetric = ref('equity')
const metrics = [{ key: 'equity', label: 'Equity' }, { key: 'netPnl', label: 'P&L neto' }, { key: 'drawdown', label: 'Drawdown' }]
const chart = computed<ChartResponse>(() => {
  const last = Math.max(0, ...props.experiments.flatMap(e => e.equityCurve.map(p => new Date(p.at).getTime())))
  const days: Record<string, number> = { '1D': 1, '7D': 7, '30D': 30 }; const cutoff = period.value === 'Sesión' ? last - 86400000 : days[period.value] ? last - days[period.value]! * 86400000 : 0
  return { title: `Comparación · ${selectedMetric.value}`, unit: 'USD', series: props.experiments.filter(e => enabled.value.includes(e.id)).map(e => ({ name: e.id, points: e.equityCurve.filter(p => new Date(p.at).getTime() >= cutoff).map(p => ({ at: p.at, value: selectedMetric.value === 'equity' ? p.equity : selectedMetric.value === 'drawdown' ? p.drawdown : p.netPnl, netPnl: p.netPnl, drawdown: p.drawdown, tradeNumber: p.tradeNumber })) })) }
})
</script>
<template><section class="card"><div class="panel-heading"><div><h3>Comparador de experimentos</h3><p>Curvas registradas · sin mezclar las tres asignaciones de capital</p></div><div class="segmented"><button v-for="p in ['Sesión', '1D', '7D', '30D', 'Todo']" :key="p" :class="{ selected: period === p }" @click="period = p">{{ p }}</button></div></div><div class="chart-controls"><div class="tab-bar"><button v-for="m in metrics" :key="m.key" :class="{ active: selectedMetric === m.key }" @click="selectedMetric = m.key">{{ m.label }}</button></div><div class="flex gap-3"><label v-for="e in experiments" :key="e.id" class="line-toggle"><input v-model="enabled" type="checkbox" :value="e.id">{{ e.id.slice(7) }}</label></div></div><EquityChart :chart="chart" /><p class="small muted">El punto inicial representa capital preregistrado. Las curvas avanzan únicamente con resultados conciliados.</p></section></template>
