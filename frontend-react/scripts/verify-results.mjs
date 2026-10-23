import { readFileSync, writeFileSync } from 'node:fs';
import assert from 'node:assert/strict';
const e2e = JSON.parse(readFileSync('../artifacts/m014a/e2e.json','utf8'));
assert(e2e.stats.expected === 20 && e2e.stats.unexpected === 0 && e2e.stats.flaky === 0 && e2e.stats.skipped === 0);
const unit = readFileSync('test-results/unit.xml','utf8');
const cases = [...unit.matchAll(/<testcase\b/g)].length;
assert(cases === 34 && !/<(?:failure|error|skipped)\b/.test(unit),'Missing or non-passing unit cases');
const expected = JSON.parse(readFileSync('scripts/expected-tests.json','utf8'));
assert.deepEqual([...unit.matchAll(/<testcase\b[^>]*\bname="([^"]*)"/g)].map(m=>m[1]).sort(),[...expected.unit,...JSON.parse(readFileSync('../build/react-bff/expected-unit.json','utf8'))].toSorted());
const walk = suite => [...(suite.specs ?? []),...(suite.suites ?? []).flatMap(walk)];
const specs = e2e.suites.flatMap(walk);
assert(specs.length === 20 && specs.every(spec => spec.ok && spec.tests.length === 1 && spec.tests[0].results.length === 1 && spec.tests[0].results[0].status === 'passed'));
assert.deepEqual(specs.map(spec=>spec.title).sort(),expected.e2e.toSorted());
const result = { unit_passed:cases, original_unit_passed:13, new_unit_passed:21, e2e_passed:20, failed:0, skipped:0, retries:0,
  routes:specs.map(spec=>spec.title), mode:'OFFLINE', decision:'NO_TRADE' };
writeFileSync('../artifacts/m014a/result.json',JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result));
