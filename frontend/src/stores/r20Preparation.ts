import { computed, reactive, ref, shallowRef, watch } from 'vue'
import { defineStore } from 'pinia'
import { configRequest } from '../r20-configuration-contract'
import { preparationSchema,preparationPreviewSchema,preparationFields } from '../r20-preparation-contract'
import type { Preparation,PreparationPreview,PreparationValues } from '../r20-preparation-contract'
export const useR20Preparation=defineStore('r20-preparation',()=>{
 const values=reactive<PreparationValues>({logical_capital_usd:'100',allocation_usd:'20',requested_allocation_leverage:'20',
  risk_per_trade_pct:'',daily_loss_limit_pct:'',max_open_positions:'',environment:'SHADOW'})
 const state=shallowRef<Preparation|null>(null),preview=shallowRef<PreparationPreview|null>(null)
 const busy=ref(false),error=ref(''),stale=ref(false)
 const purpose=ref<'NORMAL'|'TECHNICAL_VALIDATION'>('NORMAL')
 const complete=computed(()=>preparationFields.every(k=>values[k].trim()!==''))
 const matchesSaved=computed(()=>!!state.value?.latest&&purpose.value===state.value.latest.profile.purpose&&[...preparationFields,'environment' as const].every(k=>values[k]===state.value?.latest?.profile.values[k]))
 let generation=0
 watch(values,()=>{generation++;preview.value=null},{flush:'sync'})
 watch(purpose,()=>{generation++;preview.value=null},{flush:'sync'})
 async function task(fn:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e){stale.value=true;error.value=e instanceof Error?e.message:'PREPARATION_UNAVAILABLE'}finally{busy.value=false}}
 async function refresh(){state.value=preparationSchema.parse(await configRequest('preparation'));stale.value=false}
 async function load(){await task(refresh)}
 async function calculate(){await task(async()=>{
  const requested=generation
  const result=preparationPreviewSchema.parse(await configRequest('preparation/preview',{values:{...values},purpose:purpose.value}))
  if(generation===requested)preview.value=result
 })}
 async function command(action:'save'|'validate'){
  await task(async()=>{
   const body={revision:state.value?.revision??0,requestId:crypto.randomUUID(),...(action==='save'?{values:{...values},purpose:purpose.value}:{})}
   await configRequest('preparation/'+action,body);await refresh()
  })
 }
 function loadVersion(revision?:number){const saved=revision?state.value?.history.find(x=>x.revision===revision):state.value?.latest
  if(saved){Object.assign(values,saved.profile.values);purpose.value=saved.profile.purpose}
 }
 return {values,purpose,state,preview,busy,error,stale,complete,matchesSaved,load,calculate,command,loadVersion}
})
