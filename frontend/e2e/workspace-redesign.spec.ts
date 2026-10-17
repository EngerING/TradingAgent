import { test, expect } from '@playwright/test'
import { mockSnapshot } from '../src/__tests__/fixtures'
import type { Trade } from '../src/types'
const artifacts=process.env.TRADING_UI_TEST_ARTIFACTS ?? '../artifacts/frontend-workspace-20261008/final'
test.beforeEach(async({page})=>{
 const token=process.env.TRADING_DASHBOARD_TOKEN
 if(!token)throw new Error('Read-only local dashboard session required')
 expect((await page.request.post('/api/ui/session',{data:{token}})).ok()).toBe(true)
 await page.goto('/');await expect(page.getByTestId('account-card')).toBeVisible()
})
test('360px Home keeps equity and agent status in the first viewport and scrolls profiles locally',async({page})=>{
 await page.setViewportSize({width:360,height:800});await page.evaluate(()=>scrollTo(0,0))
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
 const account=await page.getByTestId('account-card').boundingBox();const agent=await page.getByTestId('agent-status').boundingBox()
 await page.screenshot({path:`${artifacts}/mobile-360-viewport.png`});expect(account!.y).toBeLessThan(agent!.y);expect(agent!.y+agent!.height).toBeLessThan(730)
 const profiles=page.locator('.quick-profiles')
 expect(await profiles.evaluate(e=>e.scrollWidth>e.clientWidth)).toBe(true)
 await page.screenshot({path:`${artifacts}/mobile-360-viewport.png`})
 await page.getByRole('button',{name:'Ver cartera EURUSD_R10'}).click();await expect(page.getByTestId('account-card')).toContainText('EURUSD_R10')
 const detail=page.getByTestId('quick-profile').last();await detail.getByText('Detalle de cartera',{exact:true}).click();await expect(detail.getByText('Profit factor neto',{exact:true})).toBeVisible()
 await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:`${artifacts}/mobile-360-full.png`,fullPage:true})
})
test('desktop and light preserve useful labels, contrast and keyboard focus',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message))
 for(const theme of ['dark','light']){
  if(theme==='light')await page.getByRole('button',{name:'Activar modo claro'}).click()
  // Theme controls transition for 120ms. Capture the settled state, not a blend
  // of dark and light that can make a screenshot look falsely low-contrast.
  await expect.poll(()=>page.locator('.secondary-button').first().evaluate(e=>getComputedStyle(e).backgroundColor)).toBe(theme==='dark'?'rgb(16, 49, 45)':'rgb(241, 245, 249)')
  await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:`${artifacts}/desktop-${theme}-viewport.png`})
  for(const selector of ['.agent-actions .primary-button','.agent-actions .secondary-button','.sol-launcher','.sidebar nav a.router-link-exact-active']){
  const contrast=await page.locator(selector).evaluate(e=>{
   const c=getComputedStyle(e);const lum=(s:string)=>{const values=s.match(/[\d.]+/g)!.slice(0,3).map(Number).map(x=>{const v=x/255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return .2126*values[0]!+.7152*values[1]!+.0722*values[2]!}
   const a=lum(c.color),b=lum(c.backgroundColor);return(Math.max(a,b)+.05)/(Math.min(a,b)+.05)
  });expect(contrast).toBeGreaterThanOrEqual(4.5)
  }
 }
 await page.getByRole('button',{name:'Activar modo oscuro'}).focus();await expect(page.getByRole('button',{name:'Activar modo oscuro'})).toBeFocused()
 await page.getByRole('button',{name:'Activar modo oscuro'}).press('Enter')
 await page.getByRole('link',{name:'Mercado',exact:true}).click()
 const signalContrast=await page.locator('.decision-row').first().evaluate(e=>{
  const s=getComputedStyle(e);const lum=(rgb:string)=>{const a=rgb.match(/[\d.]+/g)!.slice(0,3).map(Number).map(n=>{const v=n/255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return .2126*a[0]!+.7152*a[1]!+.0722*a[2]!};const a=lum(s.color),b=lum(s.backgroundColor);return(Math.max(a,b)+.05)/(Math.min(a,b)+.05)
 });expect(signalContrast).toBeGreaterThanOrEqual(4.5)
 await page.screenshot({path:`${artifacts}/market-dark-final.png`,fullPage:true})
 await page.getByRole('link',{name:'Inicio',exact:true}).click();await page.getByRole('button',{name:'Abrir copiloto Sol'}).click()
 await expect(page.getByRole('dialog',{name:'Panel Sol'})).toContainText('LOCAL EVIDENCE · GPT inactivo')
 await page.screenshot({path:`${artifacts}/sol-desktop-local.png`});await page.keyboard.press('Escape')
 await expect(page.getByRole('button',{name:'Abrir copiloto Sol'})).toBeFocused();expect(errors).toEqual([])
})
test('browser-only fixtures keep Paper and Shadow distinct with pending P&L, without trading',async({page})=>{
 const base:Trade={id:'MOCK_TEST_ONLY',profile:'EURUSD_R5',symbol:'EUR/USD',direction:'LONG',quantity:10,entry:1.12,currentPrice:1.121,stop:1.11,target:1.14,exit:null,openedAt:'2026-10-08T03:00:00Z',closedAt:null,durationSeconds:60,grossPnl:.01,netPnl:null,commission:null,commissionStatus:'PENDING',spread:null,slippage:null,probability:null,expectedValue:null,regime:'UNKNOWN',entryReason:'MOCK_TEST_ONLY',exitReason:'',signalId:'MOCK',strategyVersion:'MOCK',classification:'BROKER_PAPER_EXECUTION',environment:'PAPER',protection:'UNKNOWN',status:'PENDING',outcome:null,exitCategory:null}
 await page.route('**/api/ui/dashboard',route=>route.fulfill({json:{...mockSnapshot,openPositions:[base,{...base,id:'MOCK_SHADOW',classification:'SIMULATED_SHADOW'}]}}));await page.reload()
 const cards=page.getByTestId('open-trade-card');await expect(cards).toHaveCount(2);await expect(cards.first()).toContainText('IBKR PAPER');await expect(cards.last()).toContainText('SIMULATED SHADOW')
 await expect(cards.first()).toContainText('PENDING');await expect(cards.first()).toContainText('No evaluable');await expect(cards.first()).toContainText('ProtecciónUNKNOWN')
 await page.screenshot({path:`${artifacts}/inventory-fixture-only.png`,fullPage:true})
 const system=await(await page.request.get('/api/ui/system/status')).json();expect(system.ordersSupported).toBe(false);expect(system.emergency).toBe('ACTIVE');expect(system.solBudget).toBe(0)
})
test('reduced motion and unavailable evidence retain explanatory states',async({page})=>{
 await page.emulateMedia({reducedMotion:'reduce'})
 await page.route('**/api/ui/dashboard',route=>route.fulfill({json:{...mockSnapshot,experiments:[],kronos:{status:'KRONOS_UNAVAILABLE',calibrationState:'INSUFFICIENT_EVIDENCE',stale:true,latest:null,calibration:{},byRegime:[],evaluation:null}}}));await page.reload()
 await expect(page.getByTestId('account-card')).toContainText('DATA_UNAVAILABLE');await expect(page.getByTestId('kronos-home')).toContainText('esperando ventana auténtica')
 await expect(page.getByTestId('trade-feed')).toBeVisible();expect(await page.evaluate(()=>matchMedia('(prefers-reduced-motion:reduce)').matches)).toBe(true)
})
