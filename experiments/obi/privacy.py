#!/usr/bin/env python3
"""Privacy scan of everything OBI exported (collector file exporter, OTLP JSON lines).
  privacy.py <traces.jsonl> <metrics.jsonl> <out.json> [extra literal ...]
Checks every resource, span, event and data-point attribute key and value for:
  query strings ('?' or '=' in url.* / http.target values, url.query keys), cookies and session names,
  CSRF tokens (`_token`, XSRF, 40-char Laravel token shapes), credentials (fixture emails, password),
  SQL text (db.query.text / db.statement keys, quoted literals or `= <number>` in db.* values),
  plus any extra literal passed on the command line (e.g. a query-string value sent on purpose).
Reports hits by attribute key with an example, plus the full key inventory."""
import json, re, sys, collections
tr, me, out, *extra = sys.argv[1:]
LIT = ['home-fixture@example.test', 'home-no-titles@example.test', 'home-fixture-password', 'laravel_session', 'XSRF-TOKEN', 'remember_web', '_token'] + extra
checks = {
  'query_string': lambda k, v: (k.startswith('url.') or k in ('http.target', 'http.url')) and ('?' in v or '=' in v) or k == 'url.query',
  'cookie': lambda k, v: 'cookie' in k.lower() or re.search(r'(?i)cookie|laravel_session|remember_web', v) is not None,
  'csrf': lambda k, v: re.search(r'(?i)_token|xsrf|csrf', k + ' ' + v) is not None or re.fullmatch(r'[A-Za-z0-9]{40}', v) is not None,
  'credential': lambda k, v: re.search(r'(?i)password|@example\.test', k + ' ' + v) is not None,
  'sql_text': lambda k, v: k in ('db.query.text', 'db.statement') or (k.startswith('db.') and (re.search(r"'[^']*'", v) or re.search(r'=\s*-?\d', v))),
  'sql_literal': lambda k, v: k in ('db.query.text', 'db.statement') and re.search(r"(?i)\bin \((\d+, )*\d+\)|'[^']*'|[=<>]\s*-?\d", v) is not None,
  'literal': lambda k, v: any(x in v for x in LIT),
}
# Examples are committed: mask live CSRF/session token shapes (40+ alphanumerics) before storing them.
MASK = lambda v: re.sub(r'[A-Za-z0-9]{40,}', '<token-shaped value masked>', v)
hits = collections.defaultdict(lambda: {'count': 0, 'example': None}); keys = collections.Counter(); n = {'spans': 0, 'datapoints': 0}
def val(a): return str(list(a['value'].values())[0]) if a.get('value') else ''
def scan(attrs, where):
    for a in attrs or []:
        k, v = a['key'], val(a); keys[f'{where}:{k}'] += 1
        for c, f in checks.items():
            if f(k, v):
                h = hits[f'{c}:{where}:{k}']; h['count'] += 1; h['example'] = h['example'] or MASK(v[:200])
for l in open(tr):
    for rs in json.loads(l).get('resourceSpans', []):
        scan(rs['resource'].get('attributes'), 'resource')
        for ss in rs.get('scopeSpans', []):
            for s in ss.get('spans', []):
                n['spans'] += 1; scan(s.get('attributes'), 'span')
                if any(x in s['name'] for x in LIT) or '?' in s['name']: h = hits['literal:span:name']; h['count'] += 1; h['example'] = h['example'] or s['name']
                for e in s.get('events', []): scan(e.get('attributes'), 'event')
for l in open(me):
    for rm in json.loads(l).get('resourceMetrics', []):
        scan(rm['resource'].get('attributes'), 'resource')
        for sm in rm.get('scopeMetrics', []):
            for m in sm.get('metrics', []):
                for kind in ('sum', 'gauge', 'histogram', 'exponentialHistogram'):
                    for dp in m.get(kind, {}).get('dataPoints', []): n['datapoints'] += 1; scan(dp.get('attributes'), 'metric')
res = {'scanned': n, 'hits': dict(hits), 'pass': not hits, 'attribute_keys': dict(sorted(keys.items()))}
json.dump(res, open(out, 'w'), indent=1); print(json.dumps({'scanned': n, 'pass': res['pass'], 'hits': dict(hits)}, indent=1))
