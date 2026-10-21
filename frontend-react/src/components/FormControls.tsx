import { useId, useState } from 'react';
import type { InputHTMLAttributes } from 'react';
import { Icon } from './Icons';
export function Field({ label, error, icon = 'mail', ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string; icon?: 'mail' | 'lock' }) {
  const id = useId(); const [visible, setVisible] = useState(false); const password = props.type === 'password';
  return <div className="field"><label htmlFor={id}>{label}</label><div className="input-wrap"><Icon name={icon} />
    <input {...props} id={id} type={password && visible ? 'text' : props.type} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined} />
    {password && <button className="password-toggle" type="button" aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible} onClick={() => setVisible(!visible)}><Icon name={visible ? 'eye' : 'eye-off'} /></button>}
  </div>{error && <span className="field-error" id={`${id}-error`}>{error}</span>}</div>;
}
export function SubmitButton({ busy, disabled = false, children }: { busy: boolean; disabled?: boolean; children: string }) {
  return <button type="submit" className="primary-button" disabled={busy || disabled} aria-busy={busy}>{busy ? 'Please wait…' : children}<Icon name="arrow" /></button>;
}
export function Notice({ text, error = false }: { text: string; error?: boolean }) {
  return text ? <p className={`notice ${error ? 'error-notice' : ''}`} role={error ? 'alert' : 'status'}>{text}</p> : null;
}
export function Heading({ title, subtitle }: { title: string; subtitle: string }) {
  return <header className="form-heading"><h1 tabIndex={-1}>{title}</h1><p>{subtitle}</p></header>;
}
