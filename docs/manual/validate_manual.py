"""Validate documentation artifacts without loading application modules or services."""
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tmp/manual-tools'))
import pymupdf

md_path = OUT / 'TradingAgent_Manual_Tecnico_Integral.md'
pdf_path = OUT / 'TradingAgent_Manual_Tecnico_Integral.pdf'
md = md_path.read_text(encoding='utf-8')
doc = pymupdf.open(pdf_path)
chapters = re.findall(r'^# (\d+\. .+)$', md, re.M)
assert len(chapters) == 15
toc = doc.get_toc()
assert len(toc) == 19, toc
for _, title, number in toc:
    page_text = doc[number-1].get_text()
    assert title in page_text, (title, number)
for title in chapters:
    assert any(entry[1] == title for entry in toc), title

paths = re.findall(r'`([^`\n]+\.(?:py|cs|sql|ps1|ts|vue|json|props|sln|md)):([0-9]+)`', md)
for name, line in paths:
    path = ROOT / name
    assert path.is_file(), name
    assert 1 <= int(line) <= len(path.read_text(encoding='utf-8-sig').splitlines()), (name, line)
figures = re.findall(r'!\[[^\]]*\]\((diagrams/[^)]+)\)', md)
assert len(figures) == 8
for name in figures:
    assert (OUT/name).is_file(), name
assert '<!-- TRACEABILITY -->' not in md and '<!-- PROTECTED -->' not in md

secret_patterns = {
    'private_key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'jwt': r'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}',
    'literal_bearer': r'Bearer\s+[A-Za-z0-9_+./=-]{30,}',
    'credential_assignment': r'(?i)(?:password|api_key|secret)\s*[:=]\s*[\x22\x27][A-Za-z0-9_+./=-]{16,}[\x22\x27]',
}
secret_matches = {k: len(re.findall(pattern, md)) for k, pattern in secret_patterns.items()}
assert not any(secret_matches.values()), secret_matches

body_lengths = []
margin_violations = []
for number, page in enumerate(doc, 1):
    spans = [s for b in page.get_text('dict')['blocks'] for l in b.get('lines', []) for s in l['spans']]
    body = [s for s in spans if 45 <= s['bbox'][1] < page.rect.height-45]
    body_lengths.append(sum(len(s['text'].strip()) for s in body))
    assert body_lengths[-1] > 100, (number, body_lengths[-1])
    assert '\ufffd' not in page.get_text(), number
    if number > 1:
        for s in body:
            x0, _, x1, _ = s['bbox']
            if x0 < 49 or x1 > page.rect.width-43:
                margin_violations.append({'page': number, 'text': s['text'], 'bounds': s['bbox']})
assert not margin_violations, margin_violations

report_path = OUT/'pdf-validation.json'
report = json.loads(report_path.read_text(encoding='utf-8'))
report.update({
    'pdf_sha256': hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
    'md_sha256': hashlib.sha256(md_path.read_bytes()).hexdigest(),
    'chapter_count': len(chapters), 'bookmarks_and_page_targets_verified': len(toc),
    'index_paths_and_lines_verified': len(paths), 'svg_sources_verified': len(figures),
    'body_text_lengths': body_lengths, 'body_margin_violations': margin_violations,
    'secret_pattern_scan': secret_matches,
    'secret_review_scope': 'Public documentation only; no secret values read for comparison. Patterns and manual content review are complementary.',
    'review_status': 'AUTOMATED_CHECKS_PASS_VISUAL_REVIEW_PENDING',
})
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:report[k] for k in ('pages','chapter_count','bookmarks_and_page_targets_verified','index_paths_and_lines_verified','svg_sources_verified','body_margin_violations','secret_pattern_scan')}, ensure_ascii=False))
