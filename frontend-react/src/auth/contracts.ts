export type AuthKind = 'anonymous' | 'mfa-required' | 'demo-enrollment' | 'invalid-code' |
  'demo-complete' | 'preview-complete' | 'invalid-credentials' | 'mfa-recovery-required' | 'expired' | 'unavailable' | 'denied' |
  'demo-recovery' | 'demo-invitation' | 'demo-password-set' | 'complete' | 'enrollment' | 'conflict' | 'rate-limited';
export type AuthResult = Readonly<{ kind: AuthKind; enrollment?: Readonly<{ secret: string; uri: string }> }>;
export interface AuthAdapter {
  readonly mode: 'demo' | 'unavailable' | 'bff';
  readonly source?: 'synthetic' | 'hosted' | 'preview' | 'local-checks';
  login(email: string, password: string, signal?: AbortSignal): Promise<AuthResult>;
  session(signal?: AbortSignal): Promise<AuthResult>;
  enroll(signal?: AbortSignal): Promise<AuthResult>;
  verify(code: string, signal?: AbortSignal): Promise<AuthResult>;
  recover(email: string, signal?: AbortSignal): Promise<AuthResult>;
  invitation(signal?: AbortSignal): Promise<AuthResult>;
  setPassword(password: string, signal?: AbortSignal): Promise<AuthResult>;
  activity?(signal?: AbortSignal): Promise<AuthResult>;
  logout(): Promise<void>;
}

// Existing BFF wire contracts only. No transport is enabled by M01.4A.
export const bffRoutes = Object.freeze({ csrf: '/bff/csrf', login: '/bff/auth/login',
  previewLogin: '/bff/preview/login', previewSession: '/bff/preview/session', previewActivity: '/bff/preview/activity', previewLogout: '/bff/preview/logout',
  enroll: '/bff/auth/mfa/enroll', challenge: '/bff/auth/mfa/challenge',
  verify: '/bff/auth/mfa/verify', session: '/bff/session', logout: '/bff/auth/logout' });
export interface BffCsrfResponse { token: string }
export interface BffLoginRequest { email: string; password: string }
export interface BffLoginResponse { status: 'MFA_REQUIRED'; factors: readonly { id: string; verified: boolean }[]; executionAuthorized: false }
export interface BffChallengeRequest { factorId: string }
export interface BffEnrollmentResponse { factorId: string; secret: string; uri: string }
export interface BffChallengeResponse { id: string; expiresAt: string }
export interface BffVerifyRequest { challengeId: string; code: string }
export interface BffVerifyResponse { status: 'SIGNED_IN'; expiresAt: string; renewable: false; executionAuthorized: false }
export interface BffSessionResponse { authenticated: true; aal: 'aal2'; expiresAt: string; renewable: false; providerSessionConfirmedActive: false; executionAuthorized: false; mode: 'OFFLINE'; decision: 'NO_TRADE' }
export interface BffError { code: string; correlationId: string; executionAuthorized: false }
export const pendingBffCapabilities = Object.freeze({ recovery: 'NOT_IMPLEMENTED', invitation: 'NOT_IMPLEMENTED' });

export const unavailableAdapter: AuthAdapter = {
  mode: 'unavailable', login: async () => ({ kind: 'unavailable' }), session: async () => ({ kind: 'anonymous' }),
  enroll: async () => ({ kind: 'unavailable' }), verify: async () => ({ kind: 'unavailable' }),
  recover: async () => ({ kind: 'unavailable' }), invitation: async () => ({ kind: 'unavailable' }),
  setPassword: async () => ({ kind: 'unavailable' }), logout: async () => {},
};
