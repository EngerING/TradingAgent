<script setup lang="ts">
defineProps<{ title:string; description:string }>()
</script>
<template><div class="empty-state"><span class="empty-state-symbol" aria-hidden="true">—</span><div><h3>{{ title }}</h3><p>{{ description }}</p><slot /></div></div></template>
