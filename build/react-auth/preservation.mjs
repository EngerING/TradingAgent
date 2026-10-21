import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import assert from 'node:assert/strict';
const git = (...args) => execFileSync('git', args, { encoding:'utf8' }).trim();
const baseline = 'cd25a103b177d43a59f9d99c8047c0db3d20abbb';
execFileSync('git', ['merge-base','--is-ancestor',baseline,'HEAD']);
const changes = git('diff','--name-status','--no-renames',baseline,'HEAD').split('\n').filter(Boolean);
for (const row of changes) {
  const [status,path] = row.split('\t');
  assert(status === 'A' && /^(frontend-react\/|build\/react-auth\/|docs\/architecture\/m01-4a-[\w-]+\.(md|json)$|\.github\/workflows\/m01-4a-react-auth-ci\.yml$|AGENTS\.md$)/.test(path), 'Change outside additive M01.4A scope');
  assert(!/(^|\/)(node_modules|dist|\.local|\.env|test-results|playwright-report)(\/|$)|\.(pfx|pem|key|exe|dll|zip|db|sqlite)$/i.test(path), 'Sensitive/artifact path');
}
const paths = ['python/trading_agent/core_v3','python/trading_agent/market_analyst','src','frontend','tests','Directory.Build.props','TradingAgent.sln','build/auth','build/auth-pilot','build/web','build/identity'];
const objects = Object.fromEntries(paths.map(path => {
  const before = git('rev-parse',`${baseline}:${path}`), after = git('rev-parse',`HEAD:${path}`);
  assert(before === after, `Protected object changed: ${path}`); return [path,after];
}));
const count = git('ls-tree','-r','--name-only',baseline).split('\n').length;
assert(count === 843);
const main = git('rev-parse','origin/main'); assert(main === 'f67fa92086d10b9562df214f4e869344bf0753d8');
mkdirSync('artifacts/m014a', {recursive:true});
writeFileSync('artifacts/m014a/identity.json',JSON.stringify({ baseline, commit:git('rev-parse','HEAD'), tree:git('rev-parse','HEAD^{tree}'), main, preserved_files:count, protected_objects:objects, changes:changes.length, result:'PASS', mode:'OFFLINE', decision:'NO_TRADE' },null,2)+'\n');
console.log(`Preservation PASS: ${count} baseline files, all protected objects, main unchanged.`);
