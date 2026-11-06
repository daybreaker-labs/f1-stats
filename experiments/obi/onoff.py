#!/usr/bin/env python3
"""Cross-talk control: OBI toggled between blocks while both app containers keep running.
kprobes are global and uprobes attach to the php-fpm and nginx inodes, which both containers share
(same image layers), so the unselected `baseline` container may still pay probe costs while OBI runs.
Each block stops or starts the OBI container (alternating, first state alternates by shape), waits until
OBI reports the target's three processes instrumented, then requests both app containers once,
rotating the order. Same login, warm-up, timing, CPU and hash method as measure_exec.py.
  LOCK=<dir> APP=fix onoff.py <heavy|light> <blocks> <out.json>"""
import os, json, statistics, subprocess, sys, time, atexit, signal
LOCK = os.environ['LOCK']
while True:
    try: os.mkdir(LOCK); break
    except FileExistsError: time.sleep(15)
def _release(*_):
    try: os.rmdir(LOCK)
    except OSError: pass
atexit.register(_release)
for _s in (signal.SIGTERM, signal.SIGINT): signal.signal(_s, lambda *a: (_release(), os._exit(1)))
APP = os.environ.get('APP', 'fix'); OBI = os.environ.get('OBI', 'f1x-obi')
shape, blocks, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
variants = ['baseline', 'obi']
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
    time.sleep(1.0)
    c1, t1 = cpu(v)
    tt, code, _ = r.split()
    h = ex(v, "t=$(grep -o 'csrf-token\" content=\"[^\"]*' /tmp/o.html | cut -d'\"' -f3); test -n \"$t\" && sed \"s/$t/NORMALIZED_CSRF/g\" /tmp/o.html | sha256sum | cut -d' ' -f1; grep -c 'Fixture Pilot' /tmp/o.html").split()
    if len(h) < 2: h = [None, '0']
    return float(tt) * 1000, int(code), (c1 - c0) / 1000, t1 - t0, h[0], int(h[1]) > 0
def obi(on):
    if not on:
        subprocess.run(['docker', 'stop', '-t', '10', OBI], capture_output=True, check=True); time.sleep(3); return
    since = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 1))
    subprocess.run(['docker', 'start', OBI], capture_output=True, check=True)
    for _ in range(120):
        logs = subprocess.run(['docker', 'logs', '--since', since, OBI], capture_output=True, text=True).stdout + subprocess.run(['docker', 'logs', '--since', since, OBI], capture_output=True, text=True).stderr
        if logs.count('instrumenting process') >= 3: time.sleep(3); return
        time.sleep(1)
    raise RuntimeError('OBI did not attach')
def running(): return subprocess.run(['docker', 'inspect', '-f', '{{.State.Running}}', OBI], capture_output=True, text=True).stdout.strip() == 'true'
hashes = {}
for v in variants:
    login(v); ms, code, cms, thr, h, ok = get(v, 1)
    if code != 200 or not ok: raise RuntimeError(f'{v}: /home not populated ({code})')
    hashes[v] = h
first_on = shape == 'heavy'
rows = []
for b in range(blocks):
    on = first_on if b % 2 == 0 else not first_on
    if running() != on: obi(on)
    order = variants if b % 4 < 2 else variants[::-1]
    for v in order:
        ms, code, cms, thr, h, ok = get(v, b + 1)
        rows.append({'block': b, 'obi_running': on, 'variant': v, 'ms': ms, 'cpu_ms': cms, 'throttled': thr, 'status': code, 'hash': h})
    print(json.dumps({'block': b, 'obi': on, 'ms': {r['variant']: round(r['ms']) for r in rows if r['block'] == b}, 'cpu': {r['variant']: round(r['cpu_ms']) for r in rows if r['block'] == b}}), flush=True)
if not running(): obi(True)
res = {}
for v in variants:
    for on in (False, True):
        R = [r for r in rows if r['variant'] == v and r['obi_running'] == on]
        res[f'{v}/obi_{"on" if on else "off"}'] = {'n': len(R), 'median': statistics.median(r['ms'] for r in R), 'cpu_median': statistics.median(r['cpu_ms'] for r in R),
            'identical': all(r['hash'] == hashes['baseline'] for r in R), 'all_200': all(r['status'] == 200 for r in R)}
json.dump({'shape': shape, 'summary': res, 'rows': rows}, open(out, 'w'), indent=1)
print(json.dumps(res, indent=1))
