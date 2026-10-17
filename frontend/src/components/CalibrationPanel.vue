<script setup lang="ts">
import { computed } from 'vue'
import type { CalibrationBucket,ChartResponse } from '../types'
import { number,percent } from '../format'
import EquityChart from './EquityChart.vue'
import StatusBadge from './StatusBadge.vue'
const props=defineProps<{ buckets:CalibrationBucket[];status:string;source:string }>()
const chart=computed<ChartResponse>(()=>({title:'Predicted probability vs observed success rate',unit:'probabilidad',series:[{name:'Éxito observado',points:props.buckets.filter(b=>b.average_probability!=null&&b.observed_tp_rate!=null&&b.samples>0).map(b=>({at:String(b.average_probability),value:b.observed_tp_rate!}))}]}))
</script>
<template><section class="calibration-panel"><div class="panel-heading"><div><h3>Confidence calibration</h3><p>{{ source }} · tamaño de muestra visible por bucket</p></div><StatusBadge :value="status" /></div><EquityChart :chart="chart" probability-axis kind="scatter" :height="250" /><div class="table-scroll" tabindex="0" aria-label="Buckets de calibración"><table><caption class="sr-only">Predicción frente a éxito observado, frecuencia TP antes de SL</caption><thead><tr><th>Bucket</th><th>Predicted</th><th>Observed</th><th>Sample count</th><th>Error absoluto</th></tr></thead><tbody><tr v-for="b in buckets" :key="b.bucket"><td>{{ b.bucket }}</td><td>{{ percent(b.average_probability) }}</td><td>{{ percent(b.observed_tp_rate) }}</td><td>{{ number(b.samples,0) }}</td><td>{{ b.average_probability!=null&&b.observed_tp_rate!=null?percent(Math.abs(b.average_probability-b.observed_tp_rate)):'No evaluable' }}</td></tr><tr v-if="!buckets.length"><td colspan="5" class="empty-cell">INSUFFICIENT_EVIDENCE · sin resultados comparables</td></tr></tbody></table></div><p class="small muted">La diagonal es referencia ideal, no un resultado. RAW no equivale a confianza calibrada.</p></section></template>
