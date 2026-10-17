<script setup lang="ts">
import AdvancedPage from '../../app/AdvancedPage.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import { useExperimentStore } from '../../stores'
import type { Json } from '../../types'
import ResearchPipeline from '../../components/ResearchPipeline.vue'
import KronosEvaluation from '../../components/KronosEvaluation.vue'
const experiments=useExperimentStore()
function display(v:Json|undefined){return v==null?'DATA_UNAVAILABLE':typeof v==='object'?JSON.stringify(v):String(v)}
</script>
<template><AdvancedPage title="Memoria de investigación" description="Conclusiones persistentes, hipótesis y decisiones DEFER_RESEARCH."><ResearchPipeline /><KronosEvaluation /><section class="card"><h3>Sesiones anteriores</h3><div v-for="s in experiments.research?.sessions" :key="s.session" class="research-session"><b>{{ s.session }}</b><StatusBadge :value="s.state" /><span>{{ s.reason ?? 'Sin motivo registrado' }}</span></div><p v-if="!experiments.research?.sessions.length">DATA_UNAVAILABLE</p></section><section v-for="candidate in experiments.research?.candidates" :key="candidate.id" class="card"><div class="panel-heading"><h3>{{ candidate.parameters.name ?? candidate.id }}</h3><StatusBadge :value="candidate.state" /></div><p>{{ candidate.hypothesis }}</p><p class="notice">{{ candidate.reasons.join(' · ') }}</p><details><summary>Parámetros y resultados originales</summary><pre>{{ JSON.stringify({ version: candidate.version, parameters: candidate.parameters, results: candidate.results }, null, 2) }}</pre></details></section><section v-for="d in experiments.research?.deferred" :key="d.session" class="card"><h3>{{ d.session }} · DEFER_RESEARCH</h3><dl class="detail-list"><template v-for="(v, k) in d.plan" :key="k"><dt>{{ k }}</dt><dd>{{ display(v) }}</dd></template></dl></section></AdvancedPage></template>
