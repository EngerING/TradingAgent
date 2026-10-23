import { useState } from 'react';
import { Icon, Mark } from '../components/Icons';
import './dashboard.css';

type Section = 'overview' | 'session';
const upcoming = [
  { number: 3, label: 'Market Analyst' }, { number: 4, label: 'Kronos / AI' },
  { number: 5, label: 'Strategy Lab' }, { number: 6, label: 'Risk Engine' },
  { number: 7, label: 'Execution Engine' }, { number: 8, label: 'Operations & portfolio' },
  { number: 9, label: 'IBKR & connections' }, { number: 10, label: 'AI Agent' },
  { number: 11, label: 'Monitoring' }, { number: 12, label: 'Configuration & audit' },
] as const;

function Metric({ label, detail }: { label: string; detail: string }) {
  return <div className="dash-metric"><div className="dash-metric-top"><span>{label}</span><span className="dash-metric-symbol"><Icon name="chart" /></span></div>
    <strong aria-label={label + ': no verified data'}>—</strong><small>{detail}</small></div>;
}
function MarketSketch() {
  return <div className="dash-market-sketch" role="img" aria-label="Decorative market illustration, not real prices">
    <svg viewBox="0 0 720 205" preserveAspectRatio="none" aria-hidden="true">
      <defs><linearGradient id="dash-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#5f95c4" stopOpacity=".23" /><stop offset="1" stopColor="#5f95c4" stopOpacity="0" /></linearGradient></defs>
      {[35, 78, 121, 164].map(y => <line key={y} x1="0" x2="720" y1={y} y2={y} stroke="#e8edf2" />)}
      {[90, 180, 270, 360, 450, 540, 630].map(x => <line key={x} y1="0" y2="205" x1={x} x2={x} stroke="#eef1f5" />)}
      <path d="M0 178 C45 160 60 173 103 165 S170 117 218 136 S290 151 332 111 S403 123 446 79 S511 99 551 65 S622 90 665 41 L720 28 L720 205 L0 205Z" fill="url(#dash-fill)" />
      <path d="M0 178 C45 160 60 173 103 165 S170 117 218 136 S290 151 332 111 S403 123 446 79 S511 99 551 65 S622 90 665 41 L720 28" fill="none" stroke="#5689b7" strokeWidth="3" strokeLinecap="round" />
      <circle cx="665" cy="41" r="6" fill="#fff" stroke="#5689b7" strokeWidth="3" />
    </svg><span>ILLUSTRATION ONLY · NO MARKET FEED</span>
  </div>;
}
function Overview() {
  return <div className="dash-stack">
    <section className="dash-hero" aria-labelledby="dash-title"><div><span className="dash-eyebrow">WORKSPACE / DEVELOPMENT PREVIEW</span>
      <h1 id="dash-title">A clearer view of every decision.</h1>
      <p>The TradingAgent workspace is taking shape. Financial accounts, live quotes and trading services are intentionally not connected.</p></div>
      <span className="dash-preview-badge"><Icon name="lock" /> READ-ONLY ACCESS</span></section>
    <section className="dash-metrics" aria-label="Financial data availability">
      <Metric label="Account capital" detail="No verified balance connected" />
      <Metric label="Net P&L" detail="No verified result connected" />
      <Metric label="Open positions" detail="No position feed connected" />
      <Metric label="Active strategies" detail="No strategy feed connected" />
    </section>
    <div className="dash-panels">
      <section className="dash-panel dash-chart" aria-labelledby="dash-chart-title"><div className="dash-panel-header"><div><span className="dash-eyebrow">MARKET OVERVIEW</span><h2 id="dash-chart-title">Price action</h2></div><span className="dash-muted-badge">Illustrative</span></div>
        <MarketSketch /><p className="dash-panel-note">No quotes, candles or historical prices have been fetched. This drawing is decorative.</p></section>
      <section className="dash-panel" aria-labelledby="dash-agent-title"><div className="dash-panel-header"><div><span className="dash-eyebrow">SAFETY FIRST</span><h2 id="dash-agent-title">Agent status</h2></div><span className="dash-light" aria-hidden="true" /></div>
        <dl className="dash-details"><div><dt>Operating mode</dt><dd><code>OFFLINE</code></dd></div><div><dt>Trade decision</dt><dd><code>NO_TRADE</code></dd></div><div><dt>Execution permission</dt><dd>Not granted</dd></div><div><dt>Financial data</dt><dd>Not connected</dd></div></dl>
        <div className="dash-safe"><Icon name="shield" /><p>Permissions and risk limits belong to the protected backend. This view cannot place or approve orders.</p></div></section>
    </div>
    <div className="dash-panels">
      <section className="dash-panel" aria-labelledby="dash-stream-title"><div className="dash-panel-header"><div><span className="dash-eyebrow">SEPARATE SOURCES</span><h2 id="dash-stream-title">Operating streams</h2></div></div>
        <div className="dash-streams"><div><i className="paper" /><div><strong>Paper</strong><small>Simulation account data</small></div><span>Not connected</span></div><div><i className="shadow" /><div><strong>Shadow</strong><small>Observed signals without orders</small></div><span>Not connected</span></div><div><i className="forecast" /><div><strong>Forecast</strong><small>Model predictions and evidence</small></div><span>Not connected</span></div></div></section>
      <section className="dash-panel" aria-labelledby="dash-alert-title"><div className="dash-panel-header"><div><span className="dash-eyebrow">MONITORING</span><h2 id="dash-alert-title">Alerts & activity</h2></div></div>
        <div className="dash-empty"><span><Icon name="info" /></span><strong>No alert source connected</strong><p>Security and strategy events will appear when a separately reviewed read-only contract is available.</p></div></section>
    </div>
  </div>;
}
function SessionDetails() {
  return <section className="dash-panel dash-session" aria-labelledby="dash-session-title"><span className="dash-eyebrow">AUTH DEV / SECURITY</span><h1 id="dash-session-title">Session & access</h1>
    <p>This isolated password-only session grants access to the local development preview, not the protected financial application.</p>
    <dl className="dash-details"><div><dt>Identity validation</dt><dd>Confirmed by BFF</dd></div><div><dt>Access profile</dt><dd>PASSWORD_ONLY_DEV_PREVIEW</dd></div><div><dt>Absolute limit</dt><dd>8 hours</dd></div><div><dt>Inactivity limit</dt><dd>30 minutes</dd></div><div><dt>Token renewal</dt><dd>Server-side only</dd></div><div><dt>Financial authorization</dt><dd>Not granted</dd></div></dl>
    <div className="dash-safe"><Icon name="lock" /><p>Background polling and market updates never extend inactivity. Only deliberate user activity in a visible tab can update the idle deadline.</p></div></section>;
}

