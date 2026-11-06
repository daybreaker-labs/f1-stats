#!/bin/sh
# usage: APP=<main|fix> LOCK=<dir> OUT=<dir> run-shape-exec.sh <heavy|light> <pairs>
# measure_exec.py acquires and releases LOCK itself.
shape=$1; pairs=$2; here=$(cd "$(dirname "$0")" && pwd)
exec python3 "$here/measure_exec.py" "$shape" "$pairs" "$OUT/exec-$shape.json" baseline distro distro-ratio distro-pdoff distro-ratio-pdoff distro-lite distro-ratio-lite
