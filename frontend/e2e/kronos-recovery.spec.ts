import { test, expect } from '@playwright/test'
import type { DashboardSnapshot } from '../src/types'
const artifacts=process.env.TRADING_UI_TEST_ARTIFACTS ?? '../artifacts/research/kronos/recovery-20261008'

test.beforeEach(async({page})=>{
 const token=process.env.TRADING_DASHBOARD_TOKEN
 if(!token)throw new Error('Local read-only dashboard token required')
 expect((await page.request.post('/api/ui/session',{data:{token}})).ok()).toBe(true)
})

test('persisted authentic forecast reaches API and chart with honest diagnostics',async({page})=>{
 const response=await page.request.get('/api/ui/dashboard');expect(response.ok()).toBe(true)
 const snapshot=await response.json() as DashboardSnapshot
 const k=snapshot.kronos;expect(k?.latest?.model).toBe('NeoQuasar/Kronos-base')
 expect(k?.latest?.historical.length).toBeGreaterThan(0);expect(k?.latest?.quantiles.length).toBe(12)
 expect(k?.diagnostics?.total_paths).toBe(32);expect(k?.diagnostics?.operational_health).toBe(k?.operationalHealth)
 if(k?.calibrationState!=='CALIBRATED')expect(k?.calibration.brier_score).toBeNull()
 expect(snapshot.system.solBudget).toBe(0);expect(snapshot.system.emergency).toBe('ACTIVE');expect(snapshot.system.liveEnabled).toBe(false)
 await page.goto('/');await page.getByRole('link',{name:'Mercado',exact:true}).click()
 const card=page.getByTestId('kronos-card');await expect(card.getByTestId('kronos-diagnostics')).toBeVisible()
 await expect(card).toContainText('Trayectorias válidas');await expect(card).toContainText('no autorización')
 await expect(page.getByRole('img',{name:'Velas reales y forecast Kronos separados'})).toBeVisible()
 await page.screenshot({path:`${artifacts}/kronos-diagnostics-desktop.png`,fullPage:true})
 await page.setViewportSize({width:390,height:844})
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
 await page.screenshot({path:`${artifacts}/kronos-diagnostics-mobile.png`,fullPage:true})
})

test('real SignalR preserves forecast identity and distinguishes unavailable observers',async({page})=>{
 test.setTimeout(50000)
 const delivered: {type:string;data:{latest?:{prediction_id:string};diagnostics?:{operational_health:string}}}[]=[];let heartbeats=0
 page.on('websocket',socket=>socket.on('framereceived',frame=>{
  const text=typeof frame.payload==='string'?frame.payload:frame.payload.toString()
  for(const part of text.split('\u001e')){
   if(!part)continue
   const message=JSON.parse(part) as {target?:string;arguments?:typeof delivered}
   if(message.target==='event'&&message.arguments?.[0]?.type==='kronos.updated')delivered.push(message.arguments[0])
   if(message.target==='event'&&message.arguments?.[0]?.type==='connection.updated')heartbeats++
  }
 }))
 await page.goto('/');await expect(page.getByText('UI CONNECTED',{exact:true})).toBeVisible()
 const before=await (await page.request.get('/api/ui/dashboard')).json() as DashboardSnapshot
 if(before.kronos?.operationalHealth==='UNAVAILABLE'){
  expect(before.kronos.status).toBe('KRONOS_UNAVAILABLE')
  await expect.poll(()=>heartbeats,{timeout:15000}).toBeGreaterThanOrEqual(2)
  const after=await (await page.request.get('/api/ui/dashboard')).json() as DashboardSnapshot
  expect(after.kronos?.latest?.prediction_id).toBe(before.kronos.latest?.prediction_id)
  expect(after.kronos?.operationalHealth).toBe('UNAVAILABLE')
  expect(delivered.every(update=>update.data.latest?.prediction_id===before.kronos?.latest?.prediction_id)).toBe(true)
  await expect(page.getByTestId('kronos-home').getByTestId('kronos-diagnostics')).toBeVisible()
  return
 }
 await expect.poll(()=>delivered.length,{timeout:40000}).toBeGreaterThan(0)
 const snapshot=await (await page.request.get('/api/ui/dashboard')).json() as DashboardSnapshot
 expect(delivered.at(-1)?.data.latest?.prediction_id).toBe(snapshot.kronos?.latest?.prediction_id)
 expect(delivered.at(-1)?.data.diagnostics?.operational_health).toBe(snapshot.kronos?.operationalHealth)
 await expect(page.getByTestId('kronos-home').getByTestId('kronos-diagnostics')).toBeVisible()
})
