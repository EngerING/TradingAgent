<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch, nextTick } from 'vue'
import { ShieldCheck } from '@lucide/vue'
import { api } from './api'
import { realtime } from './realtime'
import { useSystemStore, useTradeStore, useInterfaceStore } from './stores'
import AppSidebar from './components/AppSidebar.vue'
import AppHeader from './components/AppHeader.vue'
import SolPanel from './components/SolPanel.vue'
import StatusBadge from './components/StatusBadge.vue'
import BottomNavigation from './app/BottomNavigation.vue'
import { useActivityStore } from './stores/activity'
const system=useSystemStore();const trades=useTradeStore();const ui=useInterfaceStore()
ui.initializeTheme()
const token=ref('');const busy=ref(false);const checking=ref(true);const loginError=ref('');const sidebar=ref(false)
let stream:ReturnType<typeof realtime>|undefined
const detail=ref<HTMLDialogElement>()
watch(()=>trades.selected,async value=>{await nextTick();if(value&&!detail.value?.open)detail.value?.showModal();else if(!value)detail.value?.close()})
async function connect(){system.authenticated=true;stream=realtime();await stream.start()}
async function login(){busy.value=true;loginError.value='';try{await api.login(token.value);token.value='';await connect()}catch{loginError.value='Acceso no confirmado. Revisa el código local y que el backend está iniciado.';token.value=''}finally{busy.value=false}}
async function logout(){await stream?.stop();await api.logout();system.authenticated=false;trades.selected=null;useActivityStore().clear()}
onMounted(async()=>{try{await api.session();await connect()}catch{system.authenticated=false}finally{checking.value=false}})
onBeforeUnmount(()=>{void stream?.stop()})
</script>
<template>
 <div v-if="checking" class="session-loading" role="status" aria-label="Verificando sesión"><span class="brand">TradingAgent</span><div class="skeleton"></div><p>Recuperando tu espacio de investigación…</p></div>
 <div v-else-if="!system.authenticated" class="login-page"><div class="login-story"><div class="brand light-brand"><span class="brand-mark"><i></i><i></i><i></i></span><span>TradingAgent</span></div><span class="eyebrow">RESEARCH WORKSPACE</span><h1>Decisiones con evidencia.<br>Control en cada paso.</h1><p>Observa el mercado, compara experimentos y entiende al agente.</p><div class="login-safety"><ShieldCheck :size="24" /><span>Paper y simulación claramente separados.<br>Live permanece bloqueado.</span></div></div><form class="card login-form" @submit.prevent="login"><StatusBadge value="ACCESO LOCAL · SOLO LECTURA" tone="neutral" /><h2>Bienvenido a tu laboratorio</h2><p>Utiliza el código de acceso local del backend. No introduzcas tu API Key de OpenAI.</p><label for="access-code">Código de acceso del dashboard</label><input id="access-code" v-model="token" type="password" autocomplete="off" required maxlength="512" placeholder="Código local protegido"><p v-if="loginError" role="alert" class="notice">{{ loginError }}</p><button class="primary-button" :disabled="busy">{{ busy?'Verificando…':'Abrir TradingAgent' }}</button><small>Sesión HttpOnly de lectura. Sin credenciales IBKR en el navegador.</small></form></div>
 <div v-else class="app-shell" @keydown.esc="sidebar=false">
  <a href="#main-content" class="skip-link">Saltar al contenido</a>
  <button v-if="sidebar" class="nav-backdrop" aria-label="Cerrar menú" @click="sidebar=false"></button>
  <AppSidebar :open="sidebar" @navigate="sidebar=false" />
  <div class="main-shell"><AppHeader :menu-open="sidebar" @menu="sidebar=!sidebar" @logout="logout" @sol="ui.openSol" /><main id="main-content" tabindex="-1"><RouterView /></main><footer class="workspace-footer"><span>TradingAgent · evidencia persistente</span><span>America/Santo_Domingo · origen UTC</span></footer></div>
  <SolPanel /><BottomNavigation @more="sidebar=!sidebar" />
 </div>
 <dialog ref="detail" class="trade-dialog" aria-labelledby="trade-detail-title" @close="trades.selected=null"><header class="panel-heading"><h3 id="trade-detail-title">Detalle de operación</h3><button class="icon-button" aria-label="Cerrar detalle" @click="trades.selected=null">×</button></header><StatusBadge :value="trades.selected?.classification ?? 'DATA_UNAVAILABLE'" /><dl class="detail-list"><template v-for="(value,key) in trades.selected ?? {}" :key="key"><dt>{{ key }}</dt><dd>{{ value ?? 'No evaluable' }}</dd></template></dl></dialog>
</template>
