import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import { useAuth } from '../auth/context';
import { useOperation } from '../auth/useOperation';
import { Field, Heading, Notice, SubmitButton } from '../components/FormControls';
import { GoogleMark, Icon } from '../components/Icons';

export function Login() {
  const auth = useAuth(); const navigate = useNavigate(); const operation = useOperation();
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [attempted, setAttempted] = useState(false); const [info, setInfo] = useState('');
  const emailError = attempted && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? 'Enter a valid email address.' : '';
  const passwordError = attempted && password.length === 0 ? 'Enter your password.' : '';
  async function submit(event: FormEvent) {
    event.preventDefault(); setAttempted(true); setInfo('');
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || !password) return;
    const transient = password; setPassword(''); setAttempted(false);
    await operation.run(signal => auth.login(email.trim(), transient, signal), result => {
      if (result.kind === 'mfa-required') void navigate('/mfa/enroll');
      else if (result.kind === 'mfa-recovery-required') void navigate('/mfa/recovery');
      else if (result.kind === 'denied') void navigate('/session/denied');
      else if (result.kind === 'unavailable') void navigate('/session/unavailable');
      else operation.setMessage(auth.mode === 'demo' ? 'Unable to sign in. Check the demonstration credentials and try again.' : result.kind === 'conflict' ? 'An incomplete or ambiguous MFA enrollment requires manual review. No factor was deleted.' : result.kind === 'rate-limited' ? 'Too many attempts. Wait before trying again.' : 'Unable to sign in. Check your credentials and try again.');
    });
  }
  return <><Heading title="Welcome back" subtitle="Sign in to continue on TradingAgent" />
    <form className="login-form" noValidate onSubmit={event => { void submit(event); }}>
      <Field label="Email address" name="email" type="email" autoComplete="off" disabled={auth.mode === 'unavailable'} maxLength={320} placeholder="you@company.com" value={email} onChange={event => setEmail(event.target.value)} error={emailError} />
      <Field label="Password" name="password" type="password" icon="lock" autoComplete="off" disabled={auth.mode === 'unavailable'} maxLength={1024} placeholder="Enter your password" value={password} onChange={event => setPassword(event.target.value)} error={passwordError} />
      <div className="login-options"><label className="remember" title="Persistent login is not available"><input type="checkbox" disabled aria-describedby="remember-note" />Remember me</label><span id="remember-note" className="sr-only">Unavailable. Sessions are never extended or saved by this preview.</span><Link to="/forgot-password">Forgot your password?</Link></div>
      <fieldset className="environment"><legend>Trading environment <button type="button" className="info-button" aria-label="Trading environment information" onClick={() => setInfo('Paper is a visual preference only. Live Trading is unavailable. Neither authorizes financial operations.')}><Icon name="info" /></button></legend>
        <div className="environment-options" role="radiogroup" aria-label="Trading preference"><button type="button" className="environment-choice selected" role="radio" aria-checked="true" aria-label="Paper Trading, visual preference only" onClick={() => setInfo('Paper preference selected. No trading capability is enabled.')}><span className="radio-dot" /><span>Paper Trading<small>Risk-free simulation</small></span></button><button type="button" className="environment-choice" disabled aria-describedby="live-note"><span className="radio-dot" /><span>Live Trading<small>Real money</small></span></button></div>
        <span id="live-note" className="sr-only">Live Trading is unavailable.</span>
      </fieldset>
      <SubmitButton busy={operation.busy} disabled={auth.mode === 'unavailable'}>Sign in</SubmitButton>
      <Notice text={operation.message} error />
    </form>
    <div className="separator"><span>or</span></div>
    <button className="google-button" type="button" disabled aria-describedby="google-note"><GoogleMark />Continue with Google</button>
    <span id="google-note" className="sr-only">Google sign-in is not configured and is unavailable.</span>
    <p className="register">Don’t have an account? <button type="button" className="text-button" onClick={() => setInfo('Access is by invitation only. Public registration is disabled.')}>Register</button></p>
    <Notice text={info} />
  </>;
}
