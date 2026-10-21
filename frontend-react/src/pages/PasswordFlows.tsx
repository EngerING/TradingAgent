import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router';
import { useAuth } from '../auth/context';
import { useOperation } from '../auth/useOperation';
import { Field, Heading, Notice, SubmitButton } from '../components/FormControls';

export function ForgotPassword() {
  const auth = useAuth(); const operation = useOperation(); const [email, setEmail] = useState('');
  const [error, setError] = useState(''); const [done, setDone] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError('Enter a valid email address.'); return; }
    setError(''); await operation.run(signal => auth.recover(email, signal), result => {
      if (result.kind === 'demo-recovery') { setDone(true); setEmail(''); }
      else operation.setMessage('Password recovery is not connected. Please contact your administrator.');
    });
  }
  return <><Heading title="Forgot your password?" subtitle="Let’s help you get back to TradingAgent." />
    <form className="secondary-form" noValidate onSubmit={event => { void submit(event); }}><Field label="Email address" type="email" autoComplete="off" disabled={auth.mode === 'unavailable'} placeholder="you@company.com" maxLength={320} value={email} onChange={e => setEmail(e.target.value)} error={error} /><SubmitButton busy={operation.busy} disabled={auth.mode === 'unavailable'}>Send recovery link</SubmitButton></form>
    <Notice text={operation.message} error />
    {done && <div className="flow-result"><Notice text="Recovery demonstration only. No email was sent and no account was changed." /><Link className="outline-button" to="/reset-password">Continue recovery demo</Link></div>}
    <Link className="back-link" to="/">Back to sign in</Link>
  </>;
}

export function PasswordSetup({ invitation = false }: { invitation?: boolean }) {
  const auth = useAuth(); const operation = useOperation(); const [ready, setReady] = useState(!invitation);
  const [password, setPassword] = useState(''); const [confirm, setConfirm] = useState('');
  const [error, setError] = useState(''); const [done, setDone] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password.length < 12 || password !== confirm) { setError('Use at least 12 characters and matching passwords.'); return; }
    const transient = password; setPassword(''); setConfirm(''); setError('');
    await operation.run(signal => auth.setPassword(transient, signal), result => {
      if (result.kind === 'demo-password-set') setDone(true);
      else operation.setMessage(result.kind === 'expired' ? 'This demonstration continuation has expired. Start a new recovery demo.' : 'Secure password setup is not connected. No account has been changed.');
    });
  }
  return <><Heading title={invitation ? 'Your invitation awaits' : 'Set a new password'} subtitle={invitation ? 'A considered start to your TradingAgent workspace.' : 'Choose a strong password for your next chapter.'} />
    <p className="support-copy">{auth.mode === 'demo' ? 'Development demonstration. No real invitation or recovery link is exchanged.' : 'Secure invitation and recovery exchange is not available yet.'}</p>
    {!ready && <button className="primary-button" type="button" disabled={operation.busy || auth.mode === 'unavailable'} onClick={() => { void operation.run(signal => auth.invitation(signal), result => { if (result.kind === 'demo-invitation') setReady(true); else operation.setMessage('Invitation acceptance is not connected.'); }); }}>Start invitation demo</button>}
    {ready && !done && <form className="secondary-form" noValidate onSubmit={event => { void submit(event); }}>
      <Field label="New password" type="password" icon="lock" autoComplete="off" disabled={auth.mode === 'unavailable'} placeholder="At least 12 characters" maxLength={1024} value={password} onChange={e => setPassword(e.target.value)} error={error} />
      <Field label="Confirm password" type="password" icon="lock" autoComplete="off" disabled={auth.mode === 'unavailable'} placeholder="Re-enter your password" maxLength={1024} value={confirm} onChange={e => setConfirm(e.target.value)} />
      <SubmitButton busy={operation.busy} disabled={auth.mode === 'unavailable'}>{invitation ? 'Accept invitation' : 'Set new password'}</SubmitButton>
    </form>}
    <Notice text={operation.message} error />{done && <Notice text="Demonstration complete. No real password or account has been changed." />}
    <Link className="back-link" to="/">Back to sign in</Link>
  </>;
}
