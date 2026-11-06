#!/usr/bin/env python3
"""Two small probes, both under the timing lock (env LOCK):
  probes.py idle <seconds> <out.json>   OBI's own CPU and memory with no traffic (env OBI_CG, CGREADER)
  probes.py floor <n> <out.json>        CPU charged to the app container by the measurement path itself:
                                        the same docker exec + curl + 1 s settle as measure_exec.py, on /healthz
                                        (php-fpm ping through nginx, no Laravel), for baseline and obi."""
import os, json, statistics, subprocess, sys, time, atexit, signal
LOCK = os.environ['LOCK']
while True:
    try: os.mkdir(LOCK); break
    except FileExistsError: time.sleep(15)
atexit.register(lambda: os.path.isdir(LOCK) and os.rmdir(LOCK))
for _s in (signal.SIGTERM, signal.SIGINT): signal.signal(_s, lambda *a: (os.rmdir(LOCK), os._exit(1)))
APP = os.environ.get('APP', 'fix'); CGREADER = os.environ.get('CGREADER', 'f1x-cgreader')
mode, n, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
def rd(f): return subprocess.run(['docker', 'exec', CGREADER, 'cat', f"{os.environ['OBI_CG']}/{f}"], capture_output=True, text=True, check=True).stdout
def ex(v, sh): return subprocess.run(['docker', 'exec', f'f1x-{APP}-' + v, 'sh', '-c', sh], capture_output=True, text=True, check=True).stdout
def cpu(v): return int(dict(l.split() for l in ex(v, 'cat /sys/fs/cgroup/cpu.stat').splitlines())['usage_usec'])
if mode == 'idle':
    u = lambda: int(dict(l.split() for l in rd('cpu.stat').splitlines())['usage_usec'])
    t0, c0 = time.time(), u(); time.sleep(n); t1, c1 = time.time(), u()
    st = dict(l.split() for l in rd('memory.stat').splitlines())
    res = {'seconds': t1 - t0, 'obi_cpu_ms': (c1 - c0) / 1000, 'obi_cpu_ms_per_s': (c1 - c0) / 1000 / (t1 - t0),
           'memory_current_bytes': int(rd('memory.current')), 'anon_bytes': int(st['anon']), 'kernel_bytes': int(st.get('kernel', 0))}
else:
    rows = []
    for i in range(n):
        for v in (['baseline', 'obi'] if i % 2 == 0 else ['obi', 'baseline']):
            c0 = cpu(v); r = ex(v, "curl -s -o /dev/null -w '%{time_total} %{http_code}' -H 'Host: home.fixture.test' http://127.0.0.1:8080/healthz"); time.sleep(1.0); c1 = cpu(v)
            rows.append({'variant': v, 'ms': float(r.split()[0]) * 1000, 'status': int(r.split()[1]), 'cpu_ms': (c1 - c0) / 1000})
    res = {v: {'n': sum(r['variant'] == v for r in rows), 'cpu_median': statistics.median(r['cpu_ms'] for r in rows if r['variant'] == v),
               'ms_median': statistics.median(r['ms'] for r in rows if r['variant'] == v), 'all_200': all(r['status'] == 200 for r in rows if r['variant'] == v)} for v in ('baseline', 'obi')}
    res['rows'] = rows
json.dump({'mode': mode, 'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'result': res}, open(out, 'w'), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != 'rows'}))
