<script setup lang="ts">
import { computed } from 'vue'
import { useExperimentStore } from '../stores'
const experiments=useExperimentStore()
const stages=[{label:'PROPOSED',states:['REGISTERED','PROPOSED']},{label:'BACKTEST',states:['BACKTESTING']},{label:'WALK-FORWARD',states:['WALK_FORWARD']},{label:'SHADOW',states:['SHADOW']},{label:'PAPER',states:['PAPER_EXPERIMENTAL']},{label:'REJECTED',states:['REJECTED','REJECTED_INSUFFICIENT_EVIDENCE','NO_VIABLE_STRATEGY_FOUND']}]
const counted=computed(()=>stages.map(s=>({...s,count:(experiments.research?.candidates ?? []).filter(c=>s.states.includes(c.state)).length})))
const uncategorized=computed(()=>Math.max(0,(experiments.research?.candidates.length ?? 0)-counted.value.reduce((n,s)=>n+s.count,0)))
</script>
<template><section class="card pipeline-card"><div class="panel-heading"><div><span class="eyebrow">STRATEGY PIPELINE</span><h3>De hipótesis a evidencia</h3></div><span class="pill">PRUEBA FINAL SELLADA</span></div><ol class="pipeline-stages"><li v-for="s in counted" :key="s.label"><strong>{{ experiments.research ? s.count : '—' }}</strong><span>{{ s.label }}</span></li></ol><p class="small muted">Conteos por estado registrado; no representan validaciones superadas. {{ uncategorized }} candidatos con otro estado. Sin promoción automática.</p></section></template>
