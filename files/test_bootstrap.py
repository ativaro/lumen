"""Run the streamed installer with local download/package stand-ins, never sudo."""
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

REPO = Path(__file__).resolve().parent.parent


class BootstrapTest(unittest.TestCase):
    def test_streamed_install_and_failures_preserve_user_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); mock = root / 'bin'; mock.mkdir()
            fixture = root / 'source.tar.gz'
            with tarfile.open(fixture, 'w:gz') as archive:
                for name, content in {
                    'install.sh': 'set -eu\nmkdir -p "$PREFIX/bin"\ncp "$(dirname "$0")/wizard" "$PREFIX/bin/lumen-setup-wizard"\n',
                    'wizard': '#!/bin/sh\nprintf "wizard\\n" >> "$TEST_EVENTS"\n',
                }.items():
                    info = tarfile.TarInfo('lumen-main/' + name); data = content.encode()
                    info.size = len(data); info.mode = 0o755; archive.addfile(info, io.BytesIO(data))
            helper = '''#!/usr/bin/python3
import json, os, pathlib, shutil, sys
name=pathlib.Path(sys.argv[0]).name
with open(os.environ['TEST_EVENTS'],'a') as log: log.write(json.dumps([name,*sys.argv[1:]])+'\\n')
if name=='id': print(os.environ.get('TEST_UID','1000'))
elif name=='curl':
    if os.environ.get('TEST_FAIL')=='download': sys.exit(22)
    shutil.copyfile(os.environ['TEST_ARCHIVE'],sys.argv[sys.argv.index('-o')+1])
elif name=='pacman': sys.exit(0 if os.environ.get('TEST_PACKAGES')=='ready' else 127)
elif name=='sudo': sys.exit(1 if os.environ.get('TEST_FAIL')=='packages' else 0)
elif name=='qdbus6': sys.exit(1 if os.environ.get('TEST_FAIL')=='desktop' else 0)
'''
            for name in ('id', 'curl', 'pacman', 'sudo', 'qdbus6'):
                path = mock / name; path.write_text(helper); path.chmod(0o755)
            script = (REPO / 'bootstrap.sh').read_text()
            with tarfile.open(fixture) as archive:
                archive.extractall(root, filter='data')
            checkout = root / 'lumen-main'
            (checkout / 'bootstrap.sh').write_text(script)
            cases = ({}, {'TEST_PACKAGES': 'ready'}, {'TEST_FAIL': 'download'},
                     {'TEST_FAIL': 'packages'}, {'TEST_FAIL': 'desktop'},
                     {'TEST_UID': '0'}, {'XDG_CURRENT_DESKTOP': 'GNOME'}, {'DISPLAY': ''},
                     {'TEST_LOCAL': '1', 'TEST_FAIL': 'download', 'TEST_PACKAGES': 'ready'})
            for index, overrides in enumerate(cases):
                with self.subTest(overrides=overrides):
                    folder = root / str(index); folder.mkdir(); scratch = folder / 'tmp'; scratch.mkdir()
                    prefix = folder / 'lumen'; prefix.mkdir()
                    personal = prefix / 'speech/model.bin'; personal.parent.mkdir(); personal.write_bytes(b'personal')
                    events = folder / 'events'
                    env = dict(os.environ, HOME=str(folder), PREFIX=str(prefix), TMPDIR=str(scratch),
                               PATH=str(mock)+':/usr/bin', TEST_ARCHIVE=str(fixture), TEST_EVENTS=str(events),
                               XDG_CURRENT_DESKTOP='KDE', DISPLAY=':test', WAYLAND_DISPLAY='',
                               DBUS_SESSION_BUS_ADDRESS='unix:path=/test/not-a-real-bus')
                    env.update(overrides)
                    local = overrides.get('TEST_LOCAL') == '1'
                    command = ['bash', str(checkout / 'bootstrap.sh'), '--local'] if local else ['bash']
                    result = subprocess.run(command, input=None if local else script, text=True, env=env,
                                            capture_output=True, timeout=20)
                    log = events.read_text() if events.exists() else ''
                    success = index < 2 or local
                    self.assertEqual(result.returncode == 0, success, result.stderr)
                    self.assertEqual('wizard\n' in log, success, log)
                    self.assertEqual(personal.read_bytes(), b'personal')
                    self.assertEqual(list(scratch.iterdir()), [])
                    if local:
                        self.assertNotIn('"curl"', log)
                        self.assertNotIn('"sudo"', log)
                        self.assertTrue((checkout / 'install.sh').is_file())
                    if index == 0:
                        self.assertIn('"--noconfirm"', log)
                    elif index in (1, 2, 5, 6, 7):
                        self.assertNotIn('"sudo"', log)
                    if index == 0:
                        # Running again must still open the wizard and retain private files.
                        again = subprocess.run(['bash'], input=script, text=True, env=env,
                                               capture_output=True, timeout=20)
                        self.assertEqual(again.returncode, 0, again.stderr)
                        self.assertEqual(events.read_text().count('wizard\n'), 2)
                        self.assertEqual(personal.read_bytes(), b'personal')


if __name__ == '__main__': unittest.main()
