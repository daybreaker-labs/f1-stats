#!/usr/bin/env python3
"""Span and metric sample from the collector's OTLP JSON files (OBI service only).
  sample.py <traces.jsonl> <metrics.jsonl> <out.json> [service.name]
Writes one example per (span name, kind) with attributes, the full span tree of one heavy GET /home
trace, counts per span name, and every metric name with unit, type and data-point attribute keys."""
import json, sys, collections
tr, me, out, svc = (sys.argv[1:] + ['f1x-fix-obi'])[:4]
KIND = {1: 'INTERNAL', 2: 'SERVER', 3: 'CLIENT'}
def av(a): return list(a['value'].values())[0] if a.get('value') else None
spans, resource = [], None
for l in open(tr):
    for rs in json.loads(l).get('resourceSpans', []):
        ra = {a['key']: av(a) for a in rs['resource'].get('attributes', [])}
        if ra.get('service.name') != svc: continue
        resource = resource or ra
        for ss in rs.get('scopeSpans', []):
            for s in ss.get('spans', []):
                spans.append({'trace': s['traceId'], 'span': s['spanId'], 'parent': s.get('parentSpanId', ''), 'name': s['name'], 'kind': KIND.get(s.get('kind'), s.get('kind')),
                              'duration_ms': round((int(s['endTimeUnixNano']) - int(s['startTimeUnixNano'])) / 1e6, 3), 'attributes': {a['key']: av(a) for a in s.get('attributes', [])}})
examples = {}
for s in spans: examples.setdefault(f"{s['kind']} {s['name']}", {k: s[k] for k in ('duration_ms', 'attributes')})
home = [s for s in spans if s['name'] == 'GET /home' and s['kind'] == 'SERVER' and s['attributes'].get('server.port') == '8080']
home.sort(key=lambda s: -s['duration_ms'])
t = home[0]['trace'] if home else None
by_parent = collections.defaultdict(list)
for s in spans:
    if s['trace'] == t: by_parent[s['parent']].append(s)
def tree(s): return {'name': s['name'], 'kind': s['kind'], 'duration_ms': s['duration_ms'], 'port': s['attributes'].get('server.port'), 'children': [tree(c) for c in sorted(by_parent[s['span']], key=lambda c: c['name'])]}
metrics = {}
for l in open(me):
    for rm in json.loads(l).get('resourceMetrics', []):
        if {a['key']: av(a) for a in rm['resource'].get('attributes', [])}.get('service.name') != svc: continue
        for sm in rm.get('scopeMetrics', []):
            for m in sm.get('metrics', []):
                kind = next(k for k in ('sum', 'gauge', 'histogram', 'exponentialHistogram') if k in m)
                e = metrics.setdefault(m['name'], {'unit': m.get('unit'), 'type': kind, 'attributes': set()})
                for dp in m[kind].get('dataPoints', []): e['attributes'] |= {a['key'] for a in dp.get('attributes', [])}
for e in metrics.values(): e['attributes'] = sorted(e['attributes'])
json.dump({'resource': resource, 'span_counts': dict(collections.Counter(f"{s['kind']} {s['name']}" for s in spans).most_common()), 'examples': examples,
           'heavy_home_trace': [tree(s) for s in by_parent[''] ] if t else None, 'metrics': metrics}, open(out, 'w'), indent=1)
print(len(spans), 'spans;', len(examples), 'span types;', len(metrics), 'metrics')
