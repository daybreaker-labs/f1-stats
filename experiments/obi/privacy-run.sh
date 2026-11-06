#!/bin/sh
# usage: OUT=<results dir> RAW=<scratch dir> privacy-run.sh
# For each OBI/collector configuration: restart both with that config, send privacy-traffic.sh to the selected
# container, wait for the 15 s batch, then (1) privacy.py over the attributes with the planted literals and
# (2) a raw grep -F over the exported OTLP JSON for every planted literal plus the real CSRF token and session
# cookie values of that traffic run (counts only; the values are never printed). Raw exports stay in RAW.
# querytext opts in to db.query.text to show what that attribute would expose; it is expected to fail.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
PLANTED="privacy-token-value privacy-plain-value privacy-season-value privacy-cookie-like privacy-password-value privacy-header-csrf privacy-cookie-value privacy-path-token-value home-fixture@example.test home-fixture%40example.test home-fixture-password 987654"
sed 's/exclude: \[url.query\]/include: [db.query.text]\n      exclude: [url.query]/' "$here/obi-private.yaml" > "$RAW/obi-querytext.yaml"
for case in default:obi.yaml:collector.yaml private:obi-private.yaml:collector.yaml private-scrub:obi-private.yaml:collector-scrub.yaml querytext:QT:collector-scrub.yaml; do
  name=${case%%:*}; rest=${case#*:}; obi=${rest%%:*}; col=${rest#*:}
  [ "$obi" = QT ] && obicfg="$RAW/obi-querytext.yaml" || obicfg="$here/$obi"
  mkdir -p "$RAW/$name/out"; rm -f "$RAW/$name/out/"*.jsonl; chmod 777 "$RAW/$name/out"
  docker rm -f f1x-obi f1x-collector >/dev/null 2>&1 || true
  docker run -d --name f1x-collector --network f1-found306-perf --cpus 1 -v "$here/$col":/etc/otelcol-contrib/config.yaml:ro -v "$RAW/$name/out":/out otel/opentelemetry-collector-contrib:0.162.0 >/dev/null
  docker run -d --name f1x-obi --privileged --pid=host --network f1-found306-perf -v /var/run/docker.sock:/var/run/docker.sock:ro \
    -v "$obicfg":/config/obi.yaml:ro -e OTEL_EBPF_CONFIG_PATH=/config/obi.yaml otel/ebpf-instrument:v1.0.0 >/dev/null
  until [ "$(docker logs f1x-obi 2>&1 | grep -c 'instrumenting process')" -ge 3 ]; do sleep 2; done; sleep 5
  sh "$here/privacy-traffic.sh" f1x-fix-obi >/dev/null
  sleep 25; docker stop f1x-collector >/dev/null
  python3 "$here/privacy.py" "$RAW/$name/out/traces.jsonl" "$RAW/$name/out/metrics.jsonl" "$OUT/privacy-$name.json" $PLANTED >/dev/null || true
  live=$(docker exec f1x-fix-obi sh -c "cat /tmp/ptk; awk '\$6 ~ /session|XSRF/ {print \$7}' /tmp/pcj.mid")
  { for v in $PLANTED; do printf 'planted %s %s\n' "$v" "$(cat "$RAW/$name/out/"*.jsonl | grep -cF -- "$v" || true)"; done
    i=0; for v in $live; do i=$((i+1)); printf 'live-value-%s %s\n' "$i" "$(cat "$RAW/$name/out/"*.jsonl | grep -cF -- "$v" || true)"; done
  } > "$OUT/privacy-$name-rawgrep.txt"
  python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(sys.argv[2],d['scanned'],'pass' if d['pass'] else 'fail',sorted({k.split(':',1)[1] for k in d['hits']}))" "$OUT/privacy-$name.json" "$name"
  awk '$2>0' "$OUT/privacy-$name-rawgrep.txt" | sed "s/^/  raw lines matching: /"
done
