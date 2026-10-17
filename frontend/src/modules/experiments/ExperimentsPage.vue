<script setup lang="ts">
import AdvancedPage from '../../app/AdvancedPage.vue'
import { money, number, percent } from '../../format'
import { useExperimentStore, useTradeStore } from '../../stores'
import ExperimentCard from '../../components/ExperimentCard.vue'
import ExperimentComparisonChart from '../../components/ExperimentComparisonChart.vue'
import PriceRiskExperiment from '../../components/PriceRiskExperiment.vue'
import PaperReadiness from '../../components/PaperReadiness.vue'
import ActivityPanel from '../../components/ActivityPanel.vue'
const experiments=useExperimentStore();const trades=useTradeStore()
</script>
<template><AdvancedPage title="Experimentos" description="Capital aislado, resultados comparables y límites explícitos.">
    <PaperReadiness /><PriceRiskExperiment />
    <div class="section-heading"><div><span class="eyebrow">R1 / R5 / R10</span><h2>Misma oportunidad. Riesgo independiente.</h2></div><span class="pill">US$100 POR CARTERA · SHADOW</span></div>
    <div class="experiment-grid"><ExperimentCard v-for="e in experiments.experiments" :key="e.id" :experiment="e" /></div>
    <ExperimentComparisonChart :experiments="experiments.experiments" />
    <ActivityPanel :trades="trades.open" open @select="trades.selected = $event" />
    <section class="card"><div class="panel-heading"><h3>Evidencia ampliada por perfil</h3></div><div class="table-scroll"><table><thead><tr><th>Perfil</th><th>Wins / losses</th><th>Comisiones</th><th>Win / loss promedio</th><th>Sharpe / Sortino</th><th>Riesgo de ruina</th><th>Recovery factor</th><th>Racha perdedora</th></tr></thead><tbody><tr v-for="e in experiments.experiments" :key="e.id"><td>{{ e.id }}</td><td>{{ number(e.metrics?.wins, 0) }} / {{ number(e.metrics?.losses, 0) }}</td><td>{{ money(e.metrics?.fees) }}</td><td>{{ money(e.metrics?.averageWin) }} / {{ money(e.metrics?.averageLoss) }}</td><td>{{ number(e.metrics?.sharpe) }} / {{ number(e.metrics?.sortino) }}</td><td>{{ percent(e.metrics?.riskOfRuin) }}</td><td>{{ number(e.metrics?.recoveryFactor) }}</td><td>{{ number(e.metrics?.losingStreak, 0) }}</td></tr></tbody></table></div><p class="small muted">No se infieren ratios estadísticos ni riesgo de ruina con evidencia insuficiente.</p></section>
</AdvancedPage></template>
