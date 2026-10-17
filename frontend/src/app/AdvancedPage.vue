<script setup lang="ts">
import { useSystemStore } from '../stores'
import StatusBadge from '../components/StatusBadge.vue'
defineProps<{title:string;description:string}>();const system=useSystemStore()
</script>
<template><div class="page-intro"><div><span class="eyebrow">PAPER RESEARCH · EVIDENCIA</span><h1>{{ title }}</h1><p>{{ description }}</p></div><slot name="action" /></div><div v-if="system.error" class="error-banner" role="alert">{{ system.error }}</div><div class="safety-banner"><span class="safety-symbol">!</span><p><b>Experimento, sin promoción.</b> {{ system.studyStatus }} · EmergencyStop: {{ system.status?.emergency ?? 'UNKNOWN' }} · el frontend no puede enviar órdenes.</p><StatusBadge value="SOLO LECTURA" tone="neutral" /></div><slot /></template>
