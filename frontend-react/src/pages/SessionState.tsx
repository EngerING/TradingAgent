import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { useAuth } from '../auth/context';
import { Heading } from '../components/FormControls';
import { Icon } from '../components/Icons';
const states: Record<string, { title: string; subtitle: string }> = {
  expired: { title: 'Your session has expired', subtitle: 'Sign in again to continue securely.' },
  denied: { title: 'Access is restricted', subtitle: 'This workspace is available to invited members with the appropriate permissions.' },
  unavailable: { title: 'We’ll be right back', subtitle: 'Authentication is temporarily unavailable. No account changes have been made.' },
  progress: { title: 'Checking your session', subtitle: 'Authentication in progress. No trading access is granted.' },
  complete: { title: 'Demonstration complete', subtitle: 'No real session has been created. This is a development fixture, with no trading access.' },
};
export function SessionState() {
  const { state = 'expired' } = useParams(); const item = states[state] ?? states.expired!;
  const auth = useAuth(); const navigate = useNavigate();
  const [confirmed, setConfirmed] = useState(false);
  const stop = useRef<() => void>(() => {});
  useEffect(() => {
    if (auth.mode !== 'bff' || state !== 'complete') return;
    let active = true; let checking = false; const controller = new AbortController();
    stop.current = () => { active = false; controller.abort(); };
    const check = () => {
      if (checking || !active) return;
      checking = true;
      void auth.session(controller.signal).then(result => {
        if (!active || result.kind === 'conflict') return;
        if (result.kind === 'complete') setConfirmed(true);
        else void navigate(result.kind === 'unavailable' ? '/session/unavailable' : '/session/expired', { replace: true });
      }).finally(() => { checking = false; });
    };
    check(); const timer = setInterval(check, 5000); const focus = () => check(); window.addEventListener('focus', focus);
    return () => { stop.current(); clearInterval(timer); window.removeEventListener('focus', focus); };
  }, [auth, navigate, state]);
  if (auth.mode === 'bff' && state === 'complete') return <><Heading title={confirmed ? 'Identity authenticated' : 'Checking your session'} subtitle={auth.source === 'hosted' ? 'Supabase Auth Dev via secure BFF; no financial access.' : 'HTTP Auth fixture; secure BFF session; no financial access.'} /><p className="support-copy">OFFLINE / NO_TRADE. Session expires within five minutes, without refresh. Provider session activity is not remotely guaranteed.</p><button type="button" className="primary-button" onClick={() => { stop.current(); setConfirmed(false); void auth.logout().then(() => navigate('/')).catch(() => navigate('/session/unavailable')); }}>Sign out</button></>;
  return <><div className="state-symbol"><Icon name={state === 'complete' ? 'check' : state === 'denied' ? 'shield' : 'lock'} /></div><Heading title={item.title} subtitle={auth.mode === 'bff' && state === 'unavailable' ? 'The result could not be confirmed. No financial access is available; retry sign out when the BFF is reachable.' : item.subtitle} />
    <p className="support-copy">OFFLINE / NO_TRADE. Account identity and financial permissions remain separate.</p>
    <button type="button" className="primary-button" onClick={() => { void auth.logout().then(() => navigate('/')).catch(() => navigate('/session/unavailable')); }}>Return to sign in</button>
  </>;
}
export function BlockedCallback() {
  return <><Heading title="Secure link exchange pending" subtitle="Recovery and invitation links need a verified BFF exchange." /><p className="support-copy">The URL parameters have been removed. No link credentials were read, stored or exchanged, and no account was changed.</p><Link className="back-link" to="/">Back to sign in</Link></>;
}
