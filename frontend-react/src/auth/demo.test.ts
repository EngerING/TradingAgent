import { describe, expect, it, vi } from 'vitest';
import { createDemoAdapter } from './demo';

describe('explicit in-memory development authentication', () => {
  it('requires MFA and never returns a real authenticated identity', async () => {
    const auth = createDemoAdapter(0);
    expect(await auth.session()).toEqual({ kind: 'anonymous' });
    expect((await auth.login('demo@tradingagent.test', 'InventedPassword8')).kind).toBe('mfa-required');
    expect((await auth.enroll()).kind).toBe('demo-enrollment');
    expect((await auth.verify('000000')).kind).toBe('invalid-code');
    expect((await auth.verify('123456')).kind).toBe('demo-complete');
    await auth.logout(); expect((await auth.session()).kind).toBe('anonymous');
  });
  it('does not retain credentials, contact a provider or write browser storage', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch'); const set = vi.spyOn(Storage.prototype, 'setItem');
    const auth = createDemoAdapter(0);
    expect((await auth.login('someone@other.invalid', 'InventedPassword8')).kind).toBe('invalid-credentials');
    expect(JSON.stringify(auth)).not.toContain('InventedPassword8');
    expect(fetch).not.toHaveBeenCalled(); expect(set).not.toHaveBeenCalled();
  });
  it('guards MFA and password continuation without a pending flow', async () => {
    const auth = createDemoAdapter(0);
    expect((await auth.verify('123456')).kind).toBe('expired');
    expect((await auth.setPassword('InventedPassword8')).kind).toBe('expired');
  });
  it('allows recovery only as a labelled fixture and consumes its continuation', async () => {
    const auth = createDemoAdapter(0);
    expect((await auth.recover('demo@tradingagent.test')).kind).toBe('demo-recovery');
    expect((await auth.setPassword('InventedPassword8')).kind).toBe('demo-password-set');
    expect((await auth.setPassword('InventedPassword8')).kind).toBe('expired');
  });
  it('cancellation prevents a delayed login from granting a pending fixture', async () => {
    const auth = createDemoAdapter(50); const controller = new AbortController();
    const pending = auth.login('demo@tradingagent.test', 'InventedPassword8', controller.signal);
    controller.abort(); await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect((await auth.session()).kind).toBe('anonymous');
  });
  it('keeps errors closed and distinguishes denied and unavailable fixtures', async () => {
    const auth = createDemoAdapter(0);
    expect(await auth.login('unavailable@tradingagent.test','InventedPassword8')).toEqual({ kind:'unavailable' });
    expect(await auth.login('denied@tradingagent.test','InventedPassword8')).toEqual({ kind:'denied' });
    expect((await auth.session()).kind).toBe('anonymous');
  });
});
