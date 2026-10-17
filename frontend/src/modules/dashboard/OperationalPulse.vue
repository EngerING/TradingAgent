<script setup lang="ts">
import { computed } from 'vue'
import { useSystemStore, useTradeStore, usePredictionStore, useKronosStore, useInterfaceStore } from '../../stores'
const system=useSystemStore();const trades=useTradeStore();const prediction=usePredictionStore();const kronos=useKronosStore();const ui=useInterfaceStore()
const reason=computed(()=>{const v=prediction.current?.decisions[ui.profile];return v&&typeof v==='object'&&!Array.isArray(v)?String(v.reason ?? v.decision ?? 'UNKNOWN'):prediction.current?.status ?? 'DATA_UNAVAILABLE'})
</script>
<template><section class="operational-pulse" aria-label="Resumen operativo inmediato"><RouterLink to="/trading"><span>Inventario del experimento</span><b>{{ trades.open.length }} registros abiertos</b></RouterLink><RouterLink to="/mercado"><span>Kronos · {{ kronos.view?.stale||system.connection!=='CONNECTED'?'STALE':kronos.view?.calibrationState ?? 'UNKNOWN' }}</span><b>{{ kronos.view?.latest?.consensus.kronos_direction ?? 'DATA_UNAVAILABLE' }}</b></RouterLink><RouterLink to="/mercado"><span>{{ prediction.current?.decision ?? 'INSUFFICIENT_EVIDENCE' }}</span><b>{{ reason }}</b></RouterLink><button @click="ui.openSol"><span>Sol · US${{ system.status?.solBudget ?? 'UNKNOWN' }}</span><b>{{ system.status?.solBudget===0?'Evidencia local; GPT inactivo':system.status?.sol ?? 'UNKNOWN' }}</b></button></section></template>
