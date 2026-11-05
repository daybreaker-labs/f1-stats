# syntax=docker/dockerfile:1
# F1 Stats (viniciusmelchior/f1_2022), packaged unchanged for the arm64 OKE
# workers. The upstream checkout arrives as the named build context `app`; the
# workflow pins and verifies its commit, so this file never fetches source.
#
#   docker buildx build --platform linux/arm64 \
#     --build-context app=<upstream checkout> --build-arg UPSTREAM_SHA=<sha> \
#     --build-arg PACKAGING_SHA=<sha of this directory's latest commit> \
#     images/f1-stats
#
# One container runs nginx and php-fpm under entrypoint.sh: nginx needs the
# same public/ tree php-fpm serves, and a single process tree gives Traefik one
# port and the probes one path through both servers.
FROM docker.io/library/composer:2.10.2@sha256:d020706319701a44468968321dccd0fce6620190159a7a9ec195d78e6e971c71 AS composer

# PHP 8.4 runs past Laravel 13's security support. 8.5 is not usable yet: the
# PhpSpreadsheet 1.x that maatwebsite/excel 3.1 requires declares <8.5.
FROM docker.io/library/php:8.4-fpm-trixie@sha256:3a6527017daca7917709afa08a37388ec108db093857f31d642cfff2e6f0449e AS runtime
# Freeze Debian package resolution as well as the base image. The snapshot is
# the one the base image was built from: an older one fails on packages the base
# already holds at a newer version.
RUN rm -f /etc/apt/sources.list /etc/apt/sources.list.d/* \
    && printf '%s\n' \
        'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20261027T000000Z trixie main' \
        'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20261027T000000Z trixie-updates main' \
        'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian-security/20261027T000000Z trixie-security main' \
        > /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        nginx libfreetype6 libjpeg62-turbo libpng16-16t64 libzip5 \
        libfreetype-dev libjpeg62-turbo-dev libpng-dev libzip-dev \
    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install -j"$(nproc)" gd pdo_mysql zip \
    && apt-get purge -y libfreetype-dev libjpeg62-turbo-dev libpng-dev libzip-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled /etc/nginx/conf.d /var/www/html \
    && cp /usr/local/etc/php/php.ini-production /usr/local/etc/php/php.ini \
    # php-fpm runs unprivileged, where these directives only produce warnings.
    && sed -i -e '/^user = /d' -e '/^group = /d' /usr/local/etc/php-fpm.d/www.conf \
    && install -d -o www-data -g www-data /tmp/nginx
RUN apt-get update \
    && apt-get install -y --no-install-recommends $PHPIZE_DEPS \
    && pecl install opentelemetry-1.4.2 \
    && docker-php-ext-enable opentelemetry \
    && apt-get purge -y --auto-remove $PHPIZE_DEPS \
    && rm -rf /var/lib/apt/lists/* /tmp/pear
COPY nginx.conf /etc/nginx/nginx.conf
COPY php.ini /usr/local/etc/php/conf.d/zz-f1-stats.ini
COPY php-fpm.conf /usr/local/etc/php-fpm.d/zz-f1-stats.conf
COPY --chmod=0755 entrypoint.sh /usr/local/bin/f1-stats-entrypoint

FROM runtime AS build
COPY --from=composer /usr/bin/composer /usr/local/bin/composer
COPY --from=app . /src
COPY telemetry /src/telemetry
WORKDIR /src
# post-autoload-dump runs artisan package:discover, which boots the application
# and therefore needs the runtime extensions installed above.
ENV COMPOSER_ALLOW_SUPERUSER=1
RUN rm -rf .git .github \
    && composer install --no-dev --no-interaction --no-progress \
        --optimize-autoloader --classmap-authoritative \
    && php telemetry/install.php \
    && composer dump-autoload --no-dev --optimize --classmap-authoritative \
    && composer check-platform-reqs --no-dev \
    && php -d zend.assertions=1 -d assert.exception=1 telemetry/privacy-test.php \
    && rm -f /usr/local/bin/composer

FROM runtime
ARG UPSTREAM_SHA
ARG PACKAGING_SHA
ARG UPSTREAM_REPO=viniciusmelchior/f1_2022
LABEL org.opencontainers.image.source="https://github.com/${UPSTREAM_REPO}" \
      org.opencontainers.image.revision="${UPSTREAM_SHA}" \
      org.opencontainers.image.title="f1-stats"
RUN test -n "$UPSTREAM_SHA" && test -n "$PACKAGING_SHA" \
    && sed -i -e "s/__UPSTREAM_SHA__/$UPSTREAM_SHA/" -e "s/__PACKAGING_SHA__/$PACKAGING_SHA/" /etc/nginx/nginx.conf
COPY --from=build /src /var/www/html
WORKDIR /var/www/html
RUN chown -R www-data:www-data storage bootstrap/cache
# Containers log to stderr; a Secret may still override it.
ENV LOG_CHANNEL=stderr
USER 33:33
EXPOSE 8080
# The base image stops with SIGQUIT; the entrypoint handles TERM, INT and QUIT
# alike, and TERM is what Kubernetes and most tooling expect.
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/f1-stats-entrypoint"]
CMD []
