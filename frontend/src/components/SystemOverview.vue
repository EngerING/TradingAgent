<script setup lang="ts">
import { computed } from 'vue'
import { useSystemStore, useKronosStore } from '../stores'
import StatusBadge from './StatusBadge.vue'
const system = useSystemStore(); const kronos = useKronosStore()
const states = computed(() => [
  { label: 'Entorno', value: 'PAPER · SHADOW', tone: 'neutral' as const, note: 'Investigación sin órdenes' },
  { label: 'Live', value: 'BLOCKED', tone: 'danger' as const, note: 'Bloqueado por backend' },
  { label: 'EmergencyStop', value: system.status?.emergency ?? 'UNKNOWN', tone: 'warn' as const, note: 'Control protegido' },
  { label: 'IBKR', value: system.status?.ibkr ?? 'UNKNOWN', note: 'Datos Paper · no acredita permisos' },
  { label: 'Kronos', value: kronos.view?.status.replace('KRONOS_', '') ?? 'UNAVAILABLE', note: kronos.view?.stale ? 'Forecast STALE' : kronos.view?.calibrationState ?? 'Sin calibración' },
  { label: 'Sol', value: system.status?.sol === 'BUDGET_DISABLED' ? 'LOCAL' : system.status?.sol ?? 'UNKNOWN', note: `Presupuesto API US$${system.status?.solBudget ?? 'UNKNOWN'}` },
  { label: 'PostgreSQL', value: system.status?.postgres ?? 'UNKNOWN', note: 'Journal persistente' },
  { label: 'Realtime', value: system.connection, note: system.connection === 'CONNECTED' ? 'SignalR · deltas' : 'Valores conservados: STALE' },
])
</script>
<template><section class="system-overview" aria-label="Estado del sistema" data-testid="system-overview"><div class="section-caption"><span class="eyebrow">SYSTEM STATUS</span><span class="small muted">Datos y ejecución son capacidades distintas</span></div><dl class="system-grid"><div v-for="s in states" :key="s.label" class="system-item"><dt>{{ s.label }}</dt><dd><StatusBadge :value="s.value" :tone="s.tone" /><small>{{ s.note }}</small></dd></div></dl></section></template>
