import { readdir, readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const files = await readdir('dist/assets');
const js = (await Promise.all(files.filter(p => p.endsWith('.js')).map(p => readFile(`dist/assets/${p}`, 'utf8')))).join('\n');
// Public help copy is shared by the screens; these markers belong only to adapter logic.
assert(!js.includes('unavailable@tradingagent.test') && !js.includes('denied@tradingagent.test'), 'Development fixture entered production bundle');
assert(!files.some(p => /^demo[-.]/.test(p)), 'Development adapter chunk in production output');
assert(!js.includes('sb_publishable_') && !js.includes('sb_secret_'), 'Provider configuration in browser bundle');
assert(!/localStorage|sessionStorage/.test(js), 'Browser persistence in production bundle');
assert(!files.some(p => p.endsWith('.map')), 'Production source maps must remain disabled');
console.log('PRODUCTION_BOUNDARY: PASS; no demo adapter, provider keys, browser persistence or source maps.');
