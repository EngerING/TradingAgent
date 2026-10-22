import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import '@fontsource/inter/latin-400.css';
import '@fontsource/inter/latin-500.css';
import '@fontsource/inter/latin-600.css';
import '@fontsource/libre-baskerville/latin-700.css';
import './styles/tokens.css';
import './styles/auth.css';
import { App } from './App';
import { configuredBff } from './auth/bff';
import { unavailableAdapter } from './auth/contracts';

// Never parse callback token/code values. Fail closed before mounting the application.
const blockedCallback = location.search.length > 0 || location.hash.length > 0;
if (blockedCallback) history.replaceState(null, '', location.pathname);
const adapter = import.meta.env.DEV && import.meta.env.MODE === 'demo' ? (await import('./auth/demo')).createDemoAdapter() : blockedCallback ? unavailableAdapter : (await configuredBff()) ?? unavailableAdapter;
createRoot(document.getElementById('root')!).render(<StrictMode><BrowserRouter><App adapter={adapter} blockedCallback={blockedCallback} /></BrowserRouter></StrictMode>);
