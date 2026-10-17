<script setup lang="ts">
defineProps<{ title:string; eyebrow?:string }>()
</script>
<template><div class="panel-heading section-header"><div><span v-if="eyebrow" class="eyebrow">{{ eyebrow }}</span><h2>{{ title }}</h2></div><slot /></div></template>
