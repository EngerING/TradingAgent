import { test, expect } from '@playwright/test';
test('production build fails closed and never uses fixture login', async ({ page }) => {
  const outside:string[]=[];
  page.on('request', request => { if (new URL(request.url()).origin !== 'http://localhost:3001') outside.push('NON_LOCAL_REQUEST'); });
  await page.goto('http://localhost:3001');
  await expect(page.getByText(/No BFF is connected/)).toBeVisible();
  await expect(page.getByLabel('Email address')).toBeDisabled();
  await expect(page.getByLabel('Password', { exact:true })).toBeDisabled();
  await expect(page.getByRole('button', { name:'Sign in', exact:true })).toBeDisabled();
  expect(outside).toEqual([]); expect(await page.context().cookies()).toEqual([]);
});
