import { readFileSync, mkdirSync } from 'node:fs';
import { test, expect } from '@playwright/test';
import type { Page, APIRequestContext } from '@playwright/test';
const ready = JSON.parse(readFileSync('../tmp/m014b/browser/ready.json', 'utf8')) as { origin: string; authOrigin: string; resource: string };
const control = async (request: APIRequestContext, command: string) => { const r = await request.post(`${ready.authOrigin}/fixture/control/${command}`, { headers: { 'X-Fixture-Control': 'public-synthetic-only' } }); expect(r.status()).toBe(204); };
const post = async (request: APIRequestContext, route: string, data: unknown) => {
  const r = await request.get('/bff/csrf'); expect(r.status()).toBe(200); const { token } = await r.json() as { token: string };
  return request.post(route, { data, headers: { Origin: ready.origin, 'X-CSRF-TOKEN': token } });
};
async function login(page: Page, user = 'viewer', password = 'fixture-password') {
  await page.goto('/'); await page.getByLabel('Email address').fill(`${user}@fixture.invalid`); await page.getByLabel('Password', { exact: true }).fill(password); await page.getByRole('button', { name: 'Sign in', exact: true }).click();
}
async function mfa(page: Page, user = 'viewer') {
  await login(page, user); await expect(page.getByRole('button', { name: 'Continue securely' })).toBeEnabled(); await page.getByRole('button', { name: 'Continue securely' }).click();
  if (user === 'enroll') { await expect(page.getByRole('img', { name: 'Authenticator enrollment QR. Keep private.' })).toBeVisible(); await page.getByRole('button', { name: /I saved my authenticator/ }).click(); }
  await expect(page.getByLabel('Verification code')).toBeVisible();
}
async function signedIn(page: Page, user = 'viewer') {
  await mfa(page, user); await page.getByLabel('Verification code').fill('123456'); await page.getByRole('button', { name: 'Verify code' }).click(); await expect(page.getByRole('heading', { name: 'Identity authenticated', exact: true })).toBeVisible();
}
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => { if (new URL(route.request().url()).origin !== ready.origin) throw new Error('NON_BFF_BROWSER_REQUEST'); return route.continue(); });
});
test('HTTPS login keeps approved design and no operational routes', async ({ page }) => {
  await page.goto('/'); await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible(); await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Live Trading Real money' })).toBeDisabled();
  expect((await page.request.get('/orders')).status()).toBe(404); mkdirSync('../artifacts/m014b/screenshots', { recursive: true }); await page.screenshot({ path: '../artifacts/m014b/screenshots/login.png' });
});
test('incorrect password never creates an authenticated UI', async ({ page }) => { await login(page, 'viewer', 'incorrect'); await expect(page.getByRole('alert')).toContainText('Check your credentials'); expect((await page.request.get('/bff/session')).status()).toBe(401); });
test('AAL1 cannot access session or synthetic resource', async ({ page }) => { await login(page); await expect(page.getByRole('button', { name: 'Continue securely' })).toBeVisible(); expect((await page.request.get('/bff/session')).status()).toBe(401); expect((await page.request.get(`/bff/probe/${ready.resource}/Paper`)).status()).toBe(401); });
test('existing verified MFA AAL2 authorizes SQL resource and logout revokes stale cookie', async ({ page, context }) => {
  await signedIn(page); const session = await page.request.get('/bff/session'); expect(await session.json()).toMatchObject({ aal: 'aal2', renewable: false, executionAuthorized: false, providerSessionConfirmedActive: false });
  expect((await page.request.get(`/bff/probe/${ready.resource}/Paper`)).status()).toBe(200);
  const cookie = (await context.cookies()).find(c => c.name === '__Host-TradingAgent.Session')!; expect({ secure: cookie.secure, httpOnly: cookie.httpOnly, sameSite: cookie.sameSite, path: cookie.path }).toEqual({ secure: true, httpOnly: true, sameSite: 'Strict', path: '/' }); expect(cookie.expires * 1000 - Date.now()).toBeLessThanOrEqual(300000);
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length, cookie: document.cookie }))).toEqual({ local: 0, session: 0, cookie: '' });
  await page.screenshot({ path: '../artifacts/m014b/screenshots/session.png' }); await page.getByRole('button', { name: 'Sign out', exact: true }).click(); await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await context.addCookies([cookie]); expect((await page.request.get('/bff/session')).status()).toBe(401);
});
test('safe fresh enrollment QR clears before verification and wrong code gets a new challenge', async ({ page }) => {
  await mfa(page, 'enroll'); await expect(page.getByText(/enrollment key private/)).toHaveCount(0); await page.screenshot({ path: '../artifacts/m014b/screenshots/mfa.png' });
  await page.getByLabel('Verification code').fill('000000'); await page.getByRole('button', { name: 'Verify code' }).click(); await expect(page.getByRole('alert')).toContainText('Code rejected'); await expect(page.getByLabel('Verification code')).toBeEmpty();
  await page.getByLabel('Verification code').fill('123456'); await page.getByRole('button', { name: 'Verify code' }).click(); await expect(page.getByRole('heading', { name: 'Identity authenticated' })).toBeVisible();
});
for (const user of ['orphan', 'ambiguous']) test(`incomplete or ambiguous MFA blocks ${user} without deletion`, async ({ page }) => { await login(page, user); await expect(page.getByRole('alert')).toContainText('No factor was deleted'); });
for (const user of ['no-role', 'no-grant', 'other']) test(`SQL denies missing authorization or different resource for ${user}`, async ({ page }) => {
  await signedIn(page, user); const resource = user === 'other' ? 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' : ready.resource;
  expect((await page.request.get(`/bff/probe/${resource}/Paper`)).status()).toBe(403); expect((await page.request.get(`/bff/probe/${ready.resource}/Live`)).status()).toBe(403);
});
test('disabled identity cannot create a BFF session', async ({ page }) => { await mfa(page, 'disabled'); await page.getByLabel('Verification code').fill('123456'); await page.getByRole('button', { name: 'Verify code' }).click(); await expect(page.getByRole('alert')).toBeVisible(); expect((await page.request.get('/bff/session')).status()).toBe(401); });
test('SQL status revocation invalidates an existing session', async ({ page, request }) => { await signedIn(page); await control(request, 'disable-viewer'); try { expect((await page.request.get('/bff/session')).status()).toBe(401); await page.reload(); await expect(page.getByRole('heading', { name: 'Your session has expired' })).toBeVisible(); } finally { await control(request, 'enable-viewer'); } });
test('invalid cookie and fabricated complete route never display success', async ({ page, context }) => { await context.addCookies([{ name: '__Host-TradingAgent.Session', value: 'invalid', url: ready.origin, secure: true, httpOnly: true, sameSite: 'Strict' }]); await page.goto('/session/complete'); await expect(page.getByRole('heading', { name: 'Your session has expired' })).toBeVisible(); });
test('CSRF Origin CORS and XSS boundaries are enforced by actual HTTPS BFF', async ({ page }) => {
  await page.goto('/'); expect((await page.request.post('/bff/auth/login', { data: { email: 'viewer@fixture.invalid', password: 'fixture-password' }, headers: { Origin: ready.origin } })).status()).toBe(403);
  const csrf = await (await page.request.get('/bff/csrf')).json() as { token: string };
  expect((await page.request.post('/bff/auth/login', { data: {}, headers: { Origin: 'https://attacker.invalid', 'X-CSRF-TOKEN': csrf.token } })).status()).toBe(403);
  const r = await page.request.get('/bff/session', { headers: { Origin: 'https://attacker.invalid' } }); expect(r.headers()['access-control-allow-origin']).toBeUndefined();
  const headers = (await page.request.get('/')).headers(); expect(headers['content-security-policy']).toContain("script-src 'self'"); expect(headers['content-security-policy']).not.toContain('unsafe-inline'); expect(headers['referrer-policy']).toBe('no-referrer');
  await page.goto('/invitation?token_hash=public-fixture#access_token=public-fixture'); await expect(page.getByRole('heading', { name: 'Secure link exchange pending' })).toBeVisible(); expect(page.url()).toBe(`${ready.origin}/invitation`); expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
});
test('recovery and invitation callbacks are blocked for expired replay altered and wrong identity links', async ({ page }) => {
  for (const input of ['expired', 'reused', 'tampered', 'wrong-user', 'disabled', 'accepted', 'no-permission']) {
    await page.goto(`/invitation?code=${input}`); await expect(page.getByRole('heading', { name: 'Secure link exchange pending' })).toBeVisible();
  }
  expect((await page.request.post('/bff/auth/recovery')).status()).not.toBe(200); expect((await page.request.get('/bff/auth/invitation')).status()).toBe(404);
});
for (const fault of ['jwt-future', 'jwt-hs256']) test(`signed fixture incompatibility ${fault} fails closed`, async ({ page, request }) => { await control(request, fault); try { await login(page); await expect(page.getByRole('alert')).toContainText('Check your credentials'); expect((await page.request.get('/bff/session')).status()).toBe(401); } finally { await control(request, 'jwt-valid'); } });
test('provider unavailable stays unavailable without demo fallback', async ({ page, request }) => { await control(request, 'provider-down'); try { await login(page); await expect(page.getByRole('heading', { name: /be right back/ })).toBeVisible(); } finally { await control(request, 'provider-up'); } });
test('PostgreSQL connection refusal cannot authorize an existing session', async ({ page, request }) => { await signedIn(page); await control(request, 'db-down'); try { expect((await page.request.get('/bff/session')).status()).toBe(503); } finally { await control(request, 'db-up'); } });
test('bounded five minute session expires without refresh', async ({ page, request }) => { await signedIn(page); await control(request, 'expire'); try { await page.reload(); await expect(page.getByRole('heading', { name: 'Your session has expired' })).toBeVisible(); } finally { await control(request, 'clock-reset'); } });
test('single-use MFA challenge cannot be replayed', async ({ page }) => {
  const login = await post(page.request, '/bff/auth/login', { email: 'viewer@fixture.invalid', password: 'fixture-password' }); const body = await login.json() as { factors: { id: string }[] };
  const challenge = await (await post(page.request, '/bff/auth/mfa/challenge', { factorId: body.factors[0]!.id })).json() as { id: string };
  const payload = { challengeId: challenge.id, code: '123456' }; expect((await post(page.request, '/bff/auth/mfa/verify', payload)).status()).toBe(200); expect((await post(page.request, '/bff/auth/mfa/verify', payload)).status()).toBe(401);
});
test('cancel clears pending flow and no duplicate login POST is sent', async ({ page }) => {
  let count = 0; page.on('request', r => { if (r.url().endsWith('/bff/auth/login')) count++; }); await page.goto('/'); await page.getByLabel('Email address').fill('viewer@fixture.invalid'); await page.getByLabel('Password', { exact: true }).fill('fixture-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); }); await expect(page.getByRole('button', { name: 'Continue securely' })).toBeVisible(); expect(count).toBe(1);
  await page.getByRole('button', { name: 'Cancel and sign out' }).click(); await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible(); expect((await page.request.get('/bff/session')).status()).toBe(401);
});
test('BFF transport outage cannot select demo or display success', async ({ page, context }) => {
  await page.goto('/'); await context.route('**/bff/auth/login', route => route.abort('connectionrefused'));
  await page.getByLabel('Email address').fill('viewer@fixture.invalid'); await page.getByLabel('Password', { exact: true }).fill('fixture-password'); await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: /be right back/ })).toBeVisible(); await expect(page.getByText('Development demo')).toHaveCount(0);
});
test('rate budget rejects excess real HTTP login attempts', async ({ page }) => {
  let limited = false; for (let i = 0; i < 21; i++) { const r = await post(page.request, '/bff/auth/login', { email: 'rate@fixture.invalid', password: 'incorrect' }); if (r.status() === 429) { limited = true; break; } expect(r.status()).toBe(401); } expect(limited).toBe(true);
});
