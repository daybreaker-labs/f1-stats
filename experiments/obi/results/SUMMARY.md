# OpenTelemetry eBPF Instrumentation (OBI) v1.0.0 offline /home results (2026-11-06)

App image `f1x:fix-baseline` (`sha256:a122753af4c4`, built 2026-11-06 from f1_2022 `fix` = FOUND-329 branch tip, the same image as the Distro run's `fix` rows), unchanged for both arms. OBI `otel/ebpf-instrument:v1.0.0` (`sha256:a68d70e93426...`), privileged, `--pid=host`, Docker socket read-only, config `obi.yaml`, no CPU limit. Docker Desktop 29.9.2, linuxkit kernel 7.0.14 aarch64 with `/sys/kernel/btf/vmlinux`, Apple M5 Pro, macOS 27.2. MySQL 8.4.13, collector contrib 0.162.0 (local file exporter). App containers: 1 CPU, 768 MiB, no swap, read-only root. Timing lock `/tmp/f1-stats-timing.lock`.

Wall = curl time_total; CPU = app container cgroup usage_usec delta (1 s settle), which includes in-kernel eBPF probe time because probes run in the app's context. OBI CPU = OBI container cgroup delta over the same window (userspace: ring-buffer reads, parsing, export). Medians over n paired, alternating requests; p95 = value at rank ceil(0.95·n), which for n = 8–19 is the maximum.

Fixture: rebuilt with `seed.py` (the Distro seed was not kept): heavy = 5000 races, 100,000 results, 250 titles; light = 500 races, 10,000 results, 0 titles. Absolute times therefore differ from the Distro table; compare the relative columns, and the same-fixture Distro reference below.

## Paired baseline vs OBI (OBI running, selecting only `f1x-fix-obi`)

| shape | n | variant | wall med ms | wall p95 ms | wall med % | wall p95 % | CPU med ms | CPU p95 ms | CPU med % | CPU p95 % | OBI CPU ms / request window | identical, all 200 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| light | 16 | baseline | 127 | 173 | +0.0 | +0.0 | 92.4 | 131.0 | +0.0 | +0.0 | 8.1 | True |
| light | 16 | obi | 127 | 151 | +0.1 | -12.6 | 92.9 | 110.7 | +0.6 | -15.5 | 9.1 | True |
| heavy | 16 | baseline | 842 | 850 | +0.0 | +0.0 | 679.5 | 684.4 | +0.0 | +0.0 | 8.3 | True |
| heavy | 16 | obi | 840 | 873 | -0.2 | +2.7 | 680.1 | 697.6 | +0.1 | +1.9 | 11.9 | True |

OBI idle (60 s, no traffic): 8.5 ms CPU per second. A request window lasts about 1.0–1.3 s (request + 1 s settle + cgroup reads), so the baseline rows' OBI column is OBI's idle cost; the obi-minus-baseline difference is OBI's per-request work: light 1.0 ms, heavy 3.5 ms.

OBI memory (cgroup, after the heavy run): current 255 MiB, peak 281 MiB; of which kernel (BPF maps) 191 MiB, anon 28 MiB, page cache 4 KiB.

Measurement floor (`probes.py floor`, /healthz through the same docker exec + curl + settle path, n=10): 23.3 ms CPU baseline, 23.9 ms obi. It is in every CPU figure above, so light's app-only CPU is about 69 ms and its relative overheads are diluted by about a quarter.

## Cross-talk control: OBI stopped vs running (`onoff.py`)

OBI's kprobes are global and its uprobes attach to the nginx and php-fpm inodes both containers share, so the unselected baseline might pay too. Blocks alternate OBI off/on (restart + attach wait between blocks); each block requests both containers once.

| shape | container | n off / on | wall med off → on ms | CPU med off → on ms | CPU Δ % | identical, all 200 |
|---|---|---|---|---|---|---|
| light | baseline | 5 / 5 | 129 → 132 | 92.2 → 93.3 | +1.2 | True |
| light | obi | 5 / 5 | 131 → 127 | 92.9 → 91.5 | -1.5 | True |
| heavy | baseline | 5 / 5 | 847 → 850 | 685.1 → 690.7 | +0.8 | True |
| heavy | obi | 5 / 5 | 843 → 853 | 677.7 → 695.2 | +2.6 | True |

## Same-fixture Distro reference (`f1x:fix-distro`, Distro 0.7.0 defaults, OBI still running but not selecting it)

| shape | n | variant | wall med ms | wall p95 ms | wall med % | CPU med ms | CPU med % | identical, all 200 |
|---|---|---|---|---|---|---|---|---|
| light | 8 | baseline | 132 | 143 | +0.0 | 94.3 | +0.0 | True |
| light | 8 | distro | 141 | 153 | +7.4 | 107.2 | +13.7 | True |
| heavy | 8 | baseline | 859 | 1265 | +0.0 | 696.0 | +0.0 | True |
| heavy | 8 | distro | 971 | 1034 | +13.1 | 804.1 | +15.5 | True |

The Distro record's own fixture gave +25% (light) and +47% (heavy) CPU for these defaults; this fixture gives less, so it is a gentler test, and OBI still sits within noise of 0%.

## Signals and privacy

`span-metric-sample.json`: one example per span type, a full heavy `/home` trace, and the metric inventory (from the timed traffic). `privacy-*.json`: scans of dedicated traffic from `privacy-traffic.sh` (query strings with sensitive and plain keys, login POST, Cookie and X-CSRF-TOKEN headers):

- `obi.yaml` (defaults), plain collector: 85 spans, 217 data points, **fail**: span:url.full, span:url.query
- `obi-private.yaml` (traces exclude `url.query`, `url.full`), plain collector: 85 spans, 128 data points, **fail**: span:url.full
- `obi-private.yaml` + `collector-scrub.yaml` (strip `?…` from `url.full`): 85 spans, 252 data points, **pass**

With `db.query.text` opted in (not committed; scratch run), statements show `?` for bound values but inline the integer ID lists of Laravel eager loading (`... in (1, 21, 41, ...)`), so that attribute must stay at its default (off).
