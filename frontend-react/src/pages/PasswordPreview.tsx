import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { useAuth } from '../auth/context';
import { Heading, Notice } from '../components/FormControls';

/** Development access does not imply operational authorization. */
export function PasswordPreview() {
  const auth = useAuth(); const navigate = useNavigate();
  const [confirmed, setConfirmed] = useState(false); const [error, setError] = useState('');
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
    const timer = setInterval(() => { void check(); }, 5000);
    return () => { active = false; clearInterval(timer); };
  }, [auth, navigate]);
  return <><Heading title={confirmed ? 'TradingAgent development access' : 'Checking access'} subtitle="Password verified by Supabase Auth Dev." />
    {confirmed && <><p className="support-copy">Authenticated for the local read-only preview. The operational TradingAgent dashboard is not connected in this React milestone.</p>
      <p className="support-copy">OFFLINE / NO_TRADE. No account balances, orders, financial data, trading permissions or automation.</p></>}
    <button type="button" className="primary-button" onClick={() => {
      void auth.logout().then(() => navigate('/', { replace: true }))
        .catch(() => setError('Sign-out could not be confirmed. Close this tab and stop the local pilot.'));
    }}>Sign out</button><Notice text={error} error />
  </>;
}