/** AAL1 development-preview UI; no trading endpoints, provider tokens or storage. */
export function ReadOnlyDashboard({ ready, onSignOut, error }: { ready: boolean; onSignOut: () => void; error: string }) {
  const [section, setSection] = useState<Section>('overview');
  if (!ready) return <div className="dash-checking"><Mark /><p role="status">Checking your development session…</p><small>The BFF must verify access before workspace content appears.</small></div>;
  return <div className="dash-shell">
    <aside className="dash-sidebar" aria-label="Workspace navigation">
      <div className="dash-brand"><Mark /><span>Trading<span>Agent</span></span></div>
      <nav aria-label="Dashboard sections"><span className="dash-nav-label">WORKSPACE</span>
        <button type="button" className={section === 'overview' ? 'dash-nav active' : 'dash-nav'} aria-current={section === 'overview' ? 'page' : undefined} onClick={() => setSection('overview')}><Icon name="chart" /> Overview</button>
        <button type="button" className={section === 'session' ? 'dash-nav active' : 'dash-nav'} aria-current={section === 'session' ? 'page' : undefined} onClick={() => setSection('session')}><Icon name="lock" /> Session & security</button></nav>
      <nav aria-label="Modules not yet available"><span className="dash-nav-label">UPCOMING MODULES</span>{upcoming.map(item => <button key={item.number} type="button" className="dash-nav" disabled title={item.label + ' is not available in this milestone'}><span className="dash-nav-number">{item.number}</span>{item.label}<small>Soon</small></button>)}</nav>
      <div className="dash-sidebar-foot"><span className="dash-light" /><div><strong>OFFLINE / NO_TRADE</strong><small>Local development preview</small></div></div>
    </aside>
    <div className="dash-workspace"><header className="dash-topbar"><span>Workspace <b>/</b> {section === 'overview' ? 'Overview' : 'Session & security'}</span>
      <div className="dash-top-actions"><span className="dash-env">AUTH DEV · READ ONLY</span><span className="dash-avatar">DEV</span><button type="button" className="dash-signout" onClick={onSignOut}><Icon name="back" /> Sign out</button></div></header>
      <main id="dashboard-content" className="dash-content">{section === 'overview' ? <Overview /> : <SessionDetails />}{error && <p role="alert" className="dash-error">{error}</p>}</main>
      <footer className="dash-footer"><span>TradingAgent · Module 2 preview</span><span>Illustrative visuals · No orders · OFFLINE / NO_TRADE</span></footer>
    </div>
  </div>;
}
