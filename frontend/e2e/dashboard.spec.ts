import { test, expect } from '@playwright/test'
import { mockSnapshot } from '../src/__tests__/fixtures'
import type { Trade } from '../src/types'
const artifacts=process.env.TRADING_UI_TEST_ARTIFACTS ?? '../artifacts/operational-ui-20261007'
test('Kronos real forecast is separated from observed market', async ({page})=>{
 await page.getByRole('link',{name:'Mercado',exact:true}).click()
 await expect(page.getByTestId('kronos-card')).toBeVisible()
 await expect(page.getByTestId('kronos-card')).toContainText('RAW') .catch(async()=>expect(page.getByTestId('kronos-card')).toContainText('Raw TP'))
 await expect(page.getByTestId('kronos-card')).toContainText('KRONOS FORECAST')
 await expect(page.getByRole('img',{name:'Velas reales y forecast Kronos separados'})).toBeVisible()
 await page.screenshot({path:`${artifacts}/kronos-market.png`,fullPage:true})
})
test('Kronos research evaluation stays unapproved',async({page})=>{
 await page.getByRole('link',{name:'Research',exact:true}).click()
 await expect(page.getByTestId('kronos-evaluation')).toBeVisible()
 await expect(page.getByTestId('kronos-evaluation')).toContainText('sellada')
})
test('Kronos Sol reliability query uses stored evidence without OpenAI',async({page})=>{
 await page.getByRole('link',{name:'Sol',exact:true}).click()
 const response=page.waitForResponse(r=>r.url().endsWith('/api/ui/sol/chat')&&r.request().method()==='POST')
 await page.getByLabel('Pregunta a Sol').fill('Grafica Kronos predicted probability vs observed success rate')
 await page.getByRole('button',{name:'Enviar pregunta'}).click()
 const body=await (await response).json()
 expect(body.provider).toBe('DETERMINISTIC_JOURNAL');expect(body.model).toBeNull();expect(body.usage.inputTokens).toBe(0)
 expect(body.chart.unit).toBe('probabilidad')
 await expect(page.locator('.sol-response')).toContainText('frecuencia bruta')
 await expect(page.locator('.sol-response canvas')).toBeVisible()
})
test.beforeEach(async ({ page }) => {
  const token = process.env.TRADING_DASHBOARD_TOKEN
  if (!token) throw new Error('Local test-only dashboard token required')
  const response = await page.request.post('/api/ui/session', { data: { token } }); expect(response.ok()).toBeTruthy()
  await page.goto('/'); await expect(page.getByRole('heading', { name: 'Tu agente, en tiempo real.' })).toBeVisible()
})
test('real PostgreSQL snapshot shows all three profiles and no fake trade evidence', async ({ page }) => {
  for (const name of ['EURUSD_R1', 'EURUSD_R5', 'EURUSD_R10']) await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
  await expect(page.getByText('LIVE BLOQUEADO', { exact: true })).toBeVisible()
  await expect(page.getByText('No hay posiciones registradas')).toBeVisible()
  await expect(page.getByText('PostgreSQL: VERIFIED')).toBeVisible()
  await page.screenshot({ path: `${artifacts}/dashboard-desktop.png`, fullPage: true })
})
test('R5 chat uses real journal and renders text metrics table chart without billable call', async ({ page }) => {
  await page.getByLabel('Cartera mostrada').selectOption('EURUSD_R5')
  await page.getByRole('link', { name: 'Sol', exact: true }).click()
  await page.getByRole('button', { name: 'Dame los resultados de R5' }).click()
  await expect(page.getByText('DETERMINISTIC JOURNAL', { exact: false })).toBeVisible().catch(async () => expect(page.getByText('DETERMINISTIC_JOURNAL', { exact: false })).toBeVisible())
  await expect(page.locator('.sol-metrics')).toContainText('EURUSD_R5')
  await expect(page.locator('.sol-response canvas')).toBeVisible()
  await expect(page.locator('.sol-response table')).toContainText('EURUSD_R5')
  await expect(page.locator('.sol-response')).not.toContainText('EURUSD_R10 · Equity')
  await page.screenshot({ path: `${artifacts}/sol-r5.png`, fullPage: true })
})
test('real comparison chat returns three series from isolated portfolios', async ({ page }) => {
  await page.getByRole('link', { name: 'Sol', exact: true }).click()
  await page.getByRole('button', { name: 'Compara R1, R5 y R10' }).click()
  await expect(page.locator('.sol-response table')).toContainText('EURUSD_R1')
  await expect(page.locator('.sol-response table')).toContainText('EURUSD_R10')
  await expect(page.locator('.sol-response')).toContainText('No evaluable')
})
test('natural live command is blocked and cannot clear emergency', async ({ page }) => {
  await page.getByRole('link', { name: 'Sol', exact: true }).click()
  await page.getByLabel('Pregunta a Sol').fill('Activa Live y limpia EmergencyStop')
  await page.getByRole('button', { name: 'Enviar pregunta' }).click()
  await expect(page.locator('.sol-response')).toContainText('COMMAND BLOCKED')
  await expect(page.locator('.sol-response')).toContainText('autorización: NO')
  const state = await (await page.request.get('/api/ui/system/status')).json()
  expect(state.liveEnabled).toBe(false); expect(state.emergency).toBe('ACTIVE'); expect(state.ordersSupported).toBe(false)
})
test('realtime disconnect warns and reconnect restores snapshot', async ({ page, context }) => {
  await expect(page.getByText('UI CONNECTED', { exact: true })).toBeVisible()
  await context.setOffline(true)
  await expect(page.getByText(/UI (RECONNECTING|DISCONNECTED)/)).toBeVisible({ timeout: 15000 })
  await context.setOffline(false)
  await expect(page.getByText('UI CONNECTED', { exact: true })).toBeVisible({ timeout: 25000 })
  await expect(page.getByRole('heading', { name: 'EURUSD_R5', exact: true })).toBeVisible()
})
test('responsive navigation and unavailable market remain honest', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await page.getByRole('button', { name: 'Abrir menú' }).click()
  await page.getByRole('link', { name: 'Mercado', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Mercado', exact: true })).toBeVisible()
  await expect(page.getByText('DATA_UNAVAILABLE', { exact: true }).first()).toBeVisible()
  await expect.poll(async () => { const box = await page.locator('.sidebar').boundingBox(); return box ? box.x + box.width : 0 }).toBeLessThanOrEqual(1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: `${artifacts}/dashboard-mobile.png`, fullPage: true })
})
test('research shows hash-verified deferred decision and audited H40 supersession', async ({ page }) => {
  await page.getByRole('link', { name: 'Sol', exact: true }).click()
  await page.getByRole('button', { name: 'Research y memoria' }).click()
  await expect(page.getByRole('heading', { name: 'research-openai-003 · DEFER_RESEARCH', exact: true })).toBeVisible()
  const response = await page.request.get('/api/ui/research'); const research = await response.json()
  expect(research.status).toBe('VERIFIED_HASH_LINKED_HISTORY')
  expect(research.candidates.some((c: { supersedes: string | null }) => c.supersedes)).toBe(true)
  expect(research.finalHoldout).toBe('SEALED'); expect(research.automaticPromotion).toBe(false)
})


