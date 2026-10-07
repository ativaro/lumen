"""Preserve legacy package reports and service preferences around pacman replacement."""
from lumen_i18n import tr
import json
import os
from pathlib import Path
import subprocess
import sys
from lumen_migrate import copy_missing

STATE = Path('/var/lib/lumen/legacy-upgrade.json')
SYSTEM = ['lumen-agentd.service', 'lumen-watch.timer']
USER = ['lumen-notify.path', 'lumen-digest.timer', 'lumen-nightly.timer']


def run(args):
    return subprocess.run(args, text=True, capture_output=True, timeout=30)


def before():
    if run(['pacman', '-Qq', 'opencode-lumen']).stdout.strip() != 'opencode-lumen': return
    copy_missing('/var/lib/opencode-lumen', '/var/lib/lumen')
    scopes = [([], SYSTEM), (['--global'], USER)]
    scopes += [(['--machine=' + p.name + '@.host', '--user'], USER)
               for p in Path('/run/user').iterdir() if p.name.isdigit() and (p / 'bus').exists()]
    records = []
    for scope, units in scopes:
        for unit in units:
            base = ['systemctl', *scope]
            enabled = run([*base, 'is-enabled', unit]).stdout.strip()
            active = False if scope == ['--global'] else run([*base, 'is-active', unit]).stdout.strip() == 'active'
            records.append(dict(scope=scope, unit=unit, enabled=enabled, active=active))
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with STATE.open('w') as stream: os.fchmod(stream.fileno(), 0o600); json.dump(records, stream)


def after():
    if not STATE.is_file(): return
    records = json.loads(STATE.read_text()); errors = []
    for record in records:
        base = ['systemctl', *record['scope']]; unit = record['unit']
        if record['scope'] != ['--global']: run([*base, 'daemon-reload'])
        state = record['enabled']
        if state in ('enabled', 'enabled-runtime', 'masked', 'masked-runtime', 'disabled'):
            action = 'mask' if state.startswith('masked') else 'enable' if state.startswith('enabled') else 'disable'
            runtime = ['--runtime'] if state.endswith('-runtime') else []
            result = run([*base, *runtime, action, unit])
            if result.returncode: errors.append(unit + ': ' + result.stderr.strip())
        if record['active']:
            result = run([*base, 'start', unit])
            if result.returncode: errors.append(unit + ': ' + result.stderr.strip())
    if errors: raise RuntimeError('\n'.join(errors))
    STATE.rename(STATE.with_suffix('.done.json'))


if __name__ == '__main__':
    if os.geteuid() != 0: raise SystemExit(tr('Paketmigration benötigt root.'))
    if sys.argv[1:] == ['before']: before()
    elif sys.argv[1:] == ['after']: after()
    else: raise SystemExit(tr('Aufruf: lumen_upgrade.py before|after'))
