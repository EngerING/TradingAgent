import { useState } from 'react';
import { useNavigate } from 'react-router';
import { useAuth } from '../auth/context';
import { Heading, Notice } from '../components/FormControls';

/** A valid password and JWT are not an MFA session. No factor mutation is possible here. */
export function MfaRecovery() {
  const auth = useAuth(); const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  return <>
    <Heading title="MFA setup needs review" subtitle="Your password was accepted, but a TOTP factor remains unverified." />
    <p className="support-copy">No factor was deleted or replaced. Since the original enrollment QR is unavailable, TradingAgent cannot safely generate a new one while that factor exists. No authenticator code is expected on this screen.</p>
    <p className="support-copy">A verified administrator must first confirm the exact user and the incomplete factor. Removal or recovery requires a separate, specific approval. After the factor is cleared, a new login may enroll TOTP only with local enrollment approval.</p>
    <p className="support-copy">This page grants no session, permissions, or trading access. OFFLINE / NO_TRADE.</p>
    <button type="button" className="primary-button" disabled={busy} onClick={() => {
      setBusy(true); void auth.logout().then(() => navigate('/', { replace: true }))
        .catch(() => { setMessage('Sign-out could not be confirmed. Close this tab and stop the pilot.'); })
        .finally(() => setBusy(false));
    }}>Sign out safely</button>
    <Notice text={message} error />
  </>;
}
