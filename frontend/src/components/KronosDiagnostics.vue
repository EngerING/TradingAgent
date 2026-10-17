<script setup lang="ts">
import type { KronosView } from '../types'
defineProps<{ view: KronosView | null | undefined }>()
const descriptions: Record<string,string>={
 INVALID_MODEL_OHLC_TRAJECTORIES:'El modelo produjo trayectorias OHLC inválidas. No se reparan; las bandas usan sólo las válidas y no son confianza calibrada.',
 OBSERVER_HEARTBEAT_MISSING_OR_STALE:'El observador no ha confirmado actividad reciente. El forecast conservado no demuestra disponibilidad.',
 PREDICTION_MISSING_OR_STALE:'No hay una predicción reciente utilizable.',
 STALE_INPUT:'Las velas cerradas exceden la antigüedad permitida. Es un bloqueo de datos; no acredita un fallo del modelo.',
 STALE_SHADOW_SOURCE:'El recolector no ha aportado evidencia reciente. No se infiere con datos antiguos.',
 BAR_ALIGNMENT_REQUIRED:'Las velas no coinciden con la cuadrícula UTC requerida; las velas parciales de sesión no son una ventana horaria completa.',
 KRONOS_POSTGRES_UNAVAILABLE:'El journal no está disponible. El observador intenta recuperarlo en consultas posteriores.',
 PROVIDER_CPU_OOM_FALLBACK:'La inferencia pasó a CPU por falta de memoria GPU.',
 NO_ELIGIBLE_TECHNICAL_SIGNAL:'Sin señal técnica elegible no se calcula P(TP antes de SL). RAW_ONLY no significa que el proveedor esté desconectado.',
 CALIBRATION_INSUFFICIENT:'Faltan observaciones históricas comparables e independientes para calibrar.',
 CALIBRATION_DEGRADED:'La calidad del modelo o el error de calibración impiden una probabilidad calibrada.',
 RAW_ONLY:'Frecuencias del modelo sin aprobación de calibración.'
}
</script>
<template><div v-if="view?.diagnostics" class="notice" data-testid="kronos-diagnostics" role="status">
 <strong>Pipeline: {{ view.diagnostics.operational_health }} · calibración: {{ view.calibrationState }}</strong>
 <p v-if="view.diagnostics.total_paths!==undefined">Trayectorias válidas {{ view.diagnostics.valid_paths }} / {{ view.diagnostics.total_paths }}; inválidas {{ view.diagnostics.invalid_paths }}.</p>
 <details><summary>Calidad del modelo y evidencia de calibración</summary>
 <p v-for="reason in view.diagnostics.reasons" :key="reason">{{ descriptions[reason] ?? reason }}</p>
 <p v-if="view.diagnostics.calibration_reason">{{ descriptions[view.diagnostics.calibration_reason] ?? view.diagnostics.calibration_reason }}</p>
 <small>Observaciones de precio: {{ view.diagnostics.observed_price_samples }}; barreras: {{ view.diagnostics.observed_barrier_samples }}. Calibración exige ≥{{ view.diagnostics.minimum_calibration_samples }} comparables y ≥{{ view.diagnostics.minimum_bucket_samples }} por bucket, con calidad suficiente. Métricas descriptivas; no autorización.</small>
 <p v-if="view.diagnostics.evaluation?.pending_count">{{ view.diagnostics.evaluation.pending_count }} forecast(s) maduros pendientes de observaciones completas; no cuentan como resultados.</p>
</details></div><p v-else-if="view?.reason" class="notice">{{ view.reason }}</p></template>
