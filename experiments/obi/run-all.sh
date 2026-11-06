#!/bin/sh
# usage: LOCK=<dir> OUT=<dir> run-all.sh      (each step takes and releases the timing lock itself)
# Order: OBI idle, on/off cross-talk control (heavy, light), paired baseline-vs-obi runs (heavy, light),
# measurement-path floor. OBI must be running and selecting only f1x-<APP>-obi.
set -eu
here=$(cd "$(dirname "$0")" && pwd); export APP=${APP:-fix}
export OBI_CG=/hcg/docker/$(docker inspect -f '{{.Id}}' f1x-obi)
uptime > "$OUT/host-load-start.txt"
python3 "$here/probes.py" idle 60 "$OUT/obi-idle.json"
python3 "$here/onoff.py" heavy 10 "$OUT/onoff-heavy.json"
python3 "$here/onoff.py" light 10 "$OUT/onoff-light.json"
python3 "$here/measure_exec.py" heavy 16 "$OUT/exec-heavy.json" baseline obi
python3 "$here/measure_exec.py" light 16 "$OUT/exec-light.json" baseline obi
python3 "$here/probes.py" floor 10 "$OUT/floor.json"
uptime > "$OUT/host-load-end.txt"
