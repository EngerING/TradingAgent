import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { useAuth } from '../auth/context';
import { Heading, Notice } from '../components/FormControls';

/** Preview authentication never authorizes trading or access to financial data. */
export function PasswordPreview() {
  const auth = useAuth(); const navigate = useNavigate();
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState('');
  const lastActivity = useRef(0);

  useEffect(() => {
    if (auth.source !== 'preview') { void navigate('/', { replace: true }); return; }
    let active = true, running = false;
    const check = async () => {
      if (!active || running) return; running = true;
      try {
        const state = await auth.session();
        if (!active) return;
        if (state.kind !== 'preview-complete') { setConfirmed(false); void navigate('/session/expired', { replace: true }); }
        else setConfirmed(true);
      } catch { if (active) { setConfirmed(false); void navigate('/session/unavailable', { replace: true }); } }
      finally { running = false; }
    };
    void check();
    // Polling is read-only and does NOT renew the inactivity deadline on the server.
    const timer = setInterval(() => { void check(); }, 60000);
    return () => { active = false; clearInterval(timer); };
  }, [auth, navigate]);

  useEffect(() => {
    if (!confirmed || auth.source !== 'preview') return;
    let active = true;
    const onHumanActivity = () => {
      const now = Date.now();
      if (now - lastActivity.current < 90000) return;
      lastActivity.current = now;
      void auth.activity?.().then(result => {
        if (!active) return;
        if (result.kind === 'expired') void navigate('/session/expired', { replace: true });
        else if (result.kind !== 'preview-complete' && result.kind !== 'conflict')
          void navigate('/session/unavailable', { replace: true });
      });
    };
    window.addEventListener('pointerdown', onHumanActivity);
    window.addEventListener('keydown', onHumanActivity);
    return () => {
      active = false;
      window.removeEventListener('pointerdown', onHumanActivity);
      window.removeEventListener('keydown', onHumanActivity);
    };
  }, [auth, confirmed, navigate]);

  return <><Heading title={confirmed ? 'TradingAgent development access' : 'Checking access'} subtitle="Password verified by Supabase Auth Dev." />
    {confirmed && <><p className="support-copy">Authenticated for the local read-only preview. The operational TradingAgent dashboard is not connected in this React milestone.</p>
      <p className="support-copy">Session: up to 8 hours, with 30 minutes of inactivity permitted. Supabase access tokens rotate exclusively in the BFF.</p>
      <p className="support-copy">OFFLINE / NO_TRADE. No account balances, orders, financial data, trading permissions or automation.</p></>}
    <button type="button" className="primary-button" onClick={() => {
      void auth.logout().then(() => navigate('/', { replace: true }))
        .catch(() => setError('Sign-out could not be confirmed. Close this tab and stop the local pilot.'));
    }}>Sign out</button><Notice text={error} error />
  </>;
}