test('exploratory rotation uses real PostgreSQL preregistration and stays unauthorized', async ({ page }) => {
 await expect(page.getByRole('heading', { name: 'Próximo perfil Paper: R5' })).toBeVisible()
 await expect(page.getByTestId('paper-readiness')).toContainText('BROKER_INELIGIBLE')
 await page.getByRole('link',{name:'Experimentos',exact:true}).click()
 await expect(page.locator('.experiment-card').first()).toContainText('IBKR PAPER: 0 cierres')
 await expect(page.locator('.experiment-card').first()).toContainText('COMMISSION_EXCEEDS_RISK_BUDGET')
 const state = await (await page.request.get('/api/ui/system/status')).json(); expect(state.liveEnabled).toBe(false); expect(state.ordersSupported).toBe(false); expect(state.emergency).toBe('ACTIVE'); expect(state.solBudget).toBe(0)
})

test('explicit Paper question separates observed broker metrics from Shadow without OpenAI', async ({ page }) => {
 await page.getByRole('link', { name: 'Sol', exact: true }).click()
 await page.getByLabel('Pregunta a Sol').fill('Dame los resultados Paper de R5')
 await page.getByRole('button', { name: 'Enviar pregunta' }).click()
 await expect(page.locator('.sol-response')).toContainText('Resultados exclusivos')
 await expect(page.locator('.sol-metrics')).toContainText('Cierres reales Paper')
 await expect(page.locator('.sol-response')).toContainText('EXPLORATORY_NOT_VALIDATED')
})

