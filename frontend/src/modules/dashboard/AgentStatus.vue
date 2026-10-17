<script setup lang="ts">
import { computed } from 'vue'
import { useSystemStore, usePredictionStore, useInterfaceStore, useTradeStore } from '../../stores'
import { useInstrument } from '../../composables/useInstrument'
const system=useSystemStore();const prediction=usePredictionStore();const ui=useInterfaceStore();const trades=useTradeStore();const {symbol,timeframe}=useInstrument()
const observing=computed(()=>system.studyStatus==='SHADOW_RESEARCH_RUNNING'&&system.connection==='CONNECTED'&&!system.error)
const state=computed(()=>system.connection!=='CONNECTED'?'Conexión interrumpida':system.error?'Evidencia no disponible':trades.open.length?'Inventario bajo observación':observing.value?`Observando ${symbol.value}`:'Investigación sin actividad confirmada')
const reason=computed(()=>{if(system.error||system.connection!=='CONNECTED')return 'Evidencia conservada STALE; esperando conciliación del feed';const d=prediction.current?.decisions[ui.profile];return d&&typeof d==='object'&&!Array.isArray(d)?String(d.reason ?? 'DATA_UNAVAILABLE'):prediction.current?.status ?? 'DATA_UNAVAILABLE'})
</script>
<template><section class="agent-status" data-testid="agent-status" aria-label="Estado del agente"><span class="agent-status-icon" :class="{observing}" aria-hidden="true">◎</span><div><span class="eyebrow">AGENT STATUS · SHADOW</span><h2>{{ state }}</h2><p>{{ reason==='NO_VALID_STRATEGY_SIGNAL'?'Esperando una señal válida; sin entrada Shadow.':reason }} · {{ timeframe }} cerrado</p></div><RouterLink to="/trading" class="text-button">Ver actividad ↗</RouterLink></section></template>
