import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router';
import { useAuth } from '../auth/context';
import { Icon, Mark } from './Icons';
import { MarketIllustration } from './MarketIllustration';

export function AuthLayout({ children }: { children: ReactNode }) {
  const location = useLocation(); const auth = useAuth();
  const previousPath = useRef(location.pathname);
  const footer = auth.source === 'local-checks'
    ? 'Local HTTPS checks · OFFLINE / NO_TRADE · Sign-in disabled by server; no hosted requests.'
    : auth.mode === 'bff' && auth.source === 'hosted'
    ? 'Supabase Auth Dev via HTTPS BFF · OFFLINE / NO_TRADE · MFA and SQL authorization required; no financial access.'
    : auth.mode === 'bff'
    ? 'HTTP Auth fixture · OFFLINE / NO_TRADE · Synthetic identity only. BFF and disposable PostgreSQL connected; no financial access.'
    : auth.mode === 'demo'
    ? 'Development demo · OFFLINE / NO_TRADE · No real authentication. Use demo@tradingagent.test and a made-up password.'
    : 'Offline preview · OFFLINE / NO_TRADE · Authentication is unavailable. No BFF is connected.';
  useEffect(() => {
    if (previousPath.current !== location.pathname) document.querySelector<HTMLElement>('.form-panel h1')?.focus({ preventScroll: true });
    previousPath.current = location.pathname;
  }, [location.pathname]);
  return <main className="auth-page">
    <a className="skip-link" href="#auth-content">Skip to sign in</a>
    <div className="auth-card">
      <section className="brand-panel" aria-label="TradingAgent">
        <div className="brand"><Mark /><span>Trading<span>Agent</span></span></div>
        <div className="brand-content"><h2>Intelligent trading<br />for the Forex market</h2>
          <p className="brand-description">Analysis, execution and risk control in one place.</p>
          <ul className="features">
            <li><span className="feature-icon"><Icon name="chart" /></span><div><h3>Real-time market analysis</h3><p>Monitor the market with AI-driven<br className="wide-break" /> insights and validated strategies.</p></div></li>
            <li><span className="feature-icon gold"><Icon name="shield" /></span><div><h3>Advanced risk management</h3><p>Full control of your capital.</p></div></li>
            <li><span className="feature-icon"><Icon name="bolt" /></span><div><h3>Automated execution</h3><p>Trade safely and with discipline.</p></div></li>
          </ul>
        </div>
        <MarketIllustration />
      </section>
      <section id="auth-content" className="form-panel" aria-label="Authentication"><div key={location.pathname} className="route-panel">{children}</div></section>
    </div>
    <footer className="preview-note">{footer}</footer>
  </main>;
}
