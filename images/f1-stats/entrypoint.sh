#!/usr/bin/env bash
# With arguments, run them as a one-off (for example `php artisan migrate
# --force` in a Job). Without, build Laravel's caches and serve.
set -euo pipefail
cd /var/www/html
export OTEL_RESOURCE_ATTRIBUTES="${OTEL_RESOURCE_ATTRIBUTES:+$OTEL_RESOURCE_ATTRIBUTES,}service.version=$F1_STATS_VERSION"

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

# Runtime configuration arrives as environment variables, so the config cache
# can only be built once the container sees them. None of these touch the
# database, so the pod starts even while MySQL is unreachable.
php artisan config:cache
php artisan route:cache
php artisan view:cache

php-fpm --nodaemonize &
fpm=$!
nginx -g 'daemon off;' &
web=$!

# QUIT is the graceful shutdown signal for both servers.
stop() {
  kill -QUIT "$fpm" "$web" 2>/dev/null || true
}
requested=0
trap 'requested=1; stop' TERM INT QUIT

# Exit as soon as either server stops, so Kubernetes restarts the container
# instead of leaving nginx in front of a dead php-fpm or the reverse.
set +e
wait -n "$fpm" "$web"
status=$?
stop
wait
if [ "$requested" = 1 ]; then
  exit 0
fi
exit "$status"
