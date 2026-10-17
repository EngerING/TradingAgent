<script setup lang="ts">
import { computed,defineAsyncComponent } from 'vue'
import { useKronosStore, useSystemStore } from '../stores'
import { percent,number,date } from '../format'
import { useInstrument } from '../composables/useInstrument'
const {symbol}=useInstrument()
import StatusBadge from './StatusBadge.vue'
import KronosDiagnostics from './KronosDiagnostics.vue'
const KronosForecastChart=defineAsyncComponent(()=>import('./KronosForecastChart.vue'))
const system=useSystemStore();const store=useKronosStore();const latest=computed(()=>store.view?.latest)
</script>
<template><section class="card kronos-card" data-testid="kronos-card">
 <div class="panel-heading"><div class="kronos-title"><span class="kronos-mark">K</span><div><span class="eyebrow">LOCAL ZERO-SHOT · OBSERVATION</span><h3>Current Kronos view <span class="muted">/ {{ symbol }}</span></h3></div></div><StatusBadge :value="store.view?.status ?? 'KRONOS_UNAVAILABLE'" /></div>
 <KronosDiagnostics :view="store.view" />
 <p v-if="store.view?.stale || system.connection!=='CONNECTED'||Boolean(system.error)" class="notice">STALE · forecast conservado para inspección. No utilizable para admisión.</p>
 <p v-if="store.view?.diagnostics?.calibration_reason==='NO_ELIGIBLE_TECHNICAL_SIGNAL'" class="probability-unavailable">TP/SL probability: NOT_AVAILABLE — NO_ELIGIBLE_SIGNAL</p>
 <div v-if="latest" class="kronos-summary"><div class="forecast-direction"><span class="eyebrow">DIRECCIÓN MEDIANA DEL MODELO</span><strong>{{ latest.consensus.kronos_direction }}</strong><span>{{ percent(latest.predicted_return_median) }} retorno · {{ percent(latest.predicted_volatility) }} dispersión</span></div><dl class="barrier-metrics"><div><dt>Raw TP frequency</dt><dd>{{ percent(latest.raw_tp_frequency) }}</dd></div><div><dt>SL frequency</dt><dd>{{ percent(latest.raw_sl_frequency) }}</dd></div><div><dt>Neither</dt><dd>{{ percent(latest.neither_frequency) }}</dd></div></dl><div class="calibration-summary"><span class="eyebrow">CALIBRACIÓN</span><StatusBadge :value="store.view?.calibrationState ?? 'CALIBRATION_INSUFFICIENT'" /><strong>{{ store.view?.stale || system.connection!=='CONNECTED'||Boolean(system.error)?'STALE':percent(latest.calibrated_probability) }}</strong><small>Probabilidad calibrada · no subjetiva</small></div></div>
 <div v-if="latest" class="forecast-meta"><span><b>{{ latest.timeframe }}</b> timeframe</span><span><b>{{ latest.lookback }}</b> velas</span><span><b>{{ latest.pred_len }}</b> pasos de horizonte</span><span><b>{{ latest.sample_count }}</b> samples</span><span><b>{{ latest.telemetry.device ?? 'UNKNOWN' }}</b> · {{ number(latest.telemetry.inference_seconds) }} s{{ latest.telemetry.forecast_reused_from_verified_artifact?' · CACHE VERIFICADA':'' }}</span><span>{{ date(latest.created_at) }}</span></div>
 <div class="forecast-workspace"><div class="chart-legend"><span><i class="legend-candle"></i>REAL MARKET · velas IBKR</span><span><i class="legend-forecast"></i>KRONOS FORECAST · mediana</span><span><i class="legend-band"></i>Banda 5–95% · dispersión no calibrada</span></div><KronosForecastChart v-if="latest?.historical.length && latest?.quantiles.length" :prediction="latest" /><div v-else class="forecast-empty"><b>Forecast no disponible</b><p>Esperando una ventana auténtica y un modelo disponible. No se inventan precios.</p></div></div>
 <div v-if="latest" class="consensus-strip"><span>Technical <b>{{ latest.consensus.technical_signal ?? 'NO_SIGNAL' }}</b></span><span>Kronos <b>{{ latest.consensus.kronos_direction }}</b></span><StatusBadge :value="latest.consensus.consensus" /><span class="small">{{ latest.consensus.disagreements.join(' · ') || 'Sin contradicción registrada' }}</span></div>
 <div v-if="latest" class="forecast-foot"><span>Trayectorias inválidas: <b>{{ percent(latest.invalid_frequency) }}</b> · no reparadas, conservadas en denominador bruto</span><details><summary>Modelo y procedencia</summary><dl class="detail-list"><dt>Modelo</dt><dd>{{ latest.model }}</dd><dt>Revisión</dt><dd>{{ latest.model_version ?? 'UNKNOWN' }}</dd><dt>Volumen</dt><dd>{{ latest.volume_mode ?? 'UNKNOWN' }}</dd><dt>última vela UTC</dt><dd>{{ latest.candle_timestamp ?? 'UNKNOWN' }}</dd><dt>Ventana futura UTC</dt><dd>{{ latest.prediction_start ?? 'UNKNOWN' }} · {{ latest.prediction_end ?? 'UNKNOWN' }}</dd></dl></details></div>
 <p class="small muted">RAW es frecuencia de trayectorias, no probabilidad real. Una predicción no concede autorización ni demuestra rentabilidad.</p>
</section></template>
