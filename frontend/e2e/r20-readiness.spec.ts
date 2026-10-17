import {test,expect} from '@playwright/test'
import {readFile,writeFile} from 'node:fs/promises'
const out=process.env.R20_UI_ARTIFACTS!
test('monitor authentication and read projection remain compatible',async({request})=>{
 expect((await request.get('/api/r20-v2/shadow')).status()).toBe(401)
 await request.post('/api/r20-v2/session',{headers:{Origin:'http://127.0.0.1:5182','X-R20-Configuration':'1'},data:{credential:process.env.R20_LAB_READER_TOKEN}})
 const r=await request.get('/api/r20-v2/shadow');expect(r.status()).toBe(200)
 const data=await r.json();const original=JSON.parse(await readFile(out+'/monitor-db.json','utf8'))
 expect(data).toEqual(original);expect(data.classification).toBe('SYNTHETIC_VIRTUAL_LAB')
 expect(data.positions).toHaveLength(0);expect(data.trades).toHaveLength(0)
 expect(data.status).toBe('NOT_PREREGISTERED')
 for(const path of ['shadow/open','shadow/stop','orders'])expect((await request.post('/api/r20-v2/'+path,{headers:{Origin:'http://127.0.0.1:5182','X-R20-Configuration':'1'},data:{}})).status()).toBe(404)
 await writeFile(out+'/monitor-http.json',JSON.stringify(data,null,2))
})
for(const width of [1600,390])test(`monitor empty state and retained evidence ${width}`,async({page})=>{
 await page.setViewportSize({width,height:1000});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message))
 await page.goto('/');await page.getByLabel('Credencial de pruebas').fill(process.env.R20_LAB_READER_TOKEN!)
 await page.getByRole('button',{name:'Entrar',exact:true}).click()
 await page.getByText('Seguimiento Shadow del laboratorio',{exact:true}).click()
 await expect(page.getByRole('heading',{name:'Seguimiento Shadow V2'})).toBeVisible()
 await expect(page.getByText('NOT_PREREGISTERED',{exact:true})).toBeVisible()
 await expect(page.locator('input[name]')).toHaveCount(6)
 for(const name of ['risk_per_trade_pct','daily_loss_limit_pct','max_open_positions'])expect(await page.locator(`[name="${name}"]`).inputValue()).toBe('')
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(errors).toEqual([])
 await page.route('**/api/r20-v2/shadow',route=>route.abort())
 await page.getByRole('button',{name:'Actualizar seguimiento Shadow',exact:true}).click()
 await expect(page.locator('.shadow-monitor')).toContainText('STALE')
 await expect(page.locator('.shadow-monitor')).toContainText('NOT_PREREGISTERED')
})
