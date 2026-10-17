<script setup lang="ts">
defineProps<{ value: string; tone?: 'good' | 'warn' | 'danger' | 'neutral' }>()
</script>
<template><span class="badge" :class="tone ?? (/BLOCK|UNPROTECTED|ERROR/.test(value) ? 'danger' : /UNKNOWN|INSUFFICIENT|STALE|DELAYED|NO_TRADE|DEGRADED|UNAVAILABLE|EMERGENCY|NOT_AUTHORIZED/.test(value) ? 'warn' : /ACTIVE|LIVE|CONNECTED|VERIFIED|READY/.test(value) && !/DISCONNECTED|INACTIVE/.test(value) ? 'good' : 'neutral')"><span class="badge-dot" aria-hidden="true"></span>{{ value.replaceAll('_', ' ') }}</span></template>
