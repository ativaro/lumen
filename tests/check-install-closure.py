#!/usr/bin/python3
"""Check both installer payloads and a user update in disposable directories."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]
ASSETS = ('translations', 'qml', 'fonts', 'notes_icons', 'memory-runtime')


def check(root, applications):
    count = 0
    for directory in ASSETS:
        for source in (REPO/'files'/directory).rglob('*'):
            if not source.is_file() or '__pycache__' in source.parts or source.suffix == '.pyc': continue
            target = root/'files'/source.relative_to(REPO/'files')
            assert target.read_bytes() == source.read_bytes(), str(target)
            count += 1
    manifest = json.loads((root/'install.json').read_text())
    assert manifest['source_url'] == 'https://forge.example.invalid/ativaro/lumen.git'
    assert manifest['revision'] == subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    for desktop in applications.glob('*.desktop'):
        result = subprocess.run(['desktop-file-validate', str(desktop)], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
    return count


with tempfile.TemporaryDirectory(prefix='lumen-install-closure-') as tmp:
    home = Path(tmp); runtime = home/'runtime'; runtime.mkdir(mode=0o700)
    env = dict(PATH='/usr/bin:/bin', HOME=tmp, LANG='C.UTF-8', QT_QPA_PLATFORM='offscreen',
               XDG_CONFIG_HOME=str(home/'config'), XDG_DATA_HOME=str(home/'data'),
               XDG_CACHE_HOME=str(home/'cache'), XDG_STATE_HOME=str(home/'state'),
               XDG_RUNTIME_DIR=str(runtime), DBUS_SESSION_BUS_ADDRESS='unix:path=/nonexistent',
               DBUS_SYSTEM_BUS_ADDRESS='unix:path=/nonexistent',
               LUMEN_SOURCE_URL='https://forge.example.invalid/ativaro/lumen.git')
    command = ['bash', str(REPO/'install.sh'), '--no-mcp', '--no-timer']
    with (home/'installer.log').open('w+') as log:
        def run(args, extra=None):
            result = subprocess.run(args, cwd=REPO, env=env | (extra or {}), stdout=log, stderr=subprocess.STDOUT, timeout=180)
            if result.returncode:
                log.seek(0); raise AssertionError(log.read()[-6000:])
        run(command)
        prefix = home/'data/lumen'
        count = check(prefix, home/'data/applications')
        # A normal app update must retain data, native opt-in and disabled timers.
        preserved = (home/'data/lumen-tools/workbench/synthetic.md',
                     home/'config/lumen-server/connection.json', prefix/'vault-lab/bin/lumen-vault-lab')
        for path in preserved:
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'synthetic-preserved')
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in preserved}
        run(command)
        assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in preserved}
        assert not list((home/'config/systemd/user').glob('*.wants/lumen-*.timer'))
        check(prefix, home/'data/applications')

        source = home/'arch-source'; source.mkdir(); (source/'lumen-1.2.0').symlink_to(REPO)
        package = home/'package'
        run(['bash', '-ec', 'source "$1"; package', 'package-check', str(REPO/'packaging/arch/PKGBUILD')],
            dict(LOCALSRC='1', LUMEN_SOURCE_SHA256='0'*64, srcdir=str(source), pkgdir=str(package)))
        check(package/'usr/share/lumen', package/'usr/share/applications')
        assert not (package/'usr/share/lumen/vault-lab').exists()
        print(json.dumps(dict(user_install='pass', user_update_preservation='pass',
                              arch_payload='pass', asset_files=count,
                              note='Payload check; no pacman installation or desktop session acceptance.')))
