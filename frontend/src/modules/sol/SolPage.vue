<script setup lang="ts">
import AdvancedPage from '../../app/AdvancedPage.vue'
import { ref,defineAsyncComponent } from 'vue'
const SolChat=defineAsyncComponent(()=>import('../../components/SolChat.vue'))
const research=ref(false)
const ResearchPage=defineAsyncComponent(()=>import('../research/ResearchPage.vue'))
</script>
<template><AdvancedPage title="Sol" description="Consulta estructurada sin autoridad de ejecución."><div class="tab-bar"><button :class="{active:!research}" @click="research=false">Sol Chat</button><button :class="{active:research}" @click="research=true">Research y memoria</button></div><ResearchPage v-if="research"/><div v-else class="card full-chat"><SolChat /></div></AdvancedPage></template>
