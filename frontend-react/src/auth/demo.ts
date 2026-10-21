import type { AuthAdapter, AuthResult } from './contracts';

// This module is imported only in Vite DEV. No cookie, storage, network or real identity.
export function createDemoAdapter(latency = 450): AuthAdapter {
  let state: 'anonymous' | 'pending' | 'complete' = 'anonymous';
  let continuation: 'recovery' | 'invitation' | null = null;
  async function pause(signal?: AbortSignal) {
    signal?.throwIfAborted();
    await new Promise<void>((resolve, reject) => {
      const done = () => { signal?.removeEventListener('abort', cancel); resolve(); };
      const timer = setTimeout(done, latency);
      const cancel = () => { clearTimeout(timer); reject(new DOMException('Cancelled', 'AbortError')); };
      signal?.addEventListener('abort', cancel, { once: true });
    });
    signal?.throwIfAborted();
  }
  return {
    mode: 'demo',
    async login(email, password, signal): Promise<AuthResult> {
      await pause(signal);
      if (email === 'unavailable@tradingagent.test') return { kind: 'unavailable' };
      if (email === 'denied@tradingagent.test') return { kind: 'denied' };
      if (email !== 'demo@tradingagent.test' || password.length < 8) return { kind: 'invalid-credentials' };
      state = 'pending'; return { kind: 'mfa-required' };
    },
    async session() { return { kind: state === 'pending' ? 'mfa-required' : state === 'complete' ? 'demo-complete' : 'anonymous' }; },
    async enroll(signal) { await pause(signal); return { kind: state === 'pending' ? 'demo-enrollment' : 'expired' }; },
    async verify(code, signal) {
      await pause(signal); if (state !== 'pending') return { kind: 'expired' };
      if (code !== '123456') return { kind: 'invalid-code' };
      state = 'complete'; return { kind: 'demo-complete' };
    },
    async recover(email, signal) { await pause(signal); void email; continuation = 'recovery'; return { kind: 'demo-recovery' }; },
    async invitation(signal) { await pause(signal); continuation = 'invitation'; return { kind: 'demo-invitation' }; },
    async setPassword(password, signal) {
      await pause(signal); if (!continuation) return { kind: 'expired' };
      if (password.length < 12) return { kind: 'invalid-credentials' };
      continuation = null; return { kind: 'demo-password-set' };
    },
    async logout() { state = 'anonymous'; continuation = null; },
  };
}
