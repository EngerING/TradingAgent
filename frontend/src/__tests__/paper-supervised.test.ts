import {beforeEach,describe,it,expect} from 'vitest'
import {createPinia,setActivePinia} from 'pinia'
import {mount} from '@vue/test-utils'
import PaperReadiness from '../components/PaperReadiness.vue'
import {useSystemStore,useExperimentStore} from '../stores'
import {useActivityStore} from '../stores/activity'
import {mockSnapshot} from './fixtures'

beforeEach(()=>{setActivePinia(createPinia());useSystemStore().status=structuredClone(mockSnapshot.system);useExperimentStore().experiments=structuredClone(mockSnapshot.experiments);useSystemStore().rotation={cohort:'MOCK_SUPERVISED',nextProfile:'EURUSD_R5',state:'PREPARED_NOT_AUTHORIZED',globalStop:null,protocolVersion:2,purpose:'PAPER_EXECUTION_DIAGNOSTIC',operationalState:'BLOCKED',authorizationStatus:'NOT_AUTHORIZED',completedPaper:0,observedFees:0,shadowTrades:0,skipped:1,maxOpenings:1,eligibility:{EURUSD_R1:{status:'BROKER_INELIGIBLE',reason:'COMMISSION_EXCEEDS_RISK_BUDGET',quantity:0,risk:0}}}})
describe('Supervised Paper read-only',()=>{
 it('shows exact eligibility and single-use trial without claiming readiness',()=>{const w=mount(PaperReadiness,{global:{stubs:{RouterLink:true}}});expect(w.text()).toContain('BROKER_INELIGIBLE');expect(w.text()).toContain('NOT_AUTHORIZED');expect(w.text()).toContain('máximo 1 apertura');expect(w.get('button:disabled').text()).toContain('START')})
 it('ASSESS presents existing local command without any API mutation',async()=>{const w=mount(PaperReadiness,{global:{stubs:{RouterLink:true}}});await w.get('button').trigger('click');expect(w.get('code').text()).toContain('-Action Assess -Cohort MOCK_SUPERVISED');expect(w.text()).toContain('esta pantalla no ejecuta acciones')})
 it('STOP procedure explains continued inventory management',async()=>{const w=mount(PaperReadiness,{global:{stubs:{RouterLink:true}}});await w.findAll('button').find(b=>b.text().startsWith('STOP'))!.trigger('click');expect(w.get('code').text()).toContain('-Action Stop');expect(w.text()).toContain('STOP conserva la gestión')})
 it('persisted callback IDs deduplicate across snapshots',()=>{const feed=useActivityStore();const rotation={...useSystemStore().rotation!,events:[{id:'own:1',kind:'PAPER_FILL',at:'2026-10-08T10:00:00Z',profile:'EURUSD_R5' as const,origin:'POSTGRESQL_PAPER_JOURNAL',detail:'exec'}]};for(const sequence of [1,2])feed.ingest({sequence,type:'rotation.updated',at:'2026-10-08T10:00:00Z',data:rotation});expect(feed.items).toHaveLength(1);expect(feed.items[0]?.kind).toBe('PAPER');expect(feed.items[0]?.title).toBe('PAPER_FILL')})
})
