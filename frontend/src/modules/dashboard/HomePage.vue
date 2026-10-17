<script setup lang="ts">
import { useSystemStore, useMarketStore } from '../../stores'
import AccountCard from './AccountCard.vue'
import AgentCard from './AgentCard.vue'
import AgentStatus from './AgentStatus.vue'
import ProfileQuickCards from '../experiments/ProfileQuickCards.vue'
import KronosHomeCard from '../kronos/KronosHomeCard.vue'
import OpenInventory from '../trading/OpenInventory.vue'
import TradeFeed from '../trading/TradeFeed.vue'
import SystemOverview from '../../components/SystemOverview.vue'
import PriceRiskExperiment from '../../components/PriceRiskExperiment.vue'
import PaperReadiness from '../../components/PaperReadiness.vue'
import MarketQuoteCard from '../../components/MarketQuoteCard.vue'
import AggressiveGrowthSummary from '../aggressive-growth/AggressiveGrowthSummary.vue'
import { computed } from 'vue'
const system=useSystemStore();const market=useMarketStore()
const researchLabel=computed(()=>system.studyStatus==='SHADOW_RESEARCH_RUNNING'?'Shadow activo':system.studyStatus.startsWith('SUSPENDED')?'Shadow suspendido':'Shadow · '+system.studyStatus)
</script>
<template><div class="home-intro"><div><span class="eyebrow">TRADING WORKSPACE · PAPER / SHADOW</span><h1>Tu agente, en tiempo real.</h1><p>Capital virtual, decisiones y evidencia de ejecución.</p></div><span class="pill" :title="system.studyStatus">{{ researchLabel }}</span></div><div class="protected-strip"><span>EmergencyStop <b>{{ system.status?.emergency ?? 'UNKNOWN' }}</b></span><span>PaperAuto <b>{{ system.status?.paperAuto ?? 'UNKNOWN' }}</b></span><span>LIVE BLOCKED · SOLO LECTURA</span></div><div class="home-top"><AccountCard /><div class="home-agent"><AgentStatus /><p v-if="system.error" class="error-banner" role="alert">{{ system.error }}</p><AgentCard /></div></div><AggressiveGrowthSummary /><OpenInventory /><ProfileQuickCards /><div class="home-research"><div><KronosHomeCard /><details class="card market-disclosure"><summary>Cotización y procedencia del feed Paper</summary><MarketQuoteCard :quote="market.quote" /></details></div><TradeFeed /></div><PaperReadiness /><PriceRiskExperiment /><details class="card advanced-status"><summary>Estado avanzado del sistema y conexiones</summary><SystemOverview /></details></template>
