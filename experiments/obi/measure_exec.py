#!/usr/bin/env python3
"""OBI copy of experiments/php-distro/measure_exec.py: same lock, login, warm-up, rotation, settle and hash checks.
Added: when OBI_CG is set (the OBI container's cgroup v2 directory on the Docker VM, read through the CGREADER
container), every row also records OBI's own CPU time over the same window, and the summary reports OBI memory.
Host-driven variant of measure.py that also records container CPU time per request.
Requests run through `docker exec <container> curl http://127.0.0.1:8080` so the cgroup's cpu.stat (usage_usec,
nr_throttled) can be read right before and after each request; wall time is curl's time_total.
  measure_exec.py <heavy|light> <pairs> <out.json> <variant> [<variant> ...]   (first variant = baseline)
Traceparent policy is the same as measure.py (pair 0 sampled by traceidratio 0.1, the rest dropped; flag 01 always)."""
import os, json, math, re, statistics, subprocess, sys, time, hashlib, atexit, signal
# The script takes the machine-wide timing lock itself (env LOCK, a directory created with mkdir) for the whole measurement
# and releases it on exit, error or TERM/INT, so no wrapper is needed and no timed run can overlap another benchmark.
LOCK = os.environ['LOCK']
while True:
    try: os.mkdir(LOCK); break
    except FileExistsError: time.sleep(15)
def _release(*_):
    try: os.rmdir(LOCK)
    except OSError: pass
atexit.register(_release)
STARTED = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
for _s in (signal.SIGTERM, signal.SIGINT): signal.signal(_s, lambda *a: (_release(), os._exit(1)))
APP = os.environ.get('APP', 'fix')
OBI_CG = os.environ.get('OBI_CG'); CGREADER = os.environ.get('CGREADER', 'f1x-cgreader')
def obi_cpu():
    if not OBI_CG: return 0
    d = dict(l.split() for l in subprocess.run(['docker', 'exec', CGREADER, 'cat', f'{OBI_CG}/cpu.stat'], capture_output=True, text=True, check=True).stdout.splitlines())
    return int(d['usage_usec'])
def obi_mem():
    if not OBI_CG: return {}
    r = lambda f: subprocess.run(['docker', 'exec', CGREADER, 'cat', f'{OBI_CG}/{f}'], capture_output=True, text=True, check=True).stdout.strip()
    st = dict(l.split() for l in r('memory.stat').splitlines())
    return {'memory_current_bytes': int(r('memory.current')), 'memory_peak_bytes': int(r('memory.peak')), 'anon_bytes': int(st['anon']), 'file_bytes': int(st['file']), 'kernel_bytes': int(st.get('kernel', 0)), 'percpu_bytes': int(st.get('percpu', 0))}
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
    o0 = obi_cpu(); c0, t0 = cpu(v)
    r = ex(v, CURL + f"-H 'traceparent: 00-{tid(i)}-fffffffffffffffe-01' -o /tmp/o.html -w '%{{time_total}} %{{http_code}} %{{url_effective}}' http://127.0.0.1:8080/home")
    time.sleep(1.0)  # let the background exporter finish before the second reading
    c1, t1 = cpu(v); o1 = obi_cpu()
    tt, code, _ = r.split()
    h = ex(v, "t=$(grep -o 'csrf-token\" content=\"[^\"]*' /tmp/o.html | cut -d'\"' -f3); test -n \"$t\" && sed \"s/$t/NORMALIZED_CSRF/g\" /tmp/o.html | sha256sum | cut -d' ' -f1; grep -c 'Fixture Pilot' /tmp/o.html").split()
    if len(h) < 2: h = [None, '0']   # non-HTML failure (e.g. 500): keep the row, mark it
    return float(tt) * 1000, int(code), (c1 - c0) / 1000, t1 - t0, h[0], int(h[1]) > 0, (o1 - o0) / 1000
hashes = {}
for v in variants:
    login(v); ms, code, cms, thr, h, ok, _ = get(v, 1)
    if code != 200 or not ok: raise RuntimeError(f'{v}: /home not populated ({code})')
    hashes[v] = h; print(json.dumps({'warm': v, 'ms': round(ms), 'cpu_ms': round(cms)}), flush=True)
rows = []
for i in range(pairs):
    k = i % len(variants); order = variants[k:] + variants[:k]
    for v in order:
        ms, code, cms, thr, h, ok, ocpu = get(v, i)
        rows.append({'pair': i, 'variant': v, 'ms': ms, 'cpu_ms': cms, 'obi_cpu_ms': ocpu, 'throttled': thr, 'status': code, 'sampled_id': i == 0, 'hash': h})
    print(json.dumps({'pair': i, 'ms': {r['variant']: round(r['ms']) for r in rows if r['pair'] == i}, 'cpu': {r['variant']: round(r['cpu_ms']) for r in rows if r['pair'] == i}}), flush=True)
def pct(xs, q): return sorted(xs)[math.ceil(len(xs) * q) - 1]
base = variants[0]; res = {}
for v in variants:
    R = [r for r in rows if r['variant'] == v]; xs = [r['ms'] for r in R]; cs = [r['cpu_ms'] for r in R]
    res[v] = {'obi_cpu_median': statistics.median(r['obi_cpu_ms'] for r in R), 'n': len(xs), 'median': statistics.median(xs), 'p95': pct(xs, .95), 'cpu_median': statistics.median(cs), 'cpu_p95': pct(cs, .95), 'throttled': sum(r['throttled'] for r in R),
              'p95_excl_pair0': pct([r['ms'] for r in R if r['pair']], .95), 'identical': all(r['hash'] == hashes[base] for r in R) and hashes[v] == hashes[base], 'all_200': all(r['status'] == 200 for r in R)}
for v in variants:
    for k in ('median', 'p95', 'cpu_median', 'cpu_p95'): res[v][k + '_overhead_pct'] = (res[v][k] / res[base][k] - 1) * 100
    res[v]['paired_median_overhead_pct'] = statistics.median([(next(r['ms'] for r in rows if r['pair'] == i and r['variant'] == v) / next(r['ms'] for r in rows if r['pair'] == i and r['variant'] == base) - 1) * 100 for i in range(pairs)])
json.dump({'shape': shape, 'summary': res, 'obi_memory': obi_mem(), 'started': STARTED, 'finished': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'rows': rows, 'baseline_hash': hashes[base]}, open(out, 'w'), indent=1)
