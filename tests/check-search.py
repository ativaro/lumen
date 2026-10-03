#!/usr/bin/python3
"""Cold/warm launcher, supervision and draft recovery on a private D-Bus session.

Run with: dbus-run-session -- python3 tests/check-search.py [launcher]
Uses only synthetic state. It never submits a prompt or opens the microphone.
"""
import signal
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
launcher = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT/'bin/lumen-search'
runtime = Path(os.environ.get('LUMEN_QT6_PYTHON', str(Path.home()/'.local/share/lumen/qt6-env/bin/python'))).parent.parent
service = 'org.lumen.Search'


def service_pid():
    result = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus',
        '--object-path', '/org/freedesktop/DBus', '--method', 'org.freedesktop.DBus.GetConnectionUnixProcessID', service],
        capture_output=True, text=True, timeout=3)
    return result.stdout.strip() if result.returncode == 0 else ''


def wait(check, process):
    deadline = time.monotonic()+10
    while time.monotonic() < deadline:
        if process.poll() is not None: raise AssertionError('Search exited before activation')
        if check(): return
        time.sleep(.05)
    raise AssertionError('Search did not become ready')


assert not service_pid(), 'Run this check inside a new dbus-run-session'
with tempfile.TemporaryDirectory(prefix='lumen-search-check-') as tmp:
    root = Path(tmp)
    # No desktop notification daemon lives on this private test bus.
    mocks = root/'bin'; mocks.mkdir()
    notification = mocks/'notify-send'
    notification.write_text('#!/bin/sh\nexit 0\n'); notification.chmod(0o755)
    runtime_link = root/'data/lumen/qt6-env'; runtime_link.parent.mkdir(parents=True)
    runtime_link.symlink_to(runtime, target_is_directory=True)
    env = dict(os.environ, PATH=str(mocks)+os.pathsep+os.environ.get('PATH', ''), HOME=tmp, XDG_CONFIG_HOME=str(root/'config'),
        XDG_DATA_HOME=str(root/'data'), XDG_STATE_HOME=str(root/'state'),
        LUMEN_DATA=str(root/'state/lumen'), LUMEN_TOOLS_DATA=str(root/'tools'),
        QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', LUMEN_LANGUAGE='en')
    seed = dict(conversation=True, chat=dict(directory=tmp, session='synthetic-session',
        draft='Unsent synthetic draft', messages=[], paths=[], mode='plan'))
    initial = root/'restore.json'; initial.write_text(json.dumps(seed))
    saved = root/'state/lumen/search.json'
    previous_mtime = 0
    with tempfile.TemporaryFile() as log:
        for arguments in ([str(launcher), '--restore-state', str(initial)], [str(launcher)]):
            process = subprocess.Popen(arguments, env=env, stdout=log, stderr=log)
            try:
                wait(lambda:bool(service_pid()) and saved.exists() and saved.stat().st_mtime_ns > previous_mtime, process)
                first = service_pid()
                assert json.loads(saved.read_text()) == seed, saved.read_text()
                subprocess.run([str(launcher)], env=env, stdout=log, stderr=log, check=True, timeout=10)
                assert service_pid() == first, 'Warm launch created another window process'
                wait(lambda:any((root/'state/lumen/crashes').glob('run-*/ready')), process)
                previous_mtime = saved.stat().st_mtime_ns
                if '--restore-state' in arguments:
                    import re
                    child = int(re.search(r'uint32 (\d+)', first).group(1))
                    os.kill(child, signal.SIGKILL)
                    assert process.wait(timeout=7) == 137
                    reports = [json.loads(p.read_text()) for p in (root/'state/lumen/crashes').glob('run-*/report.json')]
                    assert any(r.get('status') == 'crashed' for r in reports), reports
            except BaseException:
                log.seek(0); print(log.read().decode(errors='replace')[-5000:], file=sys.stderr); raise
            finally:
                process.terminate()
                try: process.wait(timeout=7)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            assert not service_pid(), 'Owned search process did not close with its supervisor'
        log.seek(0); output = log.read().decode(errors='replace')
        assert 'TypeError' not in output and 'Binding loop' not in output and 'could not be loaded' not in output, output
print('Cold/warm activation, private crash supervisor and restart without re-sending passed')
