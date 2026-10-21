import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
import { PNG } from 'pngjs';
import pixelmatch from 'pixelmatch';
const source = readFileSync('reference/tradingagent-login-reference.png');
const actual = readFileSync('../artifacts/m014a/screenshots/login-1536x1024.png');
const reference = PNG.sync.read(source), rendered = PNG.sync.read(actual);
assert(reference.width === 1536 && reference.height === 1024);
assert(rendered.width === reference.width && rendered.height === reference.height);
const diff = new PNG({ width:reference.width, height:reference.height });
const changed = pixelmatch(reference.data,rendered.data,diff.data,reference.width,reference.height,{ threshold:0.1 });
const fraction = changed / (reference.width*reference.height);
const result = { width:reference.width, height:reference.height, changed_pixels:changed, changed_fraction:fraction,
  per_pixel_threshold:0.1, maximum_fraction:0.30, reference_sha256:createHash('sha256').update(source).digest('hex'),
  screenshot_sha256:createHash('sha256').update(actual).digest('hex'),
  limitation:'Pixel difference catches gross drift; not a perceptual similarity score or independent visual approval. Original fonts and raster illustration are approximated with local fonts and editable vectors.' };
mkdirSync('../artifacts/m014a',{ recursive:true });
writeFileSync('../artifacts/m014a/reference-comparison.json',JSON.stringify(result,null,2)+'\n');
writeFileSync('../artifacts/m014a/reference-diff.png',PNG.sync.write(diff));
assert(fraction < 0.30,'Reference differs beyond gross visual drift budget');
console.log(JSON.stringify(result));
