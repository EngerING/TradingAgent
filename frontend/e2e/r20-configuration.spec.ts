import {test,expect,request as requests} from '@playwright/test'
import {readFile,writeFile} from 'node:fs/promises'
import {resolve} from 'node:path'
const out=resolve(process.env.R20_UI_ARTIFACTS!)
const url='/api/r20-v2/configuration'
const headers={Origin:'http://127.0.0.1:5182','X-R20-Configuration':'1'}
const values={risk_per_trade_pct:'20',capital_allocation_pct:'50',max_leverage:'5',daily_loss_limit_pct:'20',max_open_positions:'3'}
async function client(admin=false){const c=await requests.newContext({baseURL:'http://127.0.0.1:5182',extraHTTPHeaders:headers});expect((await c.post('/api/r20-v2/session',{data:{credential:process.env[admin?'R20_LAB_ADMIN_TOKEN':'R20_LAB_READER_TOKEN']}})).status()).toBe(200);return c}
// Compatibility tests for historical laboratory contracts; current UI coverage is r20-phase2.spec.ts.
test.describe.serial('Historical configuration API compatibility',()=>{
 test('reader, CSRF and forged role fail closed',async({request})=>{
  expect((await request.get(url)).status()).toBe(401)
  const c=await client(),a=await client(true)
  for(const action of ['draft','validate','activate'])expect((await c.post(url+'/'+action,{data:{}})).status()).toBe(403)
  expect((await a.post(url+'/draft',{headers:{Origin:'https://example.invalid'},data:{}})).status()).toBe(403)
  expect((await a.post(url+'/draft',{headers:{'X-R20-Configuration':''},data:{}})).status()).toBe(403)
  expect((await c.post('/api/orders',{data:{}})).status()).toBe(404)
  expect((await c.post('/api/r20-v2/session',{data:{credential:process.env.R20_LAB_READER_TOKEN,role:'config-admin'}})).status()).toBe(200)
  expect((await c.post(url+'/draft',{data:{values,role:'config-admin'}})).status()).toBe(403)
  await c.dispose();await a.dispose()
 })
 test('legacy versions, validation, idempotency and CAS persist without execution',async()=>{
  const c=await client(true),get=async()=> (await c.get(url)).json()
  const before=await get()
  for(const key of Object.keys(values)){
   const partial={...values};delete partial[key as keyof typeof partial]
   expect((await (await c.post(url+'/preview',{data:{values:partial}})).json()).blockers).toContain('FIELDS_REQUIRED')
  }
  const body={revision:before.revision,requestId:crypto.randomUUID(),values}
  const first=await c.post(url+'/draft',{data:body});expect(first.status()).toBe(200)
  expect(await (await c.post(url+'/draft',{data:body})).json()).toEqual(await first.json())
  const race=await Promise.all([1,2].map(()=>c.post(url+'/draft',{data:{revision:before.revision+1,requestId:crypto.randomUUID(),values}})))
  expect(race.map(r=>r.status()).sort()).toEqual([200,409])
  const current=await get();expect((await c.post(url+'/validate',{data:{revision:current.revision,requestId:crypto.randomUUID()}})).status()).toBe(200)
  const after=await get();expect(after.accountingRevision).toBe(before.accountingRevision)
  expect(after.executionEnabled).toBe(false);expect(after.ordersSupported).toBe(false)
  await writeFile(resolve(out,'legacy-http.json'),JSON.stringify({before,after},null,2));await c.dispose()
 })
 test('unknowns still prevent historical activation and preserve null assessment',async()=>{
  const c=await client(true);const s=await (await c.get(url)).json()
  expect((await c.post(url+'/activate',{data:{revision:s.revision,requestId:crypto.randomUUID()}})).status()).toBe(422)
  const p=await (await c.post(url+'/preview',{data:{values}})).json()
  expect(p.assessment).toBeNull()
  const context=JSON.parse(await readFile(resolve(out,'context.json'),'utf8'))
  expect(context.cost_unknowns).toEqual(['SLIPPAGE_UNKNOWN','FINANCING_UNKNOWN'])
  // A midnight boundary blocks before cost evaluation; never reset the preserved ledger for a UI test.
  if(p.blockers.includes('DAY_BOUNDARY_UNVERIFIED'))expect(p.blockers).toEqual(['DAY_BOUNDARY_UNVERIFIED'])
  else expect(p.blockers).toEqual(expect.arrayContaining(['SLIPPAGE_UNKNOWN','FINANCING_UNKNOWN']))
  expect((await (await c.get(url)).json()).currentProfile).toBeNull();await c.dispose()
 })
})
