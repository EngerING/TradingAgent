import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import { useAuth } from '../auth/context';
import { useOperation } from '../auth/useOperation';
import { EnrollmentQr } from '../components/EnrollmentQr';
import { Field, Heading, Notice, SubmitButton } from '../components/FormControls';

export function Mfa({ enrollment = false }: { enrollment?: boolean }) {
  const auth = useAuth(); const operation = useOperation(); const navigate = useNavigate();
  const [enrolled, setEnrolled] = useState<{ secret: string; uri: string } | undefined>();
  const [ready, setReady] = useState(false); const [code, setCode] = useState('');
  useEffect(() => { let active = true; void auth.session().then(result => {
    if (!active) return; if (result.kind === 'mfa-required') setReady(true); else void navigate('/session/expired', { replace: true });
  }); return () => { active = false; }; }, [auth, navigate]);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!/^\d{6}$/.test(code)) { operation.setMessage('Enter the six-digit verification code.'); return; }
    const transient = code; setCode('');
    await operation.run(signal => auth.verify(transient, signal), result => {
      if (result.kind === 'demo-complete' || result.kind === 'complete') void navigate('/session/complete', { replace: true });
      else if (result.kind === 'expired') void navigate('/session/expired', { replace: true });
      else operation.setMessage(auth.mode === 'demo' ? 'That demonstration code was not accepted. Try 123456.' : result.kind === 'invalid-code' ? 'Code rejected. Submit a current code to obtain a new challenge.' : 'Verification unavailable or expired. Return to sign in.');
    });
  }
  if (auth.mode === 'bff') return <><Heading title={enrollment ? 'Set up two-step verification' : 'A little extra security'} subtitle="Secure BFF authentication; no financial access." />
    <p className="support-copy">{enrollment ? 'Continue with your existing verified authenticator, or enroll if no factor exists. Incomplete enrollments require manual review.' : 'Enter a current code. Every submission uses a new challenge.'}</p>
    {enrollment ? <>{enrolled && <><EnrollmentQr uri={enrolled.uri} /><p className="support-copy">Keep this enrollment key private: <code>{enrolled.secret}</code></p></>}
      <button type="button" className="primary-button" disabled={!ready || operation.busy} onClick={() => {
        if (enrolled) { setEnrolled(undefined); void navigate('/mfa/verify'); return; }
        void operation.run(signal => auth.enroll(signal), result => {
          if (result.kind === 'enrollment' && result.enrollment) setEnrolled(result.enrollment);
          else if (result.kind === 'mfa-required') void navigate('/mfa/verify');
          else operation.setMessage('Enrollment blocked. No existing factor was deleted. Return to sign in for manual review.');
        });
      }}>{enrolled ? 'I saved my authenticator; continue' : 'Continue securely'}</button></>
      : <form className="secondary-form" onSubmit={event => { void submit(event); }} noValidate><Field label="Verification code" type="text" icon="lock" inputMode="numeric" autoComplete="off" maxLength={6} placeholder="000000" value={code} onChange={e => setCode(e.target.value.replace(/\D/g, ''))} /><SubmitButton busy={operation.busy || !ready}>Verify code</SubmitButton></form>}
    <Notice text={operation.message} error /><button type="button" className="text-button" onClick={() => { setEnrolled(undefined); setCode(''); void auth.logout().then(() => navigate('/')).catch(() => navigate('/session/unavailable')); }}>Cancel and sign out</button>
  </>;
  return <><Heading title={enrollment ? 'Set up two-step verification' : 'A little extra security'} subtitle={enrollment ? 'Protect access with an authenticator app.' : 'Enter the code from your authenticator app.'} />
    <p className="support-copy">{enrollment ? 'This preview demonstrates enrollment. It does not create or modify a real TOTP factor.' : 'Use 123456 in this demonstration. No real MFA is verified.'}</p>
    {enrollment ? <><div className="qr-placeholder" role="img" aria-label="Demonstration QR placeholder. Not an enrollable authenticator code."><svg viewBox="0 0 120 120" aria-hidden="true"><path d="M4 4h32v32H4z M84 4h32v32H84z M4 84h32v32H4z" fill="none" stroke="currentColor" strokeWidth="6"/><path d="M13 13h14v14H13z M93 13h14v14H93z M13 93h14v14H13z M48 4h12v12H48z M48 28h24v12H48z M4 48h24v12H4z M40 48h20v24H40z M72 48h44v12H72z M72 72h12v44H72z M96 72h20v12H96z M48 92h12v24H48z M96 96h20v20H96z"/></svg><span>Demo QR · not enrollable</span></div>
      <button type="button" className="primary-button" disabled={!ready || operation.busy} onClick={() => { void operation.run(signal => auth.enroll(signal), result => { if (result.kind === 'demo-enrollment') void navigate('/mfa/verify'); else void navigate('/session/expired'); }); }}>Continue to verification</button></>
      : <form className="secondary-form" onSubmit={event => { void submit(event); }} noValidate><Field label="Verification code" type="text" icon="lock" inputMode="numeric" autoComplete="off" pattern="[0-9]{6}" maxLength={6} placeholder="000000" value={code} onChange={e => setCode(e.target.value.replace(/\D/g, ''))} /><SubmitButton busy={operation.busy || !ready}>Verify code</SubmitButton></form>}
    <Notice text={operation.message} error /><Link className="back-link" to="/">Back to sign in</Link>
  </>;
}
