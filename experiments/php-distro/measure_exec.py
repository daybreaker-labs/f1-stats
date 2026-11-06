#!/usr/bin/env python3
"""Host-driven variant of measure.py that also records container CPU time per request.
Requests run through `docker exec <container> curl http://127.0.0.1:8080` so the cgroup's cpu.stat (usage_usec,
nr_throttled) can be read right before and after each request; wall time is curl's time_total.
  measure_exec.py <heavy|light> <pairs> <out.json> <variant> [<variant> ...]   (first variant = baseline)
Traceparent policy is the same as measure.py (pair 0 sampled by traceidratio 0.1, the rest dropped; flag 01 always)."""
import os, json, math, re, statistics, subprocess, sys, time, hashlib
APP = os.environ.get('APP', 'main')
shape, pairs, out, *variants = sys.argv[1:]; pairs = int(pairs)
email = {'heavy': 'home-fixture@example.test', 'light': 'home-no-titles@example.test'}[shape]
def ex(v, sh): return subprocess.run(['docker', 'exec', f'f1x-{APP}-' + v, 'sh', '-c', sh], capture_output=True, text=True, check=True).stdout
def cpu(v):
    d = dict(l.split() for l in ex(v, 'cat /sys/fs/cgroup/cpu.stat').splitlines())
    return int(d['usage_usec']), int(d.get('nr_throttled', 0))
CURL = "curl -s -H 'Host: home.fixture.test' -H 'Accept-Encoding: identity' -b /tmp/cj -c /tmp/cj "
def login(v):
    ex(v, 'rm -f /tmp/cj /tmp/o.html')
    tk = ex(v, CURL + "http://127.0.0.1:8080/users/login | grep -o 'name=\"_token\"[^>]*value=\"[^\"]*' | sed 's/.*value=\"//'").strip()
    ex(v, CURL + f"-o /dev/null --data-urlencode _token={tk} --data-urlencode email={email} --data-urlencode password=home-fixture-password http://127.0.0.1:8080/users/authenticate")
def tid(i): return 'f' * 32 if i == 0 else '0' * 16 + '%016x' % i
def get(v, i):
    c0, t0 = cpu(v)
    r = ex(v, CURL + f"-H 'traceparent: 00-{tid(i)}-fffffffffffffffe-01' -o /tmp/o.html -w '%{{time_total}} %{{http_code}} %{{url_effective}}' http://127.0.0.1:8080/home")
    time.sleep(1.0)  # let the background exporter finish before the second reading
    c1, t1 = cpu(v)
    tt, code, _ = r.split()
    h = ex(v, "t=$(grep -o 'csrf-token\" content=\"[^\"]*' /tmp/o.html | cut -d'\"' -f3); test -n \"$t\" && sed \"s/$t/NORMALIZED_CSRF/g\" /tmp/o.html | sha256sum | cut -d' ' -f1; grep -c 'Fixture Pilot' /tmp/o.html").split()
    return float(tt) * 1000, int(code), (c1 - c0) / 1000, t1 - t0, h[0], int(h[1]) > 0
hashes = {}
for v in variants:
    login(v); ms, code, cms, thr, h, ok = get(v, 1)
    if code != 200 or not ok: raise RuntimeError(f'{v}: /home not populated ({code})')
    hashes[v] = h; print(json.dumps({'warm': v, 'ms': round(ms), 'cpu_ms': round(cms)}), flush=True)
rows = []
for i in range(pairs):
    k = i % len(variants); order = variants[k:] + variants[:k]
    for v in order:
        ms, code, cms, thr, h, ok = get(v, i)
        rows.append({'pair': i, 'variant': v, 'ms': ms, 'cpu_ms': cms, 'throttled': thr, 'status': code, 'sampled_id': i == 0, 'hash': h})
    print(json.dumps({'pair': i, 'ms': {r['variant']: round(r['ms']) for r in rows if r['pair'] == i}, 'cpu': {r['variant']: round(r['cpu_ms']) for r in rows if r['pair'] == i}}), flush=True)
def pct(xs, q): return sorted(xs)[math.ceil(len(xs) * q) - 1]
base = variants[0]; res = {}
for v in variants:
    R = [r for r in rows if r['variant'] == v]; xs = [r['ms'] for r in R]; cs = [r['cpu_ms'] for r in R]
    res[v] = {'n': len(xs), 'median': statistics.median(xs), 'p95': pct(xs, .95), 'cpu_median': statistics.median(cs), 'cpu_p95': pct(cs, .95), 'throttled': sum(r['throttled'] for r in R),
              'identical': all(r['hash'] == hashes[base] for r in R) and hashes[v] == hashes[base], 'all_200': all(r['status'] == 200 for r in R)}
for v in variants:
    for k in ('median', 'p95', 'cpu_median', 'cpu_p95'): res[v][k + '_overhead_pct'] = (res[v][k] / res[base][k] - 1) * 100
    res[v]['paired_median_overhead_pct'] = statistics.median([(next(r['ms'] for r in rows if r['pair'] == i and r['variant'] == v) / next(r['ms'] for r in rows if r['pair'] == i and r['variant'] == base) - 1) * 100 for i in range(pairs)])
json.dump({'shape': shape, 'summary': res, 'rows': rows, 'baseline_hash': hashes[base]}, open(out, 'w'), indent=1)
