# OpenTelemetry eBPF Instrumentation (OBI) v1.0.0 offline /home results (2026-11-06)

App image `f1x:fix-baseline` (`sha256:a122753af4c4`, built 2026-11-06 from f1_2022 `fix` = FOUND-329 branch tip, the same image as the Distro run's `fix` rows), unchanged for both arms. OBI `otel/ebpf-instrument:v1.0.0` (`sha256:a68d70e93426...`), privileged, `--pid=host`, Docker socket read-only, config `obi.yaml`, no CPU limit. Docker Desktop 29.9.2, linuxkit kernel 7.0.14 aarch64 with `/sys/kernel/btf/vmlinux`, Apple M5 Pro, macOS 27.2. MySQL 8.4.13, collector contrib 0.162.0 (local file exporter). App containers: 1 CPU, 768 MiB, no swap, read-only root. Timing lock `/tmp/f1-stats-timing.lock`.

Wall = curl time_total; CPU = app container cgroup usage_usec delta (1 s settle), which includes in-kernel eBPF probe time because probes run in the app's context. OBI CPU = OBI container cgroup delta over the same window (userspace: ring-buffer reads, parsing, export). Medians over n paired, alternating requests; p95 = value at rank ceil(0.95·n), which for n = 8–19 is the maximum, so the p95 columns are single-sample maxima and the tail overhead is not assessed (light's negative p95 change comes from one 173 ms baseline outlier).

Fixture: rebuilt with `seed.py` (the Distro seed was not kept): heavy = 5000 races, 100,000 results, 250 titles; light = 500 races, 10,000 results, 0 titles. Absolute times therefore differ from the Distro table; compare the relative columns, and the same-fixture Distro reference below.

## Paired baseline vs OBI (OBI running, selecting only `f1x-fix-obi`)

| shape | n | variant | wall med ms | wall p95 ms | wall med % | wall p95 % | CPU med ms | CPU p95 ms | CPU med % | CPU p95 % | OBI CPU ms per window (bursty, see below) | identical, all 200 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| light | 16 | baseline | 127 | 173 | +0.0 | +0.0 | 92.4 | 131.0 | +0.0 | +0.0 | 8.1 | True |
| light | 16 | obi | 127 | 151 | +0.1 | -12.6 | 92.9 | 110.7 | +0.6 | -15.5 | 9.1 | True |
| heavy | 16 | baseline | 842 | 850 | +0.0 | +0.0 | 679.5 | 684.4 | +0.0 | +0.0 | 8.3 | True |
| heavy | 16 | obi | 840 | 873 | -0.2 | +2.7 | 680.1 | 697.6 | +0.1 | +1.9 | 11.9 | True |

OBI's own CPU runs outside the app pod, so it does not count against the app's 5% budget. Idle (60 s, no traffic): 8.5 ms per second, about 0.85% of one core; a second idle reading (`obi-load.json`) gave 11.0 ms/s. OBI works in bursts (OTLP metric export every 10 s, trace batches every 15 s, and work for one request can land in the next window), so the per-window column above is not a per-request cost. `probes.py load` measured whole phases instead: 30 back-to-back heavy `/home` requests to the selected container cost OBI 336 ms over 47 s, and 30 to the unselected one 341 ms over 46 s; both are below the idle rate times elapsed. OBI's per-request userspace work is therefore below this method's resolution (a few ms at most per heavy request); its cost is dominated by the fixed background rate.

OBI memory (cgroup, after the heavy run): current 255 MiB, peak 281 MiB; of which kernel (BPF maps) 191 MiB, anon 28 MiB, page cache 4 KiB.

Measurement floor (`probes.py floor`, /healthz through the same docker exec + curl + settle path, n=10): 23.3 ms CPU baseline, 23.9 ms obi. It is in every CPU figure above, so light's app-only CPU is about 69 ms and its relative overheads are diluted by about a quarter.

Timing used the default `obi.yaml`. The privacy settings act in OBI's userspace (attribute selection, route naming) and in the collector, so they are assumed, not measured, to leave the app-side cost unchanged.

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

