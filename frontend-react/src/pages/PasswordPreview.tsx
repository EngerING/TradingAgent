import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { useAuth } from '../auth/context';
import { Heading, Notice } from '../components/FormControls';

/** AAL1 session for local development only: never a trading capability. */
export function PasswordPreview() {
  const auth = useAuth(); const navigate = useNavigate();
  const [confirmed, setConfirmed] = useState(false); const [error, setError] = useState('');
  const lastActivityReport = useRef(0); const signingOut = useRef(false);
  useEffect(() => {
    if (auth.source !== 'preview') { void navigate('/', { replace: true }); return; }
    let active = true; let running = false;
    const expired = (kind: string) => {
      if (!active) return;
      if (kind === 'expired') void navigate('/session/expired', { replace: true });
      else if (kind !== 'conflict') void navigate('/session/unavailable', { replace: true });
    };
    const check = async () => {
      if (!active || running || signingOut.current) return; running = true;
      try {
        const state = await auth.session();
        if (!active || signingOut.current) return;
        if (state.kind !== 'preview-complete') { setConfirmed(false); expired(state.kind); }
        else setConfirmed(true);
      } catch { if (active) { setConfirmed(false); expired('unavailable'); } }
      finally { running = false; }
    };
    const activity = () => {
      if (!active || signingOut.current || !document.hasFocus() || document.visibilityState !== 'visible') return;
      const now = Date.now(); if (now - lastActivityReport.current < 60000) return;
      lastActivityReport.current = now;
      void auth.activity?.().then(result => {
        if (result.kind !== 'preview-complete' && result.kind !== 'conflict') expired(result.kind);
      }).catch(() => expired('unavailable'));
    };
    void check();
    // Passive verification checks do not extend the server-side inactivity deadline.
    const timer = setInterval(() => { void check(); }, 60000);
    window.addEventListener('focus', check);
    document.addEventListener('pointerdown', activity);
    document.addEventListener('keydown', activity);
    return () => {
      active = false; clearInterval(timer); window.removeEventListener('focus', check);
      document.removeEventListener('pointerdown', activity); document.removeEventListener('keydown', activity);
    };
  }, [auth, navigate]);
  return <><Heading title={confirmed ? 'TradingAgent development access' : 'Checking access'} subtitle="Password verified by Supabase Auth Dev." />
    {confirmed && <><p className="support-copy">Authenticated for the local read-only preview. The operational TradingAgent dashboard is not connected in this React milestone.</p>
      <p className="support-copy">Session: up to 8 hours; 30 minutes without activity. Token renewal happens only on the server. A tab left open does not reset inactivity.</p>
      <p className="support-copy">OFFLINE / NO_TRADE. No account balances, orders, financial data, trading permissions or automation.</p></>}
    <button type="button" className="primary-button" onClick={() => {
      signingOut.current = true;
      void auth.logout().then(() => navigate('/', { replace: true }))
        .catch(() => setError('Sign-out could not be confirmed. Close this tab and stop the local pilot.'));
    }}>Sign out</button><Notice text={error} error />
  </>;
}
