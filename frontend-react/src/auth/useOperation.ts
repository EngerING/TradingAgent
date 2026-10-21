import { useEffect, useRef, useState } from 'react';
import type { AuthResult } from './contracts';
export function useOperation() {
  const controller = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => () => controller.current?.abort(), []);
  async function run(action: (signal: AbortSignal) => Promise<AuthResult>, complete: (result: AuthResult) => void) {
    if (controller.current) return;
    const current = new AbortController(); controller.current = current; setBusy(true); setMessage('');
    try { const result = await action(current.signal); if (!current.signal.aborted) complete(result); }
    catch { if (!current.signal.aborted) setMessage('This service is temporarily unavailable. Please try again later.'); }
    finally { if (!current.signal.aborted) { controller.current = null; setBusy(false); } }
  }
  return { busy, message, setMessage, run };
}
