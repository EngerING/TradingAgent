import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { useAuth } from '../auth/context';
import { ReadOnlyDashboard } from '../dashboard/ReadOnlyDashboard';

/** AAL1 session for local development only: never a trading capability. */
export function PasswordPreview() {
  const auth = useAuth(); const navigate = useNavigate();
  const [confirmed, setConfirmed] = useState(false); const [error, setError] = useState('');
  const lastActivityReport = useRef(0); const signingOut = useRef(false);
  useEffect(() => {
    if (auth.source !== 'preview') { void navigate('/', { replace: true }); return; }
    let active = true; let running = false; let confirmedDeadline = 0;
    let deadlineRoute = '/session/expired';
    let deadlineTimer: ReturnType<typeof setTimeout> | undefined;
    const leave = (path: string) => {
      if (!active) return;
      active = false; setConfirmed(false);
      if (deadlineTimer) clearTimeout(deadlineTimer);
      void navigate(path, { replace: true });
    };
    const expired = (kind: string) => {
      if (kind === 'conflict') return;
      // The BFF owns authorization. A previously verified deadline can only
      // DENY browser display, never extend or create an authenticated session.
      if (confirmedDeadline && Date.now() >= confirmedDeadline) leave(deadlineRoute);
      else leave(kind === 'expired' ? '/session/expired' : '/session/unavailable');
    };
    const rememberDeadline = (result: Awaited<ReturnType<typeof auth.session>>) => {
      const absolute = Date.parse(result.expiresAt ?? '');
      const idle = Date.parse(result.idleExpiresAt ?? '');
      if (!Number.isFinite(absolute) || !Number.isFinite(idle)) return;
      confirmedDeadline = Math.min(absolute, idle);
      deadlineRoute = idle < absolute ? '/session/idle' : '/session/expired';
      if (deadlineTimer) clearTimeout(deadlineTimer);
      if (confirmedDeadline <= Date.now()) { leave(deadlineRoute); return; }
      deadlineTimer = setTimeout(() => leave(deadlineRoute), confirmedDeadline - Date.now());
    };
    const check = async () => {
      if (!active || running || signingOut.current) return;
      if (confirmedDeadline && Date.now() >= confirmedDeadline) { leave(deadlineRoute); return; }
      running = true;
      try {
        const state = await auth.session();
        if (!active || signingOut.current) return;
        if (state.kind !== 'preview-complete') expired(state.kind);
        else { rememberDeadline(state); if (active) setConfirmed(true); }
      } catch { if (active) { setConfirmed(false); expired('unavailable'); } }
      finally { running = false; }
    };
    const activity = () => {
      if (!active || signingOut.current || !document.hasFocus() || document.visibilityState !== 'visible') return;
      const now = Date.now(); if (now - lastActivityReport.current < 60000) return;
      lastActivityReport.current = now;
      void auth.activity?.().then(result => {
        if (!active) return;
        if (result.kind === 'preview-complete') rememberDeadline(result);
        else expired(result.kind);
      }).catch(() => expired('unavailable'));
    };
    void check();
    // Passive verification checks do not extend the server-side inactivity deadline.
    const timer = setInterval(() => { void check(); }, 60000);
    window.addEventListener('focus', check);
    document.addEventListener('pointerdown', activity);
    document.addEventListener('keydown', activity);
    return () => {
      active = false; clearInterval(timer); if (deadlineTimer) clearTimeout(deadlineTimer);
      window.removeEventListener('focus', check);
      document.removeEventListener('pointerdown', activity); document.removeEventListener('keydown', activity);
    };
  }, [auth, navigate]);
  return <ReadOnlyDashboard ready={confirmed} error={error} onSignOut={() => {
      signingOut.current = true;
      void auth.logout().then(() => navigate('/', { replace: true }))
        .catch(() => setError('Sign-out could not be confirmed. Close this tab and stop the local pilot.'));
    }} />;
}
