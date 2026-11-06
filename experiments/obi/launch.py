#!/usr/bin/env python3
"""Start the two app containers for the OBI experiment with the Distro experiment's pod limits
(1 CPU / 768 MiB, no swap, read-only root, tmpfs /tmp, volumes for storage and bootstrap/cache).
Both run the same uninstrumented image (f1x:<APP>-baseline): OBI is out of process, so the only
difference between `baseline` and `obi` is whether the OBI container selects that container.
  APP=fix ENVFILE=fixture.env launch.py [variant ...]"""
import os, subprocess, sys, json
APP = os.environ.get('APP', 'fix')
here = os.path.dirname(os.path.abspath(__file__))
envfile = os.environ.get('ENVFILE', os.path.join(here, 'fixture.env'))
common = ['APP_ENV=production', 'APP_DEBUG=false', 'APP_URL=http://home.fixture.test', 'SESSION_DRIVER=file',
          'SESSION_SECURE_COOKIE=false', 'CACHE_STORE=file', 'CACHE_DRIVER=file', 'LOG_CHANNEL=stderr']
variants = {'baseline': f'f1x:{APP}-baseline', 'obi': f'f1x:{APP}-baseline'}
for name in sys.argv[1:] or list(variants):
    image = variants[name]; cn = f'f1x-{APP}-{name}'
    subprocess.run(['docker', 'rm', '-f', cn], capture_output=True)
    for v in ('storage', 'cache'):
        subprocess.run(['docker', 'volume', 'rm', '-f', f'{cn}-{v}'], capture_output=True)
        subprocess.run(['docker', 'volume', 'create', f'{cn}-{v}'], capture_output=True, check=True)
    args = ['docker', 'run', '-d', '--name', cn, '--network', 'f1-found306-perf', '--cpus', '1', '--memory', '768m', '--memory-swap', '768m',
            '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m,uid=33,gid=33,mode=1777',
            '--mount', f'type=volume,src={cn}-storage,dst=/var/www/html/storage',
            '--mount', f'type=volume,src={cn}-cache,dst=/var/www/html/bootstrap/cache',
            '--mount', f'type=bind,src={here}/home-start.sh,dst=/opt/home-start.sh,readonly', '--env-file', envfile]
    for e in common: args += ['-e', e]
    args += ['--entrypoint', 'sh', image, '/opt/home-start.sh']
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
    print(json.dumps({'container': cn, 'image': image}))
