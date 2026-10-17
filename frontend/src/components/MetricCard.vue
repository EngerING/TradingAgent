<script setup lang="ts">defineProps<{ label: string; value: string; note?: string; negative?: boolean }>()</script>
<template><div class="metric"><span>{{ label }}</span><strong :class="{ negative }">{{ value }}</strong><small v-if="note">{{ note }}</small></div></template>
