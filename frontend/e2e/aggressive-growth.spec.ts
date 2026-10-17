import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { mkdirSync, writeFileSync } from 'node:fs'

const artifacts = process.env.TRADING_UI_TEST_ARTIFACTS ?? '../artifacts/operational-ui-20261007'
const fixtureDb = process.env.TRADING_R20_TEST_DATABASE
test.beforeAll(() => mkdirSync(artifacts, { recursive: true }))
function fixture(action: string, id?: string) {
  const root = resolve('..')
  return JSON.parse(execFileSync(resolve(root, '.venv/Scripts/python.exe'),
    [resolve(root, 'python/tests/r20_dashboard_fixture.py'), action, ...(id ? [id] : [])],
    { env: { ...process.env, PYTHONPATH: resolve(root, 'python'), TRADING_LAB_DB: fixtureDb }, encoding: 'utf8' }))
}
async function login(page: import('@playwright/test').Page) {
  const token = process.env.TRADING_DASHBOARD_TOKEN
  if (!token) throw new Error('READ_ONLY_SESSION_REQUIRED')
  expect((await page.request.post('/api/ui/session', { data: { token } })).status()).toBe(200)
}
async function openR20(page: import('@playwright/test').Page) {
  const loaded = page.waitForResponse(r => r.url().endsWith('/api/ui/dashboard') && r.request().method() === 'GET')
  await page.goto('/aggressive-growth')
  expect((await loaded).status()).toBe(200)
  await expect(page.getByTestId('aggressive-growth')).toBeVisible()
}

test('R20 authentication rejects anonymous HTTP and SignalR', async ({ page }) => {
  expect((await page.request.get('/api/ui/dashboard')).status()).toBe(401)
  expect((await page.request.post('/hubs/dashboard/negotiate?negotiateVersion=1')).status()).toBe(401)
  await login(page)
  expect((await page.request.post('/hubs/dashboard/negotiate?negotiateVersion=1')).status()).toBe(200)
  expect((await page.request.get('/policy')).status()).toBe(401)
  expect((await page.request.post('/api/ui/commands/confirm', { data: {} })).status()).toBe(403)
})

test('R20 PostgreSQL projection and authenticated SignalR preserve journal evidence', async ({ page }) => {
  await login(page)
  const seed = fixtureDb ? fixture('prepare') : null
  const events: any[] = []
  page.on('websocket', socket => socket.on('framereceived', frame => {
    for (const part of frame.payload.toString().split('\u001e')) {
      if (!part) continue
      const message = JSON.parse(part)
      if (message.target === 'event') events.push(message.arguments[0])
    }
  }))
  await openR20(page)
  await expect(page.getByText('UI CONNECTED', { exact: true })).toBeVisible()
  const response = await page.request.get('/api/ui/dashboard')
  expect(response.status()).toBe(200)
  const snapshot = await response.json()
  expect(snapshot.system.ordersSupported).toBe(false)
  expect(snapshot.system.liveEnabled).toBe(false)
  expect(snapshot.system.solBudget).toBe(0)
  if (seed) {
    expect(snapshot.aggressiveGrowth.experiment).toBe(seed.experiment)
    expect(snapshot.aggressiveGrowth.equity).toBe(seed.equity)
    expect(snapshot.aggressiveGrowth.classification).toBe('SHADOW_SIMULATED')
    expect(snapshot.aggressiveGrowth.paper.classification).toBe('IBKR_PAPER')
    expect(snapshot.aggressiveGrowth.paperTrades).toBe(0)
    expect(snapshot.aggressiveGrowth.kronos.calibratedProbability).toBeNull()
    expect(snapshot.aggressiveGrowth.kronos.calibration).toBe('RAW_ONLY')
    expect(snapshot.aggressiveGrowth.winRate).toBeNull()
    const stopped = fixture('stop', seed.experiment)
    await expect.poll(() => events.some(e => e.type === 'aggressiveGrowth.updated' && e.data.status === 'STOPPED')).toBe(true)
    const delivered = events.findLast(e => e.type === 'aggressiveGrowth.updated')!.data
    expect(delivered.experiment).toBe(stopped.experiment)
    expect(delivered.equity).toBe(stopped.equity)
    expect(delivered.kronos.calibratedProbability).toBeNull()
    await expect(page.getByTestId('aggressive-growth')).toContainText('STOPPED')
    writeFileSync(`${artifacts}/r20-journal-signalr.json`, JSON.stringify({ seed, stopped, delivered }, null, 2))
  } else if (process.env.TRADING_R20_EXPECTED_EXPERIMENT) {
    // Supervised operational run: the caller supplies the actual preregistered ID.
    const r20 = snapshot.aggressiveGrowth
    expect(r20.experiment).toBe(process.env.TRADING_R20_EXPECTED_EXPERIMENT)
    expect(r20.runKind).toBe('FORWARD')
    expect(r20.classification).toBe('SHADOW_SIMULATED')
    expect(r20.paper.classification).toBe('IBKR_PAPER')
    expect(r20.paperTrades).toBe(0)
    expect(r20.kronos.calibratedProbability).toBeNull()
    expect(snapshot.system.emergency).toBe('ACTIVE')
    await expect.poll(() => events.filter(e => e.type === 'connection.updated').length).toBeGreaterThanOrEqual(2)
    await expect.poll(() => events.some(e => e.type === 'aggressiveGrowth.updated' && e.data.experiment === r20.experiment), { timeout: 25000 }).toBe(true)
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByTestId('r20-freshness')).toContainText('RECENT_JOURNAL')
    writeFileSync(`${artifacts}/r20-operational-signalr.json`, JSON.stringify({ experiment: r20.experiment, delivered: events.filter(e => e.type === 'aggressiveGrowth.updated'), fixtures: false }, null, 2))
  } else {
    // Operational Paper journal is deliberately empty before the first supervised start.
    expect(snapshot.aggressiveGrowth ?? null).toBeNull()
    expect(snapshot.system.emergency).toBe('ACTIVE')
    await expect(page.getByTestId('aggressive-growth')).toContainText('DATA_UNAVAILABLE')
    await expect.poll(() => events.length).toBeGreaterThan(0)
    writeFileSync(`${artifacts}/r20-before-start.json`, JSON.stringify({ aggressiveGrowth: null, system: snapshot.system, eventTypes: [...new Set(events.map(e => e.type))] }, null, 2))
  }
})

for (const [name, width, height] of [['desktop', 1600, 1080], ['mobile', 390, 844]] as const) {
  test(`R20 ${name} renders real backend evidence without overflow or browser errors`, async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', e => errors.push(e.message))
    await login(page)
    await page.setViewportSize({ width, height })
    await openR20(page)
    await expect(page.getByText('UI CONNECTED', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `${artifacts}/r20-${name}.png`, fullPage: true })
    expect(errors).toEqual([])
  })
}
