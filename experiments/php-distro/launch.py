#!/usr/bin/env python3
"""Start one app container per variant with identical limits (1 CPU / 768 MiB, read-only root).
Usage: launch.py [--collector HOST]   env file path via ENVFILE, scripts dir = this dir."""
import os, subprocess, sys, json
APP = os.environ.get('APP', 'main')   # app version tag of the images: f1x:<APP>-baseline / f1x:<APP>-distro
here = os.path.dirname(os.path.abspath(__file__))
envfile = os.environ['ENVFILE']          # synthetic DB settings, no OTEL_* lines
collector = os.environ.get('COLLECTOR', 'f1-found306-perf-collector')
common = ['APP_ENV=production','APP_DEBUG=false','APP_URL=http://home.fixture.test','SESSION_DRIVER=file',
          'SESSION_SECURE_COOKIE=false','CACHE_STORE=file','CACHE_DRIVER=file','LOG_CHANNEL=stderr']
otel = ['OTEL_SERVICE_NAME=f1-stats','OTEL_RESOURCE_ATTRIBUTES=deployment.environment=local-fixture',
        f'OTEL_EXPORTER_OTLP_ENDPOINT=http://{collector}:4318','OTEL_EXPORTER_OTLP_INSECURE=true']
variants = {
  'baseline':     (f'f1x:{APP}-baseline', []),
  'distro':       (f'f1x:{APP}-distro', otel),
  'distro-ratio': (f'f1x:{APP}-distro', otel + ['OTEL_TRACES_SAMPLER=traceidratio','OTEL_TRACES_SAMPLER_ARG=0.1']),
  'distro-pdoff': (f'f1x:{APP}-distro', otel + ['OTEL_PHP_DISABLED_INSTRUMENTATIONS=pdo']),
  'distro-ratio-pdoff': (f'f1x:{APP}-distro', otel + ['OTEL_TRACES_SAMPLER=traceidratio','OTEL_TRACES_SAMPLER_ARG=0.1','OTEL_PHP_DISABLED_INSTRUMENTATIONS=pdo']),
  'distro-lite': (f'f1x:{APP}-distro', otel + ['OTEL_PHP_DISABLED_INSTRUMENTATIONS=pdo,laravel']),
  'distro-ratio-lite': (f'f1x:{APP}-distro', otel + ['OTEL_TRACES_SAMPLER=traceidratio','OTEL_TRACES_SAMPLER_ARG=0.1','OTEL_PHP_DISABLED_INSTRUMENTATIONS=pdo,laravel']),
}
only = sys.argv[1:] or list(variants)
for name in only:
    image, extra = variants[name]
    cn = f'f1x-{APP}-' + name
    subprocess.run(['docker','rm','-f',cn], capture_output=True)
    for v in ('storage','cache'):
        subprocess.run(['docker','volume','create',f'{cn}-{v}'], capture_output=True, check=True)
    args = ['docker','run','-d','--name',cn,'--network','f1-found306-perf','--cpus','1','--memory','768m','--memory-swap','768m',
            '--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=64m,uid=33,gid=33,mode=1777',
            '--mount',f'type=volume,src={cn}-storage,dst=/var/www/html/storage',
            '--mount',f'type=volume,src={cn}-cache,dst=/var/www/html/bootstrap/cache',
            '--mount',f'type=bind,src={here}/home-start.sh,dst=/opt/home-start.sh,readonly','--env-file',envfile]
    for e in common + extra: args += ['-e', e]
    args += ['--entrypoint','sh',image,'/opt/home-start.sh']
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
    print(json.dumps({'container': cn, 'image': image, 'env': extra}))
