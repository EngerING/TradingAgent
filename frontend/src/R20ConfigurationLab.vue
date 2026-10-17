<script setup lang="ts">
import { ref } from 'vue'
import { z } from 'zod'
import { configRequest } from './r20-configuration-contract'
import R20ConfigurationPage from './modules/r20-configuration/R20ConfigurationPage.vue'
const credential=ref(''),role=ref(''),error=ref(''),busy=ref(false)
async function login(){busy.value=true;error.value='';try{const session=z.object({role:z.enum(['config-admin','config-reader'])}).parse(await configRequest('session',{credential:credential.value}));role.value=session.role;credential.value=''}catch{error.value='Acceso no disponible. Comprueba tu credencial de pruebas.'}finally{busy.value=false}}
</script>
<template><R20ConfigurationPage v-if="role" :admin="role==='config-admin'"/><main v-else class="lab-login"><p>TRADINGAGENT · LABORATORIO AISLADO</p><h1>Configuración diaria R20</h1><p>Acceso de pruebas. Sin operaciones ni cohortes.</p><form @submit.prevent="login"><label>Credencial de pruebas<input v-model="credential" type="password" autocomplete="off" required></label><button :disabled="busy">Entrar</button></form><p v-if="error" role="alert">{{error}}</p></main></template>
<style>.lab-login{max-width:480px;margin:10vh auto;padding:28px;background:#142731;border:1px solid #36515e;border-radius:14px;color:#deedf3;font:16px/1.5 system-ui}.lab-login h1{font-size:26px}.lab-login input{display:block;box-sizing:border-box;width:100%;padding:12px;margin:10px 0 20px;background:#091d28;color:white;border:1px solid #63818f;border-radius:5px}.lab-login button{padding:12px 28px;background:#16695f;border:1px solid #70cdbc;border-radius:6px;color:white;font:inherit}.lab-login label{display:block}@media(max-width:540px){.lab-login{margin:30px 16px;padding:22px}}</style>
