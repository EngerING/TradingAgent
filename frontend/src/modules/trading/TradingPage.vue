<script setup lang="ts">
import OpenInventory from './OpenInventory.vue'
import TradeFeed from './TradeFeed.vue'
import ActivityPanel from '../../components/ActivityPanel.vue'
import { useTradeStore } from '../../stores'
const trades=useTradeStore()
</script>
<template><div class="page-intro"><div><span class="eyebrow">TRADING · PAPER / SHADOW</span><h1>Inventario & ejecución</h1><p>Órdenes y resultados observados; ninguna capacidad de enviar órdenes desde Vue.</p></div></div><OpenInventory /><TradeFeed /><ActivityPanel :trades="trades.closed" @select="trades.selected=$event" /></template>
