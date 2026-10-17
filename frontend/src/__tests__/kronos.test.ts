import { describe, it, expect } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import KronosCard from '../components/KronosCard.vue'
import KronosEvaluation from '../components/KronosEvaluation.vue'
import KronosDiagnostics from '../components/KronosDiagnostics.vue'
import { useKronosStore, applyEvent } from '../stores'
import type { KronosView } from '../types'

describe('Kronos observation',()=>{
 it('explains degraded model paths separately from absent signal calibration',()=>{
  const view={status:'KRONOS_DEGRADED',calibrationState:'RAW_ONLY',diagnostics:{operational_health:'DEGRADED',reasons:['INVALID_MODEL_OHLC_TRAJECTORIES'],valid_paths:25,invalid_paths:7,total_paths:32,calibration_reason:'NO_ELIGIBLE_TECHNICAL_SIGNAL',observed_price_samples:10,observed_barrier_samples:5,minimum_calibration_samples:100,minimum_bucket_samples:30}} as KronosView
  const w=mount(KronosDiagnostics,{props:{view}})
  expect(w.text()).toContain('trayectorias OHLC inválidas');expect(w.text()).toContain('válidas 25 / 32');expect(w.text()).toContain('no significa que el proveedor esté desconectado');expect(w.text()).toContain('no autorización')
 })
 it('keeps unknown diagnostic reason visible and does not add controls',()=>{
  const w=mount(KronosDiagnostics,{props:{view:{reason:'MODEL_HASH_MISMATCH'} as KronosView}})
  expect(w.text()).toContain('MODEL_HASH_MISMATCH');expect(w.findAll('button')).toHaveLength(0)
 })
 it('unavailable is explicit and cannot activate execution',()=>{setActivePinia(createPinia());const w=mount(KronosCard);expect(w.text()).toContain('KRONOS UNAVAILABLE');expect(w.findAll('button')).toHaveLength(0)})
 it('empty economic evidence is insufficient',()=>{setActivePinia(createPinia());const w=mount(KronosEvaluation,{global:{stubs:{EquityChart:true}}});expect(w.text()).toContain('INSUFFICIENT_EVIDENCE');expect(w.text()).toContain('Prueba final sellada')})
 it('SignalR updates only the observation store',()=>{setActivePinia(createPinia());const data={status:'KRONOS_DEGRADED',latest:null} as KronosView;applyEvent({sequence:1,type:'kronos.updated',data,at:'2026-10-07T18:00:00Z'});expect(useKronosStore().view?.status).toBe('KRONOS_DEGRADED')})
})
