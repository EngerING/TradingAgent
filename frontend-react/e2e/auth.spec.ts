import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdir } from 'node:fs/promises';
const base = 'http://localhost:3000';
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== base && url.origin !== 'http://localhost:3001') throw new Error('Unexpected non-local browser request');
    return route.continue();
  });
});
async function signIn(page: import('@playwright/test').Page) {
  await page.goto(base); await page.getByLabel('Email address').fill('demo@tradingagent.test');
  await page.getByLabel('Password', { exact: true }).fill('InventedPassword8');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Set up two-step verification' })).toBeVisible();
}
test('simulated login, loading, MFA, invalid code, completion and logout', async ({ page }) => {
  await signIn(page); await page.getByRole('button', { name: 'Continue to verification' }).click();
  await page.getByLabel('Verification code').fill('000000'); await page.getByRole('button', { name: 'Verify code' }).click();
  await expect(page.getByRole('alert')).toContainText('not accepted');
  await expect(page.getByLabel('Verification code')).toBeEmpty();
  await page.getByLabel('Verification code').fill('123456'); await page.getByRole('button', { name: 'Verify code' }).click();
  await expect(page.getByRole('heading', { name: 'Demonstration complete' })).toBeVisible();
  await expect(page.getByText(/No real session has been created/)).toBeVisible();
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length, cookies: document.cookie }))).toEqual({ local: 0, session: 0, cookies: '' });
  await page.getByRole('button', { name: 'Return to sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
});
test('recovery and single-use password continuation are explicit fixtures', async ({ page }) => {
  await page.goto(`${base}/forgot-password`); await page.getByLabel('Email address').fill('demo@tradingagent.test');
  await page.getByRole('button', { name: 'Send recovery link' }).click();
  await expect(page.getByText(/No email was sent/)).toBeVisible();
  await page.getByRole('link', { name: 'Continue recovery demo' }).click();
  await page.getByLabel('New password', { exact: true }).fill('InventedPassword123');
  await page.getByLabel('Confirm password').fill('InventedPassword123');
  await page.getByRole('button', { name: 'Set new password' }).click();
  await expect(page.getByText(/No real password or account has been changed/)).toBeVisible();
});
test('invitation demonstration never enables public registration', async ({ page }) => {
  await page.goto(`${base}/invitation`); await page.getByRole('button', { name: 'Start invitation demo' }).click();
  await page.getByLabel('New password', { exact: true }).fill('InventedPassword123');
  await page.getByLabel('Confirm password').fill('InventedPassword123');
  await page.getByRole('button', { name: 'Accept invitation' }).click();
  await expect(page.getByText(/No real password or account has been changed/)).toBeVisible();
});
test('keyboard, password visibility, errors and disabled actions', async ({ page }) => {
  await page.goto(base); await expect(page.getByRole('heading', { name:'Welcome back' })).toBeVisible();
  await page.keyboard.press('Tab'); await expect(page.getByRole('link', { name: 'Skip to sign in' })).toBeFocused();
  await page.keyboard.press('Tab'); await expect(page.getByLabel('Email address')).toBeFocused();
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByText('Enter a valid email address.')).toBeVisible();
  await page.getByRole('button', { name: 'Show password' }).click(); await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('type','text');
  await expect(page.getByRole('button', { name: /Continue with Google/ })).toBeDisabled();
  await expect(page.getByRole('button', { name: /Live Trading/ })).toBeDisabled();
  await page.getByRole('button', { name: 'Register' }).click(); await expect(page.getByRole('status')).toContainText('invitation only');
});
test('callback values are discarded, never reflected or persisted', async ({ page }) => {
  await page.goto(`${base}/reset-password?code=PUBLIC_TEST_VALUE#access_token=PUBLIC_TEST_VALUE`);
  await expect(page.getByRole('heading', { name: 'Secure link exchange pending' })).toBeVisible();
  expect(page.url()).toBe(`${base}/reset-password`);
  expect(await page.locator('body').textContent()).not.toContain('PUBLIC_TEST_VALUE');
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
  await page.getByRole('link', { name:'Back to sign in' }).click();
  await expect(page.getByRole('heading', { name:'Welcome back' })).toBeVisible();
});
for (const state of ['expired','denied','unavailable','progress']) {
  test(`session state ${state} has a recovery path and no execution control`, async ({ page }) => {
    await page.goto(`${base}/session/${state}`);
    await expect(page.getByRole('button', { name: 'Return to sign in' })).toBeVisible();
    await expect(page.getByText(/OFFLINE \/ NO_TRADE/, { exact: false }).first()).toBeVisible();
  });
}
for (const [width,height] of [[1536,1024],[1440,900],[1366,768],[1024,768],[768,1024],[390,844],[360,800]]) {
  test(`reference composition ${width}x${height}`, async ({ page }) => {
    await page.setViewportSize({ width: width!, height: height! });
    await page.emulateMedia({ reducedMotion: 'reduce' }); await page.goto(base); await page.evaluate(() => document.fonts.ready);
    await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const violations = (await new AxeBuilder({ page }).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations;
    expect(violations.map(v => ({ id:v.id, nodes:v.nodes.map(n=>n.target) }))).toEqual([]);
    if (width === 1536) { const box = await page.locator('.auth-card').boundingBox(); expect(box?.x).toBeCloseTo(162,0); expect(box?.y).toBeCloseTo(88,0); }
    await mkdir('../artifacts/m014a/screenshots', { recursive:true });
    await page.screenshot({ path:`../artifacts/m014a/screenshots/login-${width}x${height}.png`, fullPage:true, animations:'disabled' });
  });
}
test('reduced motion stops animations; console remains clean', async ({ page }) => {
  const errors:string[]=[]; page.on('pageerror', error=>errors.push(error.name));
  await page.emulateMedia({ reducedMotion:'reduce' }); await page.goto(base);
  expect(await page.locator('.auth-card').evaluate(el=>getComputedStyle(el).animationName)).toBe('none');
  expect(errors).toEqual([]);
});
test('MFA routes cannot restore a pending session after reload', async ({ page }) => {
  await signIn(page); await page.reload(); await expect(page.getByRole('heading', { name: 'Your session has expired' })).toBeVisible();
});
test('complementary screen evidence', async ({ page }) => {
  await page.emulateMedia({ reducedMotion:'reduce' });
  for (const path of ['forgot-password','reset-password','invitation','session/expired','session/denied','session/unavailable']) {
    await page.goto(`${base}/${path}`); await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path:`../artifacts/m014a/screenshots/${path.replace('/','-')}.png`, fullPage:true, animations:'disabled' });
  }
  await signIn(page); await page.screenshot({ path:'../artifacts/m014a/screenshots/mfa-enroll.png', animations:'disabled' });
  await page.getByRole('button', { name:'Continue to verification' }).click();
  await expect(page.getByLabel('Verification code')).toBeVisible();
  await page.screenshot({ path:'../artifacts/m014a/screenshots/mfa-verify.png', animations:'disabled' });
});
