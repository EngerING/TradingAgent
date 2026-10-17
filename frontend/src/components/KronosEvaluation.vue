<script setup lang="ts">
import { computed } from 'vue'
import { useKronosStore } from '../stores'
import { number,percent,money } from '../format'
import type { Json } from '../types'
import MetricCard from './MetricCard.vue'
import CalibrationPanel from './CalibrationPanel.vue'
import StatusBadge from './StatusBadge.vue'
import KronosDiagnostics from './KronosDiagnostics.vue'
const store=useKronosStore()
function object(v:Json|undefined){return v&&typeof v==='object'&&!Array.isArray(v)?v:{}}
function numeric(v:Json|undefined){return typeof v==='number'&&Number.isFinite(v)?v:null}
const rows=computed(()=>Object.entries(object(object(object(store.view?.evaluation).benchmark).profiles)).map(([name,data])=>{const r=object(data);return {name,baseline:object(r.BASELINE_ACTUAL),kronos:object(r.BASELINE_PLUS_KRONOS),delta:numeric(r.delta_expectancy)}}))
</script>
<template><section class="card evaluation-card" data-testid="kronos-evaluation"><div class="panel-heading"><div><span class="eyebrow">BASELINE vs BASELINE + KRONOS</span><h3>Kronos Evaluation</h3><p>Comparación fuera de muestra después de costos. Prueba final sellada.</p></div><StatusBadge :value="store.view?.calibrationState ?? 'CALIBRATION_INSUFFICIENT'" /></div>
 <KronosDiagnostics :view="store.view" />
 <div class="evaluation-metrics"><MetricCard label="Forecasts" :value="number(store.view?.calibration.predictions,0)" /><MetricCard label="Evaluados" :value="number(store.view?.calibration.evaluated,0)" /><MetricCard label="Brier score" :value="number(store.view?.calibration.brier_score,4)" /><MetricCard label="Calibration error" :value="percent(store.view?.calibration.calibration_error)" /><MetricCard label="TP-first accuracy" :value="percent(store.view?.calibration.tp_first_accuracy)" /><MetricCard label="Directional accuracy" :value="percent(store.view?.calibration.directional_accuracy)" /></div>
 <div class="comparison-heading"><span>BASELINE</span><span>vs</span><span>BASELINE + KRONOS</span></div>
 <div class="table-scroll" tabindex="0" aria-label="Comparación económica Kronos"><table><thead><tr><th>Perfil</th><th>Trades base / Kronos</th><th>Expectancy base / Kronos</th><th>Drawdown base / Kronos</th><th>Δ expectancy</th></tr></thead><tbody><tr v-for="r in rows" :key="r.name"><td>{{ r.name }}</td><td>{{ number(numeric(r.baseline.trades),0) }} / {{ number(numeric(r.kronos.trades),0) }}</td><td>{{ money(numeric(r.baseline.expectancy)) }} / {{ money(numeric(r.kronos.expectancy)) }}</td><td>{{ money(numeric(r.baseline.maximum_drawdown)) }} / {{ money(numeric(r.kronos.maximum_drawdown)) }}</td><td>{{ money(r.delta) }}</td></tr><tr v-if="!rows.length"><td colspan="5" class="empty-cell">INSUFFICIENT_EVIDENCE · benchmark no disponible</td></tr></tbody></table></div>
 <CalibrationPanel :buckets="store.view?.calibration.buckets ?? []" :status="store.view?.calibrationState ?? 'CALIBRATION_INSUFFICIENT'" source="KRONOS RAW TP FREQUENCY" />
 <div class="regime-list"><div v-for="r in store.view?.byRegime ?? []" :key="r.regime"><b>{{ r.regime }}</b><span>n={{ r.sample_size }}</span><span>Brier {{ number(r.brier_score,4) }}</span></div></div>
 <details v-if="store.view?.evaluation"><summary>Informe reproducible · parámetros congelados</summary><pre>{{ JSON.stringify(store.view.evaluation,null,2) }}</pre></details>
 <p class="notice">INSUFFICIENT_EVIDENCE cuando faltan muestras. Una mejor predicción de precio no implica rentabilidad; expectancy y EV no se inventan.</p></section></template>
