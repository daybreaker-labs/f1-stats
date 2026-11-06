#!/bin/sh
# usage: APP=<main|fix> LOCK=<dir> OUT=<dir> run-shape-exec.sh <heavy|light> <pairs>
shape=$1; pairs=$2; here=$(cd "$(dirname "$0")" && pwd)
until mkdir "$LOCK" 2>/dev/null; do sleep 15; done
trap 'rmdir "$LOCK"' EXIT INT TERM
python3 "$here/measure_exec.py" "$shape" "$pairs" "$OUT/exec-$shape.json" baseline distro distro-ratio distro-pdoff distro-ratio-pdoff distro-lite distro-ratio-lite
