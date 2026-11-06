#!/usr/bin/env bash
# With arguments, run them as a one-off (for example `php artisan migrate
# --force` in a Job). Without, build Laravel's caches and serve.
set -euo pipefail
cd /var/www/html

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

# Runtime configuration arrives as environment variables, so the config cache
# can only be built once the container sees them. None of these touch the
# database, so the pod starts even while MySQL is unreachable.
php artisan config:cache
php artisan route:cache
php artisan view:cache

# exec makes FrankenPHP PID 1, so the TERM Kubernetes sends reaches Caddy,
# which drains in-flight requests and exits 0.
exec frankenphp run --config /etc/frankenphp/Caddyfile --adapter caddyfile
