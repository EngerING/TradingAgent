<script setup lang="ts">
import { ref, watch, nextTick, defineAsyncComponent } from 'vue'
import { Sparkles } from '@lucide/vue'
import { useInterfaceStore } from '../stores'
const SolChat=defineAsyncComponent(()=>import('./SolChat.vue'))
const ui=useInterfaceStore();const dialog=ref<HTMLDialogElement>();const opened=ref(false)
let opener:HTMLElement|null=null
watch(()=>ui.solRequested,async()=>{
  if(dialog.value?.open){dialog.value.querySelector('textarea')?.focus();return}
  opener=document.activeElement instanceof HTMLElement?document.activeElement:null
  opened.value=true;dialog.value?.showModal();await nextTick()
  // Async chat may not yet be loaded; autofocus watcher below handles that case.
  dialog.value?.querySelector('textarea')?.focus()
})
function loaded(){if(dialog.value?.open)dialog.value.querySelector('textarea')?.focus()}
function closed(){opened.value=false;opener?.focus()}
function trap(event:KeyboardEvent){
  if(event.key!=='Tab'||!dialog.value?.open)return
  const controls=Array.from(dialog.value.querySelectorAll<HTMLElement>('button:not([disabled]),textarea:not([disabled]),input:not([disabled]),a[href],select:not([disabled]),summary,[tabindex="0"]')).filter(e=>e.getClientRects().length)
  const first=controls[0];const last=controls.at(-1)
  if(!first){event.preventDefault();dialog.value.focus()}
  else if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}
  else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
}
</script>
<template><button class="floating-sol" aria-label="Sol flotante" @click="ui.openSol"><Sparkles :size="20"/><span>Sol</span></button><dialog ref="dialog" class="sol-panel-dialog" aria-label="Panel Sol" tabindex="-1" @keydown="trap" @close="closed"><button class="drawer-close" aria-label="Cerrar Sol" @click="dialog?.close()">×</button><SolChat v-if="opened" @vue:mounted="loaded" /></dialog></template>