The Distro record's own fixture gave +25% (light) and +47% (heavy) CPU for these defaults; this fixture gives less, so it is a gentler test. OBI stays within 5% on both shapes: the paired medians are +0.1% and +0.6% CPU, and the stricter on/off control (OBI really stopped vs running, n = 5 per state, OBI freshly restarted before each on-block) gives +2.6% CPU for the selected heavy container and +0.8% for the unselected one, which n = 5 cannot separate. Best estimate: 0–3% CPU on `/home`.

## Signals and privacy

`span-metric-sample.json`: one example per span type, a full heavy `/home` trace, and the metric inventory, from the timed traffic (default `obi.yaml`).

`privacy-run.sh` (committed invocation) restarts OBI and the collector per configuration, sends `privacy-traffic.sh` to the selected container (query strings with sensitive and plain keys, login POST, Cookie and X-CSRF-TOKEN headers, IDs, an email and a token-like value as path segments), then runs `privacy.py` (every resource, span, event and data-point attribute and span name, with the planted literals) and a raw `grep -F` over the whole OTLP export for each planted literal and for the run's real CSRF token and `laravel_session` / `XSRF-TOKEN` cookie values (`privacy-<case>-rawgrep.txt`, counts only).

| case | config | spans / data points | attribute scan | raw grep: planted or live values found |
|---|---|---|---|---|
| default | `obi.yaml`, plain collector | 109 / 201 | fail: metric:http.route, span:http.route, span:name, span:url.full, span:url.path, span:url.query | `privacy-plain-value`, `privacy-season-value`, `privacy-cookie-like`, `privacy-path-token-value`, `home-fixture@example.test`, `home-fixture%40example.test`, `987654`, the live CSRF token (sent as `_token=` in a query string) |
| private | `obi-private.yaml` (traces exclude `url.query`; `routes.unmatched: wildcard`), plain collector | 109 / 159 | fail: span:url.full, span:url.path | `privacy-plain-value`, `privacy-season-value`, `privacy-cookie-like`, `privacy-path-token-value`, `home-fixture@example.test`, `home-fixture%40example.test`, `987654`, the live CSRF token (sent as `_token=` in a query string) |
| private-scrub | `obi-private.yaml` + `collector-scrub.yaml` (delete `url.full`, `url.path`, `url.query`) | 109 / 159 | pass | none |
| querytext | as private-scrub, plus `db.query.text` opted in | 109 / 159 | fail: span:db.query.text | none |

- Never exported in any case: cookies (live session and XSRF cookie values: 0 matches), the Cookie and X-CSRF-TOKEN headers, the login POST body (password, email form field), response bodies, and SQL text unless `db.query.text` is opted in.
- Defaults leak query strings: `url.query` (php-fpm span) and `url.full` (nginx FastCGI client span) keep every value whose key is not on OBI's redaction list (`token` and `password` were redacted; `_token`, `email`, `q` were not). The `heuristic` route matcher also turned a one-off path segment into an nginx route, so it reached span names and the `http.route` attribute of every `http.*` metric.
- OBI v1.0.0 honours `attributes.select.traces.exclude` for `url.query` only; `url.full` on client spans and `url.path` remain, so the collector deletes them. With that, traces keep the method, status, `http.route` (Laravel templates such as `/paises/show/{id}` on php-fpm spans; `/**` for unmatched nginx paths) and `db.query.summary`.
- `db.query.text` (opt-in) shows `?` for bound values but inlines Laravel's eager-loading ID lists (`... where pilotos.id in (1)`; 21 of 54 statements had literals), so it must stay off.
- The MySQL span of the 100,000-row join is a bare `SELECT` (no `db.query.summary`) lasting about 0.7 ms inside a ~900 ms request (three privacy-run requests: 0.63–0.79 ms). OBI's MySQL span appears to end at the first response packet (inference), so it does not show the time spent transferring and fetching a large result; for `/home`, where that is most of the work, the spans show the queries but not where the time goes.
