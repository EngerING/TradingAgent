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
  return <><div className="state-symbol"><Icon name={state === 'complete' ? 'check' : state === 'denied' ? 'shield' : 'lock'} /></div><Heading title={item.title} subtitle={item.subtitle} />
    <p className="support-copy">OFFLINE / NO_TRADE. Account identity and financial permissions remain separate.</p>
    <button type="button" className="primary-button" onClick={() => { void auth.logout().then(() => navigate('/')); }}>Return to sign in</button>
  </>;
}
export function BlockedCallback() {
  return <><Heading title="Secure link exchange pending" subtitle="Recovery and invitation links need a verified BFF exchange." /><p className="support-copy">The URL parameters have been removed. No link credentials were read, stored or exchanged, and no account was changed.</p><Link className="back-link" to="/">Back to sign in</Link></>;
}
