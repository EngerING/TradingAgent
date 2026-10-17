import {test,expect} from '@playwright/test'
import type {Page} from '@playwright/test'
import {readFile,writeFile} from 'node:fs/promises'
import {resolve} from 'node:path'
const out=resolve(process.env.R20_UI_ARTIFACTS!)
const headers={Origin:'http://127.0.0.1:5182','X-R20-Configuration':'1'}
async function login(page:Page,admin=false){await page.goto('/');await page.getByLabel('Credencial de pruebas').fill(process.env[admin?'R20_LAB_ADMIN_TOKEN':'R20_LAB_READER_TOKEN']!);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page.getByRole('heading',{name:'Preparación económica',exact:true})).toBeVisible()}
test.describe.serial('Technical Shadow lab',()=>{
 test('authenticated HTTP projection equals PostgreSQL including source distinction',async({request})=>{
  expect((await request.get('/api/r20-v2/shadow')).status()).toBe(401)
  expect((await request.post('/api/r20-v2/session',{headers,data:{credential:process.env.R20_LAB_READER_TOKEN}})).status()).toBe(200)
  const response=await request.get('/api/r20-v2/shadow');expect(response.status()).toBe(200)
  const actual=await response.json();const expected=JSON.parse(await readFile(resolve(out,'monitor-expected.json'),'utf8'))
  expect(actual).toEqual(expected);expect(actual.trades).toHaveLength(1)
  expect(actual.lastAuthenticRead.continuousFeed).toBe(false);expect(actual.brokerOrders).toBe(0)
  expect((await request.post('/api/r20-v2/preparation/save',{headers,data:{}})).status()).toBe(403)
  await writeFile(resolve(out,'http-monitor.json'),JSON.stringify(actual,null,2))
 })
 test('administrator saves technical purpose without Paper authority',async({page})=>{
  await login(page,true)
  for(const field of ['risk_per_trade_pct','daily_loss_limit_pct','max_open_positions'])await expect(page.locator(`[name="${field}"]`)).toHaveValue('')
  await page.getByLabel('Propósito del perfil').selectOption('TECHNICAL_VALIDATION')
  await page.getByLabel('Entorno solicitado').selectOption('IBKR_PAPER')
  for(const [name,value] of Object.entries({risk_per_trade_pct:'1',daily_loss_limit_pct:'5',max_open_positions:'1'}))await page.locator(`[name="${name}"]`).fill(value)
  await page.getByRole('button',{name:'Previsualizar y comprobar'}).click()
  await expect(page.getByText('TECHNICAL_SHADOW_ONLY',{exact:true})).toBeVisible()
  await expect(page.getByRole('button',{name:'Guardar configuración',exact:true})).toBeDisabled()
  await page.getByLabel('Entorno solicitado').selectOption('SHADOW')
  await page.getByRole('button',{name:'Previsualizar y comprobar'}).click()
  await expect(page.getByRole('button',{name:'Guardar configuración',exact:true})).toBeEnabled()
  await page.getByRole('button',{name:'Guardar configuración',exact:true}).click()
  await expect(page.getByRole('button',{name:'Validar versión guardada'})).toBeEnabled()
  await page.getByRole('button',{name:'Validar versión guardada'}).click()
  await expect(page.getByText('LISTO PARA REVISIÓN · NO ACTIVADO',{exact:true})).toBeVisible()
  await page.getByLabel('Propósito del perfil').selectOption('NORMAL')
  await page.getByRole('button',{name:'Recuperar última versión'}).click()
  await expect(page.getByLabel('Propósito del perfil')).toHaveValue('TECHNICAL_VALIDATION')
  for(const name of ['Iniciar','Detener','Cambiar entorno'])await expect(page.getByRole('button',{name,exact:true})).toBeDisabled()
 })
 for(const width of [1600,390])test(`monitor real lab ${width}: cycle, net loss, historical quote and stale`,async({page})=>{
  await page.setViewportSize({width,height:width===390?844:1100});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await login(page)
  await page.getByText('Seguimiento Shadow del laboratorio',{exact:true}).click()
  const monitor=page.locator('.shadow-monitor');await expect(monitor).toContainText('TECHNICAL_VALIDATION')
  await expect(monitor).toContainText('TAKE_PROFIT');await expect(monitor).toContainText('Sin posiciones Shadow abiertas.')
  await expect(monitor).toContainText('Corte histórico de lectura, sin feed continuo.')
  await expect(monitor).toContainText('UNVERIFIED_BETWEEN_QUOTES')
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  expect(errors).toEqual([])
  await monitor.screenshot({path:resolve(out,`monitor-${width}.png`)})
  await page.screenshot({path:resolve(out,`page-${width}.png`),fullPage:true})
  await page.route('**/api/r20-v2/shadow',r=>r.abort());await page.getByRole('button',{name:'Actualizar seguimiento Shadow'}).click()
  await expect(monitor.getByRole('alert')).toContainText('STALE');await expect(monitor).toContainText('TAKE_PROFIT')
 })
})
