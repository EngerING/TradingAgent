import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import assert from 'node:assert/strict';
const git = (...args) => execFileSync('git', args, { encoding: 'utf8' }).trim();
// Local pilot adds no permission to change any other integrated develop component.
const localBase = 'e4e2cd9e28b4a885c744a27a2f4b4e5dc5a5d33a';
let localPilot = false;
try { execFileSync('git', ['merge-base','--is-ancestor',localBase,'HEAD']); localPilot = true; } catch { /* Earlier B1/B2 history keeps its original checks. */ }
if (localPilot) {
 const edits = new Set(['build/react-bff/BrowserFixture/HostedDevelopmentRunner.cs','build/react-bff/BrowserFixture/Program.cs','build/react-bff/preservation.mjs','build/react-bff/verify-results.ps1','src/TradingAgent.Web.Auth/BoundaryLog.cs','src/TradingAgent.Web.Auth/IntegratedHostFactory.cs','src/TradingAgent.Web.Auth/PilotEndpoints.cs','tests/TradingAgent.React.Integration.Tests/TradingAgent.React.Integration.Tests.csproj','tests/TradingAgent.React.Integration.Tests/expected-tests.json','src/TradingAgent.Web.Browser/BrowserHost.cs','frontend-react/src/auth/bff.ts','frontend-react/src/auth/contracts.ts','frontend-react/src/components/AuthLayout.tsx','frontend-react/src/auth/bff.test.ts']);
 const additions = new Set(['build/react-bff/BrowserFixture/LocalPilotPreparation.cs','build/react-bff/BrowserFixture/LocalPilotDiagnostic.cs','build/react-bff/local-pilot.ps1','tests/TradingAgent.React.Integration.Tests/LocalPilotSafetyTests.cs','docs/architecture/m01-4b-b2-local-pilot.md','build/react-bff/serve-local.ps1','tests/TradingAgent.React.Integration.Tests/LocalStartupTests.cs','docs/architecture/m01-4b-b2-persistent-launcher.md','docs/architecture/m01-4b-b3-real-login.md']);
 for (const row of git('diff','--name-status','--no-renames',localBase,'HEAD').split('\n').filter(Boolean)) {
  const [status,path] = row.split('\t');
  assert(status === 'M' && edits.has(path) || status === 'A' && additions.has(path), `Local pilot exceeds scope: ${row}`);
 }
 for (const path of git('ls-tree','-r','--name-only',localBase).split('\n').filter(p => !edits.has(p)))
  assert(git('rev-parse',`${localBase}:${path}`) === git('rev-parse',`HEAD:${path}`), `Integrated baseline changed: ${path}`);
}
const baseline = 'efd13f6be8c3c720e24cd9921c2cf7f5b1db7bd5';
execFileSync('git', ['merge-base', '--is-ancestor', baseline, 'HEAD']);
const allowedEdits = new Set([
 'src/TradingAgent.Web.Auth/BoundaryLog.cs', 'src/TradingAgent.Web.Auth/PilotEndpoints.cs',
 '.github/workflows/m01-4a-react-auth-ci.yml', 'AGENTS.md', 'build/react-auth/preservation.mjs', 'build/auth/expected-tests.json',
 'tests/TradingAgent.Auth.Tests/ReviewRegressionTests.cs', 'tests/TradingAgent.Auth.Tests/AdversarialBffTests.cs',
 'src/TradingAgent.Web.Auth/IntegratedHostFactory.cs', 'src/TradingAgent.Web.Auth/PilotRuntime.cs', 'src/TradingAgent.Web.Auth/TemporarySessions.cs',
 'frontend-react/package.json', 'frontend-react/package-lock.json', 'frontend-react/scripts/verify-results.mjs',
 'frontend-react/src/main.tsx', 'frontend-react/src/auth/contracts.ts', 'frontend-react/src/components/AuthLayout.tsx',
 'frontend-react/src/pages/Login.tsx', 'frontend-react/src/pages/Mfa.tsx', 'frontend-react/src/pages/SessionState.tsx', 'frontend-react/src/pages/PasswordFlows.tsx'
]);
const changes = git('diff', '--name-status', '--no-renames', baseline, 'HEAD').split('\n').filter(Boolean);
for (const row of changes) {
 const [status, path] = row.split('\t');
 assert(status === 'M' && allowedEdits.has(path) || status === 'A' && /^(src\/TradingAgent.Web.Browser\/|tests\/TradingAgent.React.Integration.Tests\/|build\/react-bff\/|frontend-react\/(integration\/|playwright.integration.config.ts$|src\/auth\/(?:bff(?:.test)?.ts|session-ui.test.tsx)$|src\/components\/EnrollmentQr.tsx$)|docs\/architecture\/m01-4b-[\w-]+\.(md|json)$|\.github\/workflows\/m01-4b-react-bff-ci.yml$)/.test(path), `Unapproved diff: ${row}`);
 assert(!/(^|\/)(node_modules|dist|\.local|\.env|bin|obj|test-results|playwright-report)(\/|$)|\.(pfx|p12|pem|crt|key|exe|dll|zip|db|sqlite)$/i.test(path), `Sensitive path: ${path}`);
}
// Every baseline file outside the explicit edit list is compared by Git blob, including tests and visual assets.
const preserved = git('ls-tree','-r','--name-only',baseline).split('\n').filter(p => !allowedEdits.has(p));
for (const path of preserved) assert(git('rev-parse', `${baseline}:${path}`) === git('rev-parse', `HEAD:${path}`), `Baseline changed: ${path}`);
const protectedPaths = ['python/trading_agent/core_v3','python/trading_agent/market_analyst','src/TradingAgent.Core','src/TradingAgent.Api','src/TradingAgent.Infrastructure','frontend','Directory.Build.props','TradingAgent.sln','build/auth-pilot','build/identity','build/web','frontend-react/src/styles','frontend-react/src/components/Icons.tsx','frontend-react/src/components/MarketIllustration.tsx','frontend-react/reference'];
const objects = Object.fromEntries(protectedPaths.map(p => { const a = git('rev-parse', `${baseline}:${p}`), b = git('rev-parse', `HEAD:${p}`); assert(a === b, `Protected component: ${p}`); return [p,b]; }));
const main = git('rev-parse','origin/main'); assert(main === 'f67fa92086d10b9562df214f4e869344bf0753d8');
const result = { baseline, commit: git('rev-parse','HEAD'), tree: git('rev-parse','HEAD^{tree}'), main, preserved_files: preserved.length, approved_edit_paths: [...allowedEdits], protected_objects: objects, changes, mode:'OFFLINE', decision:'NO_TRADE', result:'PASS' };
for (const phase of ['m014a','m014b']) { mkdirSync(`artifacts/${phase}`, {recursive:true}); writeFileSync(`artifacts/${phase}/identity.json`, JSON.stringify(result,null,2)+'\n'); }
console.log(`M01.4B preservation PASS: ${preserved.length} baseline files byte-identical in Git; explicit auth-only edits; main unchanged.`);
