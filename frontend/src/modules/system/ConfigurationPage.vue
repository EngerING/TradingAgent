<script setup lang="ts">
import AdvancedPage from '../../app/AdvancedPage.vue'
import { useSystemStore } from '../../stores'
const system=useSystemStore()
</script>
<template><AdvancedPage title="Configuración protegida" description="Controles de sólo lectura, reflejados desde el backend."><section class="card"><h3>Controles reflejados desde backend</h3><dl class="detail-list"><template v-for="(v, key) in system.status ?? {}" :key="key"><dt>{{ key }}</dt><dd>{{ v ?? 'UNKNOWN' }}</dd></template></dl></section><section class="card"><h3>Política del laboratorio</h3><p>WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY · una posición por cartera · sin apalancamiento. US$100 por perfil, límite acumulado US$20 que las ganancias no restauran.</p><p class="notice">No hay controles para Live, EmergencyStop, AccountBinding, RiskEngine, ExecutionGuard, permisos Paper ni tamaño de posiciones.</p><p>Estudio: {{ system.studyId ?? 'DATA_UNAVAILABLE' }}</p></section></AdvancedPage></template>
