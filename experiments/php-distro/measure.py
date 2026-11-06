#!/usr/bin/env python3
"""Paired, alternating timing of authenticated /home across app containers (f1x-<variant>).
Run inside a client container on the fixture network:
  measure.py <shape: heavy|light> <pairs> <out.json> <variant> [<variant> ...]  (first variant = baseline)
Each variant logs in once, gets one untimed warm-up render, then every pair requests all variants once, rotating the order.
Pair 0 carries a trace ID that traceidratio(0.1) samples; the others carry IDs it drops. Every request has traceparent flag 01
(Traefik samples everything), so parent-based samplers see a sampled parent."""
import hashlib, http.cookiejar, json, math, re, statistics, sys, time, urllib.error, urllib.parse, urllib.request
shape, pairs, out, *variants = sys.argv[1:]; pairs = int(pairs)
email = {'heavy': 'home-fixture@example.test', 'light': 'home-no-titles@example.test'}[shape]
clients = {}
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
def fetch(v, path, body=None, trace=None):
    h = {'Host': 'home.fixture.test', 'Accept': 'text/html', 'Accept-Encoding': 'identity'}
    if trace: h['traceparent'] = f'00-{trace}-fffffffffffffffe-01'
    if body is not None: h['Content-Type'] = 'application/x-www-form-urlencoded'
    r = urllib.request.Request(f'http://f1x-{v}:8080{path}', data=body, headers=h)
    t0 = time.perf_counter_ns()
    try: resp = clients[v].open(r, timeout=300)
    except urllib.error.HTTPError as e:
        if body is None or e.code != 302: raise
        resp = e
    with resp:
        text = resp.read().decode('utf-8'); ms = (time.perf_counter_ns() - t0) / 1e6
        return text, ms, resp.status, resp.geturl()
def norm(b):
    t = re.search(r'<meta name="csrf-token" content="([^"]+)"', b)
    if not t: raise RuntimeError('no csrf meta')
    return hashlib.sha256(b.replace(t.group(1), 'NORMALIZED_CSRF').encode()).hexdigest()
# traceidratio compares the low 56 bits of the trace ID with a threshold: all-f is sampled at 0.1, low values are dropped.
def tid(i): return 'f' * 32 if i == 0 else '0' * 16 + '%016x' % i
hashes = {}
for v in variants:
    clients[v] = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    lg, *_ = fetch(v, '/users/login'); tk = re.search(r'name="_token"[^>]*value="([^"]+)"', lg).group(1)
    fetch(v, '/users/authenticate', urllib.parse.urlencode({'email': email, 'password': 'home-fixture-password', '_token': tk}).encode())
    b, ms, st, url = fetch(v, '/home', trace=tid(1))
    if st != 200 or not url.endswith('/home') or 'Fixture Pilot' not in b: raise RuntimeError(f'{v}: /home not populated')
    hashes[v] = norm(b); print(json.dumps({'warm': v, 'ms': round(ms), 'chars': len(b)}), flush=True)
rows = []
for i in range(pairs):
    order = list(variants[i % len(variants):] + variants[:i % len(variants)])
    for v in order:
        b, ms, st, url = fetch(v, '/home', trace=tid(i))
        rows.append({'pair': i, 'variant': v, 'ms': ms, 'status': st, 'sampled_id': i == 0, 'hash': norm(b)})
    print(json.dumps({'pair': i, 'ms': {r['variant']: round(r['ms']) for r in rows if r['pair'] == i}}), flush=True)
def pct(xs, q): return sorted(xs)[math.ceil(len(xs) * q) - 1]
base = variants[0]; res = {}
for v in variants:
    xs = [r['ms'] for r in rows if r['variant'] == v]; dr = [r['ms'] for r in rows if r['variant'] == v and not r['sampled_id']]
    res[v] = {'n': len(xs), 'median': statistics.median(xs), 'p95': pct(xs, .95), 'p95_excl_pair0': pct(dr, .95), 'min': min(xs), 'max': max(xs),
              'identical': all(r['hash'] == hashes[base] for r in rows if r['variant'] == v) and hashes[v] == hashes[base], 'all_200': all(r['status'] == 200 for r in rows if r['variant'] == v)}
for v in variants:
    res[v]['median_overhead_pct'] = (res[v]['median'] / res[base]['median'] - 1) * 100
    res[v]['p95_overhead_pct'] = (res[v]['p95'] / res[base]['p95'] - 1) * 100
    res[v]['paired_median_overhead_pct'] = statistics.median([(next(r['ms'] for r in rows if r['pair'] == i and r['variant'] == v) / next(r['ms'] for r in rows if r['pair'] == i and r['variant'] == base) - 1) * 100 for i in range(pairs)])
json.dump({'shape': shape, 'summary': res, 'rows': rows, 'baseline_hash': hashes[base]}, open(out, 'w'), indent=1)
print(json.dumps(res, indent=1))
