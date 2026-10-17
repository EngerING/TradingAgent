import {test,expect} from '@playwright/test'
const folder=process.env.TRADING_UI_TEST_ARTIFACTS ?? '../artifacts/r10-price-risk-20261008/ui'
test.beforeEach(async({page})=>{
 const token=process.env.TRADING_DASHBOARD_TOKEN;if(!token)throw new Error('Read-only session required')
 expect((await page.request.post('/api/ui/session',{data:{token}})).ok()).toBe(true)
 await page.goto('/');await expect(page.getByTestId('price-risk-experiment')).toBeVisible()
})
test('real journal exposes independent price risk without broker authority',async({page})=>{
 const card=page.getByTestId('price-risk-experiment');await expect(card).toContainText('10% PRICE RISK');await expect(card).toContainText('Paper BLOCKED');await expect(card).toContainText('R10 original');await expect(card).toContainText('SIMULATED SHADOW')
 await card.scrollIntoViewIfNeeded();await card.screenshot({path:`${folder}/price-risk-desktop.png`})
 const snapshot=await(await page.request.get('/api/ui/dashboard')).json();expect(snapshot.priceRisk.classification).toBe('SIMULATED_SHADOW');expect(snapshot.system.solBudget).toBe(0);expect(snapshot.system.emergency).toBe('ACTIVE');expect(snapshot.system.liveEnabled).toBe(false)
})
test('mobile and local Sol retain separation of modeled costs',async({page})=>{
 await page.setViewportSize({width:360,height:800});const card=page.getByTestId('price-risk-experiment');await card.scrollIntoViewIfNeeded();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
 await card.screenshot({path:`${folder}/price-risk-mobile.png`})
 const response=await page.request.post('/api/ui/sol/chat',{data:{requestId:crypto.randomUUID(),message:'¿Cuánto arriesga realmente R10?'}});expect(response.ok()).toBe(true);const result=await response.json();expect(result.status).toBe('LOCAL_EVIDENCE_ONLY');expect(result.text).toContain('R10 Experimental');expect(result.usage.estimatedCostUsd).toBe(0)
})
test('SignalR distinguishes authentic Shadow progress from an inactive observer',async({page})=>{
 test.setTimeout(65000)
 const delivered:{experiment:string;classification:string;updated_at:string}[]=[];let heartbeats=0
 page.on('websocket',ws=>ws.on('framereceived',frame=>{for(const part of frame.payload.toString().split('\u001e')){try{const message=JSON.parse(part);if(message.target==='event'){if(message.arguments[0].type==='priceRisk.updated')delivered.push(message.arguments[0].data);if(message.arguments[0].type==='connection.updated')heartbeats++}}catch{ /* heartbeat */ }}}))
 await page.reload();await expect(page.getByText('UI CONNECTED',{exact:true})).toBeVisible()
 const before=await(await page.request.get('/api/ui/dashboard')).json()
 if(before.priceRisk.status!=='SHADOW_RUNNING'){
  expect(['SHADOW_HEARTBEAT_STALE','STOPPED','DATA_UNAVAILABLE']).toContain(before.priceRisk.status)
  await expect.poll(()=>heartbeats,{timeout:15000}).toBeGreaterThanOrEqual(2)
  const after=await(await page.request.get('/api/ui/dashboard')).json()
  expect(after.priceRisk.updated_at).toBe(before.priceRisk.updated_at)
  expect(after.priceRisk.classification).toBe('SIMULATED_SHADOW')
  expect(delivered.every(update=>update.updated_at===before.priceRisk.updated_at)).toBe(true)
  return
 }
 await expect.poll(()=>delivered.length,{timeout:55000}).toBeGreaterThan(0)
 const snapshot=await(await page.request.get('/api/ui/dashboard')).json();expect(delivered.at(-1)?.experiment).toBe(snapshot.priceRisk.experiment);expect(delivered.at(-1)?.classification).toBe('SIMULATED_SHADOW');expect(delivered.at(-1)?.updated_at).toBeTruthy()
})
