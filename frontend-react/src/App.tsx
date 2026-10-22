import { useState } from 'react';
import { Route, Routes, useLocation } from 'react-router';
import type { AuthAdapter } from './auth/contracts';
import { AuthContext } from './auth/context';
import { AuthLayout } from './components/AuthLayout';
import { Login } from './pages/Login';
import { ForgotPassword, PasswordSetup } from './pages/PasswordFlows';
import { Mfa } from './pages/Mfa';
import { MfaRecovery } from './pages/MfaRecovery';
import { BlockedCallback, SessionState } from './pages/SessionState';
export function App({ adapter, blockedCallback = false }: { adapter: AuthAdapter; blockedCallback?: boolean }) {
  const location = useLocation(); const [rejectedEntry] = useState(location.key);
  return <AuthContext value={adapter}><AuthLayout>{blockedCallback && location.key === rejectedEntry ? <BlockedCallback /> : <Routes>
    <Route path="/" element={<Login />} /><Route path="/login" element={<Login />} />
    <Route path="/forgot-password" element={<ForgotPassword />} />
    <Route path="/reset-password" element={<PasswordSetup />} />
    <Route path="/invitation" element={<PasswordSetup invitation />} />
    <Route path="/mfa/enroll" element={<Mfa enrollment />} />
    <Route path="/mfa/verify" element={<Mfa />} />
    <Route path="/mfa/recovery" element={<MfaRecovery />} />
    <Route path="/session/:state" element={<SessionState />} />
    <Route path="*" element={<BlockedCallback />} />
  </Routes>}</AuthLayout></AuthContext>;
}
