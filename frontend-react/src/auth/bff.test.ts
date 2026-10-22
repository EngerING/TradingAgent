import { afterEach, describe, expect, it, vi } from 'vitest';
import { BffAuthAdapter, configuredBff } from './bff';
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const csrf = () => json({ token: 'public-fixture-csrf' });
const id = '55555555-5555-4555-8555-555555555555';
afterEach(() => vi.unstubAllGlobals());
describe('BFF transport boundary', () => {
  it('uses same-origin cookies CSRF and never accepts a partial login', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(csrf()).mockResolvedValueOnce(json({ status: 'MFA_REQUIRED' })); vi.stubGlobal('fetch', fetcher);
    expect((await new BffAuthAdapter().login('fixture@example.test', 'public-fixture')).kind).toBe('unavailable');
    expect(fetcher.mock.calls[1]?.[1]).toMatchObject({ credentials: 'same-origin', redirect: 'error', method: 'POST', headers: { 'X-CSRF-TOKEN': 'public-fixture-csrf' } });
  });
  it.each([[401, 'invalid-credentials'], [403, 'denied'], [409, 'conflict'], [429, 'rate-limited'], [503, 'unavailable']])('normalizes HTTP %i', async (status, kind) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(csrf()).mockResolvedValueOnce(json({ code: 'PRIVATE_ERROR' }, status)));
    expect(await new BffAuthAdapter().login('fixture@example.test', 'public-fixture')).toEqual({ kind });
  });
  it('blocks orphan enrollment without POST enrollment or DELETE', async () => {
    const f = vi.fn().mockResolvedValueOnce(csrf()).mockResolvedValueOnce(json({ status: 'MFA_REQUIRED', factors: [{ id, verified: false }], executionAuthorized: false })); vi.stubGlobal('fetch', f);
    expect((await new BffAuthAdapter().login('fixture@example.test', 'public-fixture')).kind).toBe('conflict'); expect(f).toHaveBeenCalledTimes(2);
  });
  it('does not confuse HTTP success with an authenticated session', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ authenticated: true, aal: 'aal1' })));
    expect((await new BffAuthAdapter().session()).kind).toBe('unavailable');
  });
  it('blocks recovery and invitation without network', async () => {
    const f = vi.fn(); vi.stubGlobal('fetch', f); const adapter = new BffAuthAdapter();
    expect(await adapter.recover('fixture@example.test')).toEqual({ kind: 'unavailable' }); expect(await adapter.invitation()).toEqual({ kind: 'unavailable' }); expect(f).not.toHaveBeenCalled();
  });
  it('blocks duplicate transport while a request is pending', async () => {
    let release!: (r: Response) => void; const f = vi.fn().mockReturnValue(new Promise<Response>(resolve => { release = resolve; })); vi.stubGlobal('fetch', f);
    const adapter = new BffAuthAdapter(); const first = adapter.login('fixture@example.test', 'public-fixture');
    expect(await adapter.login('fixture@example.test', 'public-fixture')).toEqual({ kind: 'conflict' }); expect(f).toHaveBeenCalledTimes(1);
    release(json({}, 503)); expect(await first).toEqual({ kind: 'unavailable' });
  });
  it('rejects non JSON rather than rendering an upstream error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<svg onload=attack()>PRIVATE</svg>')));
    expect(await new BffAuthAdapter().login('fixture@example.test', 'public-fixture')).toEqual({ kind: 'unavailable' });
  });
  it('cancelled requests cannot leave a preliminary authenticated state', async () => {
    const controller = new AbortController(); controller.abort(); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(csrf()));
    const adapter = new BffAuthAdapter(); expect(await adapter.login('fixture@example.test', 'public-fixture', controller.signal)).toEqual({ kind: 'unavailable' });
  });
  it('rejects oversized request bodies before transmitting credentials', async () => {
    const f = vi.fn().mockResolvedValue(csrf()); vi.stubGlobal('fetch', f);
    expect(await new BffAuthAdapter().login('fixture@example.test', 'x'.repeat(5000))).toEqual({ kind: 'unavailable' }); expect(f).toHaveBeenCalledTimes(1);
  });
  it('rejects oversized responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ token: 'x'.repeat(20000) })));
    expect((await new BffAuthAdapter().login('fixture@example.test', 'public-fixture')).kind).toBe('unavailable');
    // Hosted profile is accepted only on its exact HTTPS loopback origin.
    const response = () => json({ profile: 'HOSTED_DEVELOPMENT_AUTH', mode: 'OFFLINE', decision: 'NO_TRADE', executionAuthorized: false });
    vi.stubGlobal('location', { protocol: 'https:', hostname: '127.0.0.1', search: '', hash: '' });
    const hostedFetch = vi.fn().mockImplementation(async () => response());
    vi.stubGlobal('fetch', hostedFetch);
    const hosted = await configuredBff();
    expect(hosted?.mode).toBe('bff');
    expect(hosted?.source).toBe('hosted');
    expect(hostedFetch).toHaveBeenCalledTimes(1);
    vi.stubGlobal('location', { protocol: 'https:', hostname: 'localhost', search: '', hash: '' });
    expect(await configuredBff()).toBeUndefined();
    vi.stubGlobal('location', { protocol: 'http:', hostname: '127.0.0.1', search: '', hash: '' });
    expect(await configuredBff()).toBeUndefined();
    vi.stubGlobal('location', { protocol: 'https:', hostname: '127.0.0.1', search: '?token=blocked', hash: '' });
    expect(await configuredBff()).toBeUndefined();
    vi.stubGlobal('location', { protocol: 'https:', hostname: '127.0.0.1', search: '', hash: '' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ profile: 'HOSTED_DEVELOPMENT_AUTH', mode: 'OFFLINE', decision: 'NO_TRADE', executionAuthorized: true })));
    expect(await configuredBff()).toBeUndefined();
    // Local checks must disable the form and must never make a login request.
    const localFetch = vi.fn().mockResolvedValue(json({
      profile: 'HOSTED_LOCAL_CHECKS_ONLY', mode: 'OFFLINE', decision: 'NO_TRADE', executionAuthorized: false,
    }));
    vi.stubGlobal('fetch', localFetch);
    const localOnly = await configuredBff();
    expect(localOnly?.mode).toBe('unavailable');
    expect(localOnly?.source).toBe('local-checks');
    expect(await localOnly?.login('fixture@example.test', 'public-fixture')).toEqual({ kind: 'unavailable' });
    expect(localFetch).toHaveBeenCalledTimes(1);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ profile: 'HOSTED_LOCAL_CHECKS_ONLY', mode: 'OFFLINE', decision: 'NO_TRADE', executionAuthorized: true })));
    expect(await configuredBff()).toBeUndefined();
  });
});
