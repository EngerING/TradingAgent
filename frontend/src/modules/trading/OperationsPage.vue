<script setup lang="ts">
import AdvancedPage from '../../app/AdvancedPage.vue'
import ActivityPanel from '../../components/ActivityPanel.vue'
import { useTradeStore } from '../../stores'
const trades=useTradeStore()
</script>
<template><AdvancedPage title="Operaciones" description="Fills simulados identificados; pendientes no cuentan como ganancias."><ActivityPanel :trades="trades.open" open @select="trades.selected = $event" /><ActivityPanel :trades="trades.closed" @select="trades.selected = $event" /></AdvancedPage></template>
