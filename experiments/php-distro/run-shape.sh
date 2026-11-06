#!/bin/sh
# usage: LOCK=<dir> OUT=<dir> run-shape.sh <heavy|light> <pairs>   (holds the timing lock only around the measurement)
shape=$1; pairs=$2; here=$(cd "$(dirname "$0")" && pwd)
until mkdir "$LOCK" 2>/dev/null; do sleep 15; done
trap 'rmdir "$LOCK"' EXIT INT TERM
docker run --rm --network f1-found306-perf -v "$here/measure.py":/m.py:ro -v "$OUT":/o python:3.13-slim \
  python /m.py "$shape" "$pairs" "/o/$shape.json" baseline distro distro-ratio distro-pdoff distro-ratio-pdoff distro-lite distro-ratio-lite