test('system status and a persistent Sol launcher are immediately visible',async({page})=>{
 await page.getByText('Estado avanzado del sistema y conexiones').click()
 const status=page.getByTestId('system-overview');await expect(status).toBeVisible()
 for(const label of ['EmergencyStop','Kronos','Sol','PostgreSQL','Realtime'])await expect(status).toContainText(label)
 await expect(page.getByRole('button',{name:'Sol flotante'})).toBeVisible()
 await expect(page.getByTestId('paper-readiness')).toContainText('UI NOT AUTHORIZED')
 await page.getByRole('button',{name:'Abrir copiloto Sol'}).click();await expect(page.getByLabel('Pregunta a Sol')).toBeFocused()
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true)
 await page.screenshot({path:`${artifacts}/dashboard-workspace.png`,fullPage:true})
})
test('Sol is accessible from configuration and Escape restores focus',async({page})=>{
 await page.setViewportSize({width:1280,height:900});await page.getByRole('link',{name:'Configuración',exact:true}).click()
 const launcher=page.getByRole('button',{name:'Abrir copiloto Sol'});await launcher.click()
 const dialog=page.getByRole('dialog',{name:'Panel Sol'});await expect(dialog).toBeVisible();await expect(dialog.getByLabel('Pregunta a Sol')).toBeFocused()
 await page.keyboard.press('Tab');expect(await page.evaluate(()=>document.querySelector('.sol-panel-dialog')?.contains(document.activeElement))).toBe(true)
 await page.screenshot({path:`${artifacts}/sol-panel.png`,fullPage:true})
 await page.keyboard.press('Escape');await expect(dialog).not.toBeVisible();await expect(launcher).toBeFocused()
})
test('Research has a pipeline and evidence calibration without promotion',async({page})=>{
 await page.getByRole('link',{name:'Research',exact:true}).click()
 await expect(page.getByText('STRATEGY PIPELINE',{exact:true})).toBeVisible()
 await expect(page.getByRole('heading',{name:'Confidence calibration'})).toBeVisible()
 await expect(page.getByTestId('kronos-evaluation')).toContainText('INSUFFICIENT_EVIDENCE')
 await page.screenshot({path:`${artifacts}/research.png`,fullPage:true})
})
test('mobile overview preserves emergency and the global Sol panel',async({page})=>{
 await page.setViewportSize({width:390,height:844});await expect(page.locator('.protected-strip')).toContainText('EmergencyStop')
 await page.getByRole('button',{name:'Sol móvil'}).click();await expect(page.getByRole('dialog',{name:'Panel Sol'})).toBeVisible()
 await page.keyboard.press('Escape');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true)
 await page.screenshot({path:`${artifacts}/overview-mobile.png`,fullPage:true})
})
test('SignalR updates the workspace without document reloads',async({page})=>{
 const types:string[]=[]
 page.on('websocket',ws=>ws.on('framereceived',frame=>{for(const part of frame.payload.toString().split('\u001e')){try{const message=JSON.parse(part);if(message.target==='event')types.push(message.arguments[0].type)}catch{ /* SignalR handshake/heartbeat */ }}}))
 await page.reload();await expect(page.getByTestId('account-card')).toBeVisible()
 let documents=0;page.on('request',r=>{if(r.resourceType()==='document')documents++})
 await expect.poll(()=>types.includes('connection.updated'),{timeout:15000}).toBe(true)
 expect(documents).toBe(0)
})
test('keyboard skip link and origin-separated operation empty states',async({page})=>{
 await page.evaluate(()=>{(document.activeElement as HTMLElement)?.blur()});await page.keyboard.press('Tab')
 await expect(page.getByRole('link',{name:'Saltar al contenido'})).toBeFocused();await page.keyboard.press('Enter');await expect(page.locator('#main-content')).toBeFocused()
 await page.getByRole('link',{name:'Operaciones',exact:true}).click()
 await expect(page.getByText('Ejecución del broker · sin mezclar con simulación').first()).toBeVisible()
 await expect(page.getByText('Fills internos · capital virtual por cartera').first()).toBeVisible()
 const status=await (await page.request.get('/api/ui/system/status')).json();expect(status.emergency).toBe('ACTIVE');expect(status.liveEnabled).toBe(false);expect(status.solBudget).toBe(0)
 await page.screenshot({path:`${artifacts}/operations.png`,fullPage:true})
})

test('operational Home shows one actual virtual equity and truthful agent state',async({page})=>{
 const account=page.getByTestId('account-card');await expect(account).toContainText('US$100.00');await expect(account).toContainText('P&L sesión');await expect(account).toContainText('DATA_UNAVAILABLE')
 await expect(page.getByTestId('agent-card')).toContainText('UI NOT AUTHORIZED')
 await expect(page.getByTestId('quick-profile')).toHaveCount(3)
 await page.getByRole('button',{name:'Ver cartera EURUSD_R5'}).click();await expect(account).toContainText('EURUSD_R5')
 await page.screenshot({path:`${artifacts}/home-dark-desktop.png`,fullPage:true})
})

