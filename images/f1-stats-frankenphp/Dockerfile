# syntax=docker/dockerfile:1
# EXPERIMENT: F1 Stats served by FrankenPHP in classic (non-worker) mode
# instead of nginx + php-fpm + a bash supervisor. Same build contract as
# images/f1-stats:
#
#   docker buildx build --platform linux/arm64 \
#     --build-context app=<upstream checkout> --build-arg UPSTREAM_SHA=<sha> \
#     --build-arg PACKAGING_SHA=<sha> images/f1-stats-frankenphp
FROM docker.io/library/composer:2.10.2@sha256:d020706319701a44468968321dccd0fce6620190159a7a9ec195d78e6e971c71 AS composer

# FrankenPHP v1.13.5, PHP 8.4.27 (ZTS), Caddy v2.11.9. The base image was built
# from the Debian snapshot 20261104T212339Z, which the apt sources below reuse.
FROM docker.io/dunglas/frankenphp:php8.4-trixie@sha256:08af88488ce218936d530b80f6f55dc2afe4d0d91f13f9e6ae350a9e7752128e AS runtime
COPY apt.conf /etc/apt/apt.conf.d/80-f1-build
RUN rm -f /etc/apt/sources.list /etc/apt/sources.list.d/* \
    && printf '%s\n' \
        'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20261104T212339Z trixie main' \
        'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20261104T212339Z trixie-updates main' \
        'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian-security/20261104T212339Z trixie-security main' \
        > /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libfreetype6 libjpeg62-turbo libpng16-16t64 libzip5 \
        libfreetype-dev libjpeg62-turbo-dev libpng-dev libzip-dev \
    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install -j"$(nproc)" gd pdo_mysql zip \
    && apt-get purge -y libfreetype-dev libjpeg62-turbo-dev libpng-dev libzip-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* \
    && cp /usr/local/etc/php/php.ini-production /usr/local/etc/php/php.ini \
    # The file capability lets Caddy bind ports 80 and 443; with every
    # capability dropped it would stop the binary from executing at all.
    && setcap -r /usr/local/bin/frankenphp
COPY php.ini /usr/local/etc/php/conf.d/zz-f1-stats.ini
COPY healthz.php /opt/f1-stats/health/healthz.php
COPY Caddyfile /etc/frankenphp/Caddyfile
COPY --chmod=0755 entrypoint.sh /usr/local/bin/f1-stats-entrypoint

FROM runtime AS build
COPY --from=composer /usr/bin/composer /usr/local/bin/composer
COPY --from=app . /src
WORKDIR /src
ENV COMPOSER_ALLOW_SUPERUSER=1
RUN rm -rf .git .github \
    && composer install --no-dev --no-interaction --no-progress \
        --optimize-autoloader --classmap-authoritative \
    && composer check-platform-reqs --no-dev \
    && rm -f /usr/local/bin/composer

FROM runtime
ARG UPSTREAM_SHA
ARG PACKAGING_SHA
ARG UPSTREAM_REPO=viniciusmelchior/f1_2022
LABEL org.opencontainers.image.source="https://github.com/${UPSTREAM_REPO}" \
      org.opencontainers.image.revision="${UPSTREAM_SHA}" \
      org.opencontainers.image.title="f1-stats"
RUN test -n "$UPSTREAM_SHA" && test -n "$PACKAGING_SHA" \
    && sed -i -e "s/__UPSTREAM_SHA__/$UPSTREAM_SHA/" -e "s/__PACKAGING_SHA__/$PACKAGING_SHA/" /etc/frankenphp/Caddyfile
COPY --from=build /src /var/www/html
WORKDIR /var/www/html
RUN chown -R www-data:www-data storage bootstrap/cache
# Containers log to stderr; a Secret may still override it. Caddy's own
# config and data directories go under /tmp, the pod's writable emptyDir.
ENV LOG_CHANNEL=stderr \
    XDG_CONFIG_HOME=/tmp/caddy-config \
    XDG_DATA_HOME=/tmp/caddy-data
USER 33:33
EXPOSE 8080
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/f1-stats-entrypoint"]
CMD []
