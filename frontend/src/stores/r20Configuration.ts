import { computed, reactive, ref, shallowRef, watch } from 'vue'
import { defineStore } from 'pinia'
import { configRequest, configurationSchema, previewSchema, fieldKeys } from '../r20-configuration-contract'
import type { Configuration, Preview, Values } from '../r20-configuration-contract'
export const useR20Configuration=defineStore('r20-configuration',()=>{
 const values=reactive<Values>({risk_per_trade_pct:'',capital_allocation_pct:'',max_leverage:'',daily_loss_limit_pct:'',max_open_positions:''})
 const state=shallowRef<Configuration|null>(null),preview=shallowRef<Preview|null>(null)
 const busy=ref(false),error=ref('')
 const complete=computed(()=>fieldKeys.every(k=>values[k].trim()!==''))
 const matchesSaved=computed(()=>!!state.value?.latest && fieldKeys.every(k=>values[k]===(state.value?.latest?.values[k]??'')))
 watch(values,()=>{preview.value=null},{flush:'sync'})
 async function task(fn:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e){error.value=e instanceof Error?e.message:'CONFIGURATION_UNAVAILABLE'}finally{busy.value=false}}
 async function refresh(){state.value=configurationSchema.parse(await configRequest('configuration'))}
 async function load(){await task(refresh)}
 async function calculate(){await task(async()=>{preview.value=previewSchema.parse(await configRequest('configuration/preview',{values:{...values}}))})}
 async function command(action:'draft'|'validate'|'activate'){
  await task(async()=>{
   const body={revision:state.value?.revision??0,requestId:crypto.randomUUID(),...(action==='draft'?{values:{...values}}:{})}
   await configRequest('configuration/'+action,body);await refresh()
  })
 }
 function loadDraft(){const saved=state.value?.latest?.values;if(saved)for(const k of fieldKeys)values[k]=saved[k]??''}
 return {values,state,preview,busy,error,complete,matchesSaved,load,calculate,command,loadDraft}
})