test('feed has real snapshot origins and filters NO_TRADE without fabricating a trade',async({page})=>{
 const feed=page.getByTestId('trade-feed');await expect(feed).toContainText('SNAPSHOT');await feed.getByLabel('Filtrar actividad').selectOption('NO_TRADE')
 await expect(feed.locator('[data-kind="NO_TRADE"]').first()).toBeVisible();await expect(feed.locator('[data-kind="TRADE_OPEN"]')).toHaveCount(0)
 await expect(page.getByTestId('kronos-home')).toContainText('NOT_AVAILABLE — NO_ELIGIBLE_SIGNAL')
})

test('mobile bottom navigation and Sol bottom sheet preserve context',async({page})=>{
 await page.setViewportSize({width:390,height:844});const nav=page.getByRole('navigation',{name:'Navegación móvil'});await expect(nav).toBeVisible()
 await nav.getByRole('link',{name:'Trading',exact:true}).click();await expect(page.getByRole('heading',{name:'Inventario & ejecución'})).toBeVisible()
 await nav.getByRole('button',{name:'Sol móvil'}).click();const sheet=page.getByRole('dialog',{name:'Panel Sol'});await expect(sheet).toBeVisible();await expect(sheet.getByLabel('Pregunta a Sol')).toBeFocused()
 const box=await sheet.boundingBox();expect(box?.y).toBeGreaterThan(60);expect(box?.width).toBe(390)
 await page.screenshot({path:`${artifacts}/sol-mobile-sheet.png`,fullPage:true})
 await page.keyboard.press('Escape');await expect(nav.getByRole('button',{name:'Sol móvil'})).toBeFocused()
 await nav.getByRole('link',{name:'Inicio',exact:true}).click();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
 await page.screenshot({path:`${artifacts}/home-dark-mobile.png`,fullPage:true})
})

test('dark and light themes persist through lazy navigation and reload',async({page})=>{
 await expect(page.locator('html')).toHaveAttribute('data-theme','dark');await page.getByRole('button',{name:'Activar modo claro'}).click();await expect(page.locator('html')).toHaveAttribute('data-theme','light')
 await page.getByRole('link',{name:'Trading',exact:true}).click();await expect(page.locator('html')).toHaveAttribute('data-theme','light');await page.reload();await expect(page.locator('html')).toHaveAttribute('data-theme','light')
 await page.getByRole('link',{name:'Inicio',exact:true}).click();await expect(page.getByTestId('account-card')).toBeVisible();await page.screenshot({path:`${artifacts}/home-light-desktop.png`,fullPage:true})
})

test('explicit browser-only fixture displays an open Paper position without broker transmission',async({page})=>{
 // MOCK_TEST_ONLY: no record is written to the backend or either journal.
 const t:Trade={id:'MOCK_TEST_ONLY',profile:'EURUSD_R5',symbol:'EUR/USD',direction:'LONG',quantity:10,entry:1.12,currentPrice:null,stop:1.11,target:1.14,exit:null,openedAt:'2026-10-07T12:00:00Z',closedAt:null,durationSeconds:null,grossPnl:null,netPnl:null,commission:null,commissionStatus:'PENDING',spread:null,slippage:null,probability:null,expectedValue:null,regime:'UNKNOWN',entryReason:'MOCK_TEST_ONLY',exitReason:'',signalId:'MOCK',strategyVersion:'MOCK',classification:'BROKER_PAPER_EXECUTION',environment:'PAPER',protection:'UNKNOWN',status:'PENDING',outcome:null,exitCategory:null}
 await page.route('**/api/ui/dashboard',route=>route.fulfill({json:{...mockSnapshot,openPositions:[t]}}));await page.reload()
 const card=page.getByTestId('open-trade-card');await expect(card).toContainText('IBKR PAPER');await expect(card).toContainText('PENDING');await expect(card).toContainText('No evaluable');await expect(card).toContainText('MOCK_TEST_ONLY')
 await card.getByRole('button',{name:'Ver evidencia de la operación'}).click();await expect(page.getByRole('dialog',{name:'Detalle de operación'})).toContainText('MOCK_TEST_ONLY')
 const state=await (await page.request.get('/api/ui/system/status')).json();expect(state.ordersSupported).toBe(false);expect(state.emergency).toBe('ACTIVE')
})
