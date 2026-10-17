<script setup lang="ts">
import { computed } from 'vue'
import type { Trade } from '../types'
import TradesTable from './TradesTable.vue'
import StatusBadge from './StatusBadge.vue'
const props=defineProps<{ trades: Trade[]; open?: boolean }>();defineEmits<{ select: [trade: Trade] }>()
const paper=computed(()=>props.trades.filter(t=>t.classification==='BROKER_PAPER_EXECUTION'))
const shadow=computed(()=>props.trades.filter(t=>t.classification==='SIMULATED_SHADOW'))
const unknown=computed(()=>props.trades.filter(t=>!['BROKER_PAPER_EXECUTION','SIMULATED_SHADOW'].includes(t.classification)))
</script>
<template><section class="activity-panel" :aria-label="open ? 'Actividad de posiciones' : 'Historial de ejecución'"><div class="section-heading"><div><span class="eyebrow">LIVE EXPERIMENT ACTIVITY · ACTUALIZACIÓN SIGNALR</span><h2>{{ open ? 'Inventario bajo observación' : 'Resultados conciliados' }}</h2></div><StatusBadge value="LIVE TRADING BLOCKED" tone="danger" /></div><div class="activity-origin"><span>IBKR PAPER</span><b>{{ paper.length }} {{ open ? 'posiciones' : 'cierres' }}</b><small>Ejecución del broker · sin mezclar con simulación</small></div><TradesTable v-if="paper.length" :trades="paper" :open="open" @select="$emit('select',$event)" /><p v-else class="origin-empty">No hay {{ open ? 'posiciones' : 'cierres' }} Paper registrados en este experimento. Esto no sustituye una conciliación completa de cuenta.</p><div class="activity-origin shadow-origin"><span>SIMULATED SHADOW</span><b>{{ shadow.length }} {{ open ? 'posiciones' : 'cierres' }}</b><small>Fills internos · capital virtual por cartera</small></div><TradesTable :trades="shadow" :open="open" @select="$emit('select',$event)" /><div v-if="unknown.length" class="notice">{{ unknown.length }} registros con origen distinto/no confirmado. <TradesTable :trades="unknown" :open="open" @select="$emit('select',$event)" /></div></section></template>
