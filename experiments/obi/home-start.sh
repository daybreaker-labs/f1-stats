#!/bin/sh
set -eu
mkdir -p /tmp/nginx
exec /usr/local/bin/f1-stats-entrypoint
