import { bffRoutes, unavailableAdapter } from './contracts';
import type { AuthAdapter, AuthKind, AuthResult } from './contracts';
const uuid = (s: unknown): s is string => typeof s === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s);
const record = (v: unknown): Record<string, unknown> => { if (!v || typeof v !== 'object' || Array.isArray(v)) throw new Error('CONTRACT'); return v as Record<string, unknown>; };
const keys = (v: Record<string, unknown>, expected: string[]) => { if (Object.keys(v).sort().join() !== expected.sort().join()) throw new Error('CONTRACT'); };
const future = (v: unknown): v is string => typeof v === 'string' && Number.isFinite(Date.parse(v)) && Date.parse(v) > Date.now() && Date.parse(v) <= Date.now() + 301000;
const boundedPreviewTime = (v: unknown, milliseconds: number): v is string =>
  typeof v === 'string' && Number.isFinite(Date.parse(v)) &&
  Date.parse(v) > Date.now() && Date.parse(v) <= Date.now() + milliseconds + 60000;
class Rejected extends Error { constructor(readonly kind: AuthKind) { super('AUTH_REQUEST_REJECTED'); } }

/** Browser owns neither provider tokens nor session references. No retries or fallback transport. */
export class BffAuthAdapter implements AuthAdapter {
  readonly mode = 'bff' as const;
  constructor(readonly source: 'synthetic' | 'hosted' | 'preview' = 'synthetic') {}
  private pendingUntil = 0;
  private factor: string | undefined;
  private epoch = 0;
  private active: AbortController | undefined;
  private clear() { this.pendingUntil = 0; this.factor = undefined; }
  private previewPayload(body: Record<string, unknown>, login: boolean): boolean {
    keys(body, login
      ? ['status','authenticated','aal','profile','expiresAt','idleExpiresAt','renewable','executionAuthorized','mode','decision']
      : ['authenticated','aal','profile','expiresAt','idleExpiresAt','renewable','executionAuthorized','mode','decision']);
    return (!login || body.status === 'PASSWORD_PREVIEW') &&
      body.authenticated === true && body.aal === 'aal1' && body.profile === 'PASSWORD_ONLY_DEV_PREVIEW' &&
      boundedPreviewTime(body.expiresAt, 8 * 60 * 60 * 1000) &&
      boundedPreviewTime(body.idleExpiresAt, 30 * 60 * 1000) &&
      Date.parse(body.idleExpiresAt as string) <= Date.parse(body.expiresAt as string) &&
      body.renewable === true && body.executionAuthorized === false &&
      body.mode === 'OFFLINE' && body.decision === 'NO_TRADE';
  }
  private async request(path: string, body: unknown | undefined, signal: AbortSignal): Promise<Record<string, unknown>> {
    const options: RequestInit = { credentials: 'same-origin', cache: 'no-store', redirect: 'error', referrerPolicy: 'no-referrer', signal };
    if (body !== undefined) {
      const csrf = await this.request(bffRoutes.csrf, undefined, signal); keys(csrf, ['token']);
      if (typeof csrf.token !== 'string' || csrf.token.length < 8 || csrf.token.length > 4096) throw new Error('CONTRACT');
      const encoded = JSON.stringify(body); if (new TextEncoder().encode(encoded).length > 4096) throw new Error('REQUEST_LIMIT');
      options.method = 'POST'; options.headers = { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': csrf.token }; options.body = encoded;
    }
    const response = await fetch(path, options);
    if (!response.ok) { await response.body?.cancel(); throw new Rejected(response.status === 401 ? 'expired' : response.status === 403 ? 'denied' : response.status === 409 ? 'conflict' : response.status === 429 ? 'rate-limited' : 'unavailable'); }
    if (response.status === 204) return {};
    if (!response.headers.get('Content-Type')?.toLowerCase().startsWith('application/json')) { await response.body?.cancel(); throw new Error('CONTRACT'); }
    const reader = response.body?.getReader(); if (!reader) throw new Error('CONTRACT');
    const decoder = new TextDecoder('utf-8', { fatal: true }); let text = ''; let size = 0;
    try { while (true) { const chunk = await reader.read(); if (chunk.done) break; size += chunk.value.byteLength; if (size > 16384) throw new Error('RESPONSE_LIMIT'); text += decoder.decode(chunk.value, { stream: true }); } text += decoder.decode(); }
    finally { await reader.cancel(); reader.releaseLock(); }
    signal.throwIfAborted(); return record(JSON.parse(text));
  }
  private async operation(action: (signal: AbortSignal) => Promise<AuthResult>, outer?: AbortSignal): Promise<AuthResult> {
    if (this.active) return { kind: 'conflict' };
    const controller = new AbortController(); this.active = controller; const epoch = this.epoch;
    const cancel = () => controller.abort(); outer?.addEventListener('abort', cancel, { once: true }); if (outer?.aborted) cancel();
    const timeout = setTimeout(cancel, 10000);
    try { const result = await action(controller.signal); if (controller.signal.aborted || epoch !== this.epoch) throw new Error('CANCELLED'); return result; }
    catch (error) { if (epoch === this.epoch) this.clear(); return { kind: error instanceof Rejected ? error.kind : 'unavailable' }; }
    finally { clearTimeout(timeout); outer?.removeEventListener('abort', cancel); if (this.active === controller) this.active = undefined; }
  }
  async login(email: string, password: string, signal?: AbortSignal): Promise<AuthResult> {
    return this.operation(async s => {
      this.clear(); let body;
      if (this.source === 'preview') {
        try { body = await this.request(bffRoutes.previewLogin, { email, password }, s); }
        catch (e) { if (e instanceof Rejected && e.kind === 'expired') return { kind: 'invalid-credentials' }; throw e; }
        if (!this.previewPayload(body, true)) throw new Error('CONTRACT');
        return { kind: 'preview-complete' };
      }
      try { body = await this.request(bffRoutes.login, { email, password }, s); }
      catch (e) { if (e instanceof Rejected && e.kind === 'expired') return { kind: 'invalid-credentials' }; throw e; }
      keys(body, ['status', 'factors', 'executionAuthorized']);
      if (body.status !== 'MFA_REQUIRED' || body.executionAuthorized !== false || !Array.isArray(body.factors) || body.factors.length > 10) throw new Error('CONTRACT');
      const factors = body.factors.map(v => { const f = record(v); keys(f, ['id', 'verified']); if (!uuid(f.id) || typeof f.verified !== 'boolean') throw new Error('CONTRACT'); return { id: f.id, verified: f.verified }; });
      if (factors.length === 1 && !factors[0]!.verified) return { kind: 'mfa-recovery-required' }; // No silent removal, replacement or challenge.
      if (factors.length > 1) return { kind: 'conflict' };
      this.factor = factors[0]?.id; this.pendingUntil = Date.now() + 300000; return { kind: 'mfa-required' };
    }, signal);
  }
  async session(signal?: AbortSignal): Promise<AuthResult> {
    if (this.source === 'preview') return this.operation(async s => {
      const response = await this.request(bffRoutes.previewSession, undefined, s);
      if (!this.previewPayload(response, false)) throw new Error('CONTRACT');
      return { kind: 'preview-complete' };
    }, signal);
    if (this.pendingUntil > Date.now()) return { kind: 'mfa-required' };
    return this.operation(async signal => {
      const b = await this.request(bffRoutes.session, undefined, signal);
      keys(b, ['authenticated', 'aal', 'expiresAt', 'renewable', 'providerSessionConfirmedActive', 'executionAuthorized', 'mode', 'decision']);
      if (b.authenticated !== true || b.aal !== 'aal2' || !future(b.expiresAt) || b.renewable !== false || b.providerSessionConfirmedActive !== false || b.executionAuthorized !== false || b.mode !== 'OFFLINE' || b.decision !== 'NO_TRADE') throw new Error('CONTRACT');
      return { kind: 'complete' };
    }, signal);
  }
  async activity(signal?: AbortSignal): Promise<AuthResult> {
    if (this.source !== 'preview') return { kind: 'unavailable' };
    return this.operation(async s => {
      const b = await this.request(bffRoutes.previewActivity, {}, s);
      if (!this.previewPayload(b, false)) throw new Error('CONTRACT');
      return { kind: 'preview-complete' };
    }, signal);
  }
  async enroll(signal?: AbortSignal): Promise<AuthResult> {
    if (this.source === 'preview') return { kind: 'unavailable' };
    return this.operation(async s => {
      if (this.pendingUntil <= Date.now()) return { kind: 'expired' };
      if (this.factor) return { kind: 'mfa-required' };
      const b = await this.request(bffRoutes.enroll, {}, s); keys(b, ['factorId', 'secret', 'uri']);
      if (!uuid(b.factorId) || typeof b.secret !== 'string' || !/^[A-Z2-7]{16,256}$/.test(b.secret) || typeof b.uri !== 'string' || b.uri.length > 2048) throw new Error('CONTRACT');
      const uri = new URL(b.uri);
      if (uri.href.length > 1024 || uri.protocol !== 'otpauth:' || uri.hostname !== 'totp' || uri.username || uri.password || uri.hash || uri.searchParams.getAll('secret').length !== 1 || uri.searchParams.get('secret') !== b.secret) throw new Error('CONTRACT');
      this.factor = b.factorId; return { kind: 'enrollment', enrollment: { secret: b.secret, uri: uri.href } };
    }, signal);
  }
  async verify(code: string, signal?: AbortSignal): Promise<AuthResult> {
    if (this.source === 'preview') return { kind: 'unavailable' };
    const result = await this.operation(async s => {
      if (!this.factor || this.pendingUntil <= Date.now()) return { kind: 'expired' };
      if (!/^[0-9]{6}$/.test(code)) return { kind: 'invalid-code' };
      // Each submission obtains a fresh, single-use challenge. No automatic retry.
      const challenge = await this.request(bffRoutes.challenge, { factorId: this.factor }, s); keys(challenge, ['id', 'expiresAt']);
      if (!uuid(challenge.id) || !future(challenge.expiresAt)) throw new Error('CONTRACT');
      try {
        const b = await this.request(bffRoutes.verify, { challengeId: challenge.id, code }, s); keys(b, ['status', 'expiresAt', 'renewable', 'executionAuthorized']);
        if (b.status !== 'SIGNED_IN' || !future(b.expiresAt) || b.renewable !== false || b.executionAuthorized !== false) throw new Error('CONTRACT');
      } catch (e) { if (e instanceof Rejected && e.kind === 'expired') return { kind: 'invalid-code' }; throw e; }
      this.clear(); return { kind: 'mfa-required' }; // Success still requires an independent BFF session read.
    }, signal);
    return result.kind === 'mfa-required' ? this.session() : result;
  }
  recover(email: string, signal?: AbortSignal): Promise<AuthResult> { void email; void signal; return Promise.resolve({ kind: 'unavailable' }); }
  invitation(signal?: AbortSignal): Promise<AuthResult> { void signal; return Promise.resolve({ kind: 'unavailable' }); }
  setPassword(password: string, signal?: AbortSignal): Promise<AuthResult> { void password; void signal; return Promise.resolve({ kind: 'unavailable' }); }
  async logout(): Promise<void> {
    this.epoch++; this.active?.abort(); this.active = undefined; this.clear();
    const result = await this.operation(async signal => { await this.request(this.source === 'preview' ? bffRoutes.previewLogout : bffRoutes.logout, {}, signal); return { kind: 'anonymous' }; });
    if (result.kind !== 'anonymous') throw new Error('LOGOUT_UNCONFIRMED');
  }
}

export async function configuredBff(): Promise<AuthAdapter | undefined> {
  if (location.protocol !== 'https:' || !['localhost', '127.0.0.1'].includes(location.hostname) || location.search || location.hash) return undefined;
  const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 3000);
  try {
    const response = await fetch('/bff/config', { credentials: 'same-origin', redirect: 'error', cache: 'no-store', signal: controller.signal });
    if (!response.ok || !response.headers.get('Content-Type')?.startsWith('application/json') || Number(response.headers.get('Content-Length')) > 1024) return undefined;
    // Configuration response is fixed and tiny; transport data uses the streaming bound above.
    const reader = response.body?.getReader(); if (!reader) return undefined;
    let text = ''; let size = 0; const decoder = new TextDecoder('utf-8', { fatal: true });
    try { while (true) { const chunk = await reader.read(); if (chunk.done) break; size += chunk.value.byteLength; if (size > 1024) return undefined; text += decoder.decode(chunk.value, { stream: true }); } text += decoder.decode(); }
    finally { await reader.cancel(); reader.releaseLock(); }
    controller.signal.throwIfAborted();
    const b = record(JSON.parse(text)); keys(b, ['profile', 'mode', 'decision', 'executionAuthorized']);
    if (b.mode !== 'OFFLINE' || b.decision !== 'NO_TRADE' || b.executionAuthorized !== false) return undefined;
    if (b.profile === 'SYNTHETIC_HTTP_FIXTURE' && location.hostname === 'localhost') return new BffAuthAdapter('synthetic');
    if (b.profile === 'HOSTED_LOCAL_CHECKS_ONLY' && location.hostname === '127.0.0.1') return { ...unavailableAdapter, source: 'local-checks' };
    if (b.profile === 'HOSTED_DEVELOPMENT_AUTH' && location.hostname === '127.0.0.1') return new BffAuthAdapter('hosted');
    if (b.profile === 'HOSTED_PASSWORD_ONLY_PREVIEW' && location.hostname === '127.0.0.1') return new BffAuthAdapter('preview');
  } catch { /* Fail closed. Never select demo on a transport error. */ }
  finally { clearTimeout(timeout); }
  return undefined;
}
