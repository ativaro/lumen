"""Run the streamed installer with local download/package stand-ins, never sudo."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parent.parent


class BootstrapTest(unittest.TestCase):
    def test_streamed_install_and_failures_preserve_user_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); mock = root / 'bin'; mock.mkdir()
            checkout = root / 'lumen-main'; checkout.mkdir()
            (checkout / 'packaging/arch').mkdir(parents=True)
            shutil.copy(REPO / 'packaging/arch/native-build-deps.sh', checkout / 'packaging/arch')
            (checkout / 'install.sh').write_text(
                'set -eu\n[ "${TEST_FAIL:-}" != install ] || exit 1\nmkdir -p "$PREFIX/bin"\n'
                'cp "$(dirname "$0")/wizard" "$PREFIX/bin/lumen-setup-wizard"\n')
            wizard = checkout / 'wizard'
            wizard.write_text('#!/bin/sh\nprintf "wizard\\n" >> "$TEST_EVENTS"\n')
            wizard.chmod(0o755)
            helper = '''#!/usr/bin/python3
import json, os, pathlib, shutil, sys
name=pathlib.Path(sys.argv[0]).name
with open(os.environ['TEST_EVENTS'],'a') as log: log.write(json.dumps([name,*sys.argv[1:]])+'\\n')
if name=='id': print(os.environ.get('TEST_UID','1000'))
elif name=='git':
    expected=['clone','--depth=1','--branch','main','--single-branch','https://github.com/ativaro/lumen.git']
    if sys.argv[1:-1]!=expected or os.environ.get('TEST_FAIL')=='download': sys.exit(1)
    shutil.copytree(os.environ['TEST_CHECKOUT'],sys.argv[-1])
elif name=='pacman': sys.exit(0 if os.environ.get('TEST_PACKAGES')=='ready' else 127)
elif name=='sudo': sys.exit(1 if os.environ.get('TEST_FAIL')=='packages' else 0)
elif name=='qdbus6': sys.exit(1 if os.environ.get('TEST_FAIL')=='desktop' else 0)
'''
            for name in ('id', 'git', 'pacman', 'sudo', 'qdbus6'):
                path = mock / name; path.write_text(helper); path.chmod(0o755)
            script = (REPO / 'bootstrap.sh').read_text()
            (checkout / 'bootstrap.sh').write_text(script)
            cases = ({}, {'TEST_PACKAGES': 'ready'}, {'TEST_FAIL': 'download'},
                     {'TEST_FAIL': 'packages'}, {'TEST_FAIL': 'desktop'},
                     {'TEST_UID': '0'}, {'XDG_CURRENT_DESKTOP': 'GNOME'}, {'DISPLAY': ''},
                     {'TEST_LOCAL': '1', 'TEST_FAIL': 'download', 'TEST_PACKAGES': 'ready'},
                     {'TEST_LOCAL': 'auto', 'TEST_FAIL': 'download', 'TEST_PACKAGES': 'ready'},
                     {'TEST_FAIL': 'install'})
            for index, overrides in enumerate(cases):
                with self.subTest(overrides=overrides):
                    folder = root / str(index); folder.mkdir(); scratch = folder / 'tmp'; scratch.mkdir()
                    prefix = folder / 'lumen'; prefix.mkdir()
                    personal = prefix / 'speech/model.bin'; personal.parent.mkdir(); personal.write_bytes(b'personal')
                    events = folder / 'events'
                    env = dict(os.environ, HOME=str(folder), PREFIX=str(prefix), TMPDIR=str(scratch),
                               PATH=str(mock)+':/usr/bin', TEST_CHECKOUT=str(checkout), TEST_EVENTS=str(events),
                               XDG_CURRENT_DESKTOP='KDE', DISPLAY=':test', WAYLAND_DISPLAY='',
                               DBUS_SESSION_BUS_ADDRESS='unix:path=/test/not-a-real-bus')
                    env.update(overrides)
                    local = bool(overrides.get('TEST_LOCAL'))
                    command = ['bash', str(checkout / 'bootstrap.sh')] if local else ['bash']
                    if overrides.get('TEST_LOCAL') == '1': command.append('--local')
                    result = subprocess.run(command, input=None if local else script, text=True, env=env,
                                            capture_output=True, timeout=20)
                    log = events.read_text() if events.exists() else ''
                    success = index < 2 or local
                    self.assertEqual(result.returncode == 0, success, result.stderr)
                    self.assertEqual('wizard\n' in log, success, log)
                    self.assertEqual(personal.read_bytes(), b'personal')
                    self.assertEqual(list(scratch.iterdir()), [])
                    if local:
                        self.assertNotIn('["git",', log)
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

    def test_invalid_options_and_truncated_stream_do_not_start_installation(self):
        script = (REPO/'bootstrap.sh').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, HOME=tmp, PREFIX=tmp+'/untouched', TMPDIR=tmp)
            for arguments in (['--unknown'], ['--local', '--extra']):
                result = subprocess.run(['bash', '-s', '--', *arguments], input=script,
                                        text=True, env=env, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((Path(tmp)/'untouched').exists())
            result = subprocess.run(['bash'], input=script[:script.index('    bash "$source/install.sh"')],
                                    text=True, env=env, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_fresh_user_wizard_resolves_sibling_apps_without_shell_path_setup(self):
        with tempfile.TemporaryDirectory(prefix='lumen fresh ') as tmp:
            root = Path(tmp); binaries = root/'bin'; binaries.mkdir()
            (root/'files').mkdir(); (root/'files/setup_dialog.py').touch()
            launcher = binaries/'lumen-setup-wizard'
            launcher.write_bytes((REPO/'bin/lumen-setup-wizard').read_bytes())
            for name, source in {
                'lumen-python': '#!/bin/sh\ncommand -v lumen-vault\n',
                'lumen-vault': '#!/bin/sh\nexit 0\n',
            }.items():
                helper = binaries/name; helper.write_text(source); helper.chmod(0o755)
            result = subprocess.run(['bash', str(launcher)], env=dict(os.environ, PATH='/usr/bin'),
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(binaries/'lumen-vault'))


if __name__ == '__main__': unittest.main()
