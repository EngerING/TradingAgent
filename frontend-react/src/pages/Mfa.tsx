import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import { useAuth } from '../auth/context';
import { useOperation } from '../auth/useOperation';
import { Field, Heading, Notice, SubmitButton } from '../components/FormControls';

export function Mfa({ enrollment = false }: { enrollment?: boolean }) {
  const auth = useAuth(); const operation = useOperation(); const navigate = useNavigate();
  const [ready, setReady] = useState(false); const [code, setCode] = useState('');
  useEffect(() => { let active = true; void auth.session().then(result => {
    if (!active) return; if (result.kind === 'mfa-required') setReady(true); else void navigate('/session/expired', { replace: true });
  }); return () => { active = false; }; }, [auth, navigate]);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!/^\d{6}$/.test(code)) { operation.setMessage('Enter the six-digit verification code.'); return; }
    const transient = code; setCode('');
    await operation.run(signal => auth.verify(transient, signal), result => {
      if (result.kind === 'demo-complete') void navigate('/session/complete', { replace: true });
      else if (result.kind === 'expired') void navigate('/session/expired', { replace: true });
      else operation.setMessage('That demonstration code was not accepted. Try 123456.');
    });
  }
  return <><Heading title={enrollment ? 'Set up two-step verification' : 'A little extra security'} subtitle={enrollment ? 'Protect access with an authenticator app.' : 'Enter the code from your authenticator app.'} />
    <p className="support-copy">{enrollment ? 'This preview demonstrates enrollment. It does not create or modify a real TOTP factor.' : 'Use 123456 in this demonstration. No real MFA is verified.'}</p>
    {enrollment ? <><div className="qr-placeholder" role="img" aria-label="Demonstration QR placeholder. Not an enrollable authenticator code."><svg viewBox="0 0 120 120" aria-hidden="true"><path d="M4 4h32v32H4z M84 4h32v32H84z M4 84h32v32H4z" fill="none" stroke="currentColor" strokeWidth="6"/><path d="M13 13h14v14H13z M93 13h14v14H93z M13 93h14v14H13z M48 4h12v12H48z M48 28h24v12H48z M4 48h24v12H4z M40 48h20v24H40z M72 48h44v12H72z M72 72h12v44H72z M96 72h20v12H96z M48 92h12v24H48z M96 96h20v20H96z"/></svg><span>Demo QR · not enrollable</span></div>
      <button type="button" className="primary-button" disabled={!ready || operation.busy} onClick={() => { void operation.run(signal => auth.enroll(signal), result => { if (result.kind === 'demo-enrollment') void navigate('/mfa/verify'); else void navigate('/session/expired'); }); }}>Continue to verification</button></>
      : <form className="secondary-form" onSubmit={event => { void submit(event); }} noValidate><Field label="Verification code" type="text" icon="lock" inputMode="numeric" autoComplete="off" pattern="[0-9]{6}" maxLength={6} placeholder="000000" value={code} onChange={e => setCode(e.target.value.replace(/\D/g, ''))} /><SubmitButton busy={operation.busy || !ready}>Verify code</SubmitButton></form>}
    <Notice text={operation.message} error /><Link className="back-link" to="/">Back to sign in</Link>
  </>;
}
