"""Warm activation skips Qt; unavailable D-Bus retains the full cold-start route."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


class SearchLauncherTest(unittest.TestCase):
    def test_panel_releases_cold_start_so_the_next_click_can_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'files').mkdir()
            shutil.copy2(Path(__file__).resolve().parents[1]/'bin/lumen-panel', root/'lumen-panel')
            launcher = root/'lumen-search'
            launcher.write_text('#!/usr/bin/python3\nimport os, time\nfrom pathlib import Path\n'
                                'Path(os.environ["STARTED"]).write_text(str(os.getpid()))\n'
                                'while not Path(os.environ["RELEASE"]).exists(): time.sleep(.02)\n')
            launcher.chmod(0o755)
            env = dict(os.environ, STARTED=str(root/'started'), RELEASE=str(root/'release'))
            for action in ('--search', '--voice'):
                (root/'started').unlink(missing_ok=True); (root/'release').unlink(missing_ok=True)
                try:
                    subprocess.run([str(root/'lumen-panel'), action], env=env,
                                   capture_output=True, check=True, timeout=2)
                    deadline = time.monotonic()+2
                    while not (root/'started').exists() and time.monotonic()<deadline: time.sleep(.01)
                    self.assertTrue((root/'started').exists())
                finally:
                    (root/'release').touch()

    def test_warm_routes_and_cold_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); binaries = root/'bin'; binaries.mkdir(); (root/'files').mkdir()
            for name in ('lumen-search', 'lumen-panel'):
                shutil.copy2(Path(__file__).resolve().parents[1]/'bin'/name, binaries/name)
            for name in ('search_qml.py', 'lumen_panel.py'): (root/'files'/name).touch()
            for name, script in {
                'qdbus6': '#!/bin/sh\nprintf "dbus:%s\\n" "$*" >> "$ACTIVATION_LOG"\nexit "$BUS_EXIT"\n',
                'lumen-python': '#!/bin/sh\nprintf "python:%s\\n" "$*" >> "$ACTIVATION_LOG"\n',
            }.items():
                path = binaries/name; path.write_text(script); path.chmod(0o755)
            log = root/'calls'
            env = dict(os.environ, PATH=str(binaries)+os.pathsep+os.environ['PATH'], ACTIVATION_LOG=str(log), BUS_EXIT='0')
            def run(name, *args):
                log.write_text('')
                subprocess.run([str(binaries/name), *args], env=env, check=True, timeout=5)
                deadline = time.monotonic()+2
                while not log.read_text() and time.monotonic()<deadline: time.sleep(.01)
                # The panel intentionally detaches the cold-start child.
                if env['BUS_EXIT'] == '1' and name == 'lumen-panel':
                    while 'python:' not in log.read_text() and time.monotonic()<deadline: time.sleep(.01)
                return log.read_text().splitlines()
            for name, args, method in [('lumen-search', [], 'Activate'), ('lumen-search', ['--voice'], 'Voice'),
                                       ('lumen-panel', ['--search'], 'Activate'), ('lumen-panel', ['--voice'], 'Voice')]:
                self.assertEqual(run(name, *args), ['dbus:org.lumen.Search /Search org.lumen.Search.'+method])
            # No service / unavailable bus: preserve --voice for a real first launch.
            env['BUS_EXIT'] = '1'
            calls = run('lumen-panel', '--voice')
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[-1], 'python:'+str(binaries/'../files/search_qml.py')+' --voice')
            # Restore requests must never be swallowed by warm activation.
            calls = run('lumen-search', '--restore-state', '/tmp/saved state.json')
            self.assertEqual(len(calls), 1); self.assertTrue(calls[0].startswith('python:'))
            self.assertIn('--restore-state /tmp/saved state.json', calls[0])
            calls = run('lumen-panel', '--language')
            self.assertEqual(calls, ['python:'+str(binaries/'../files/lumen_panel.py')+' --language'])
