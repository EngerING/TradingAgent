<script setup lang="ts">
import { House, ArrowLeftRight, FlaskConical, Sparkles, Ellipsis } from '@lucide/vue'
import { useInterfaceStore } from '../stores/interface'
const ui=useInterfaceStore();defineEmits<{more:[]}>()
</script>
<template><nav class="bottom-navigation" aria-label="Navegación móvil"><RouterLink to="/" aria-label="Inicio"><House :size="20"/><span>Inicio</span></RouterLink><RouterLink to="/trading" aria-label="Trading"><ArrowLeftRight :size="20"/><span>Trading</span></RouterLink><RouterLink to="/research" aria-label="Research"><FlaskConical :size="20"/><span>Research</span></RouterLink><button aria-label="Sol móvil" @click="ui.openSol"><Sparkles :size="20"/><span>Sol</span></button><button aria-label="Más páginas" @click="$emit('more')"><Ellipsis :size="20"/><span>Más</span></button></nav></template>
