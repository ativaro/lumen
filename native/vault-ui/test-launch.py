#!/usr/bin/env python3
"""Real native singleton + cold headless helper startup, no desktop/user data."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

binary = Path(__file__).resolve().parent/'build/lumen-vault-lab'
with tempfile.TemporaryDirectory(prefix='lumen-vault-launch-') as tmp:
    root = Path(tmp); runtime = root/'runtime'; runtime.mkdir(mode=0o700)
    env = dict(os.environ, HOME=tmp, XDG_RUNTIME_DIR=str(runtime), XDG_DATA_HOME=str(root/'data'),
               XDG_CONFIG_HOME=str(root/'config'), XDG_CACHE_HOME=str(root/'cache'),
               LUMEN_TOOLS_DATA=str(root/'tools'), QT_QPA_PLATFORM='offscreen',
               PATH='/usr/bin:/bin', DBUS_SESSION_BUS_ADDRESS='unix:path=/nonexistent', DBUS_SYSTEM_BUS_ADDRESS='unix:path=/nonexistent')
    first = subprocess.Popen([str(binary), '--laboratory-only', '--backups'], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            locks = list(runtime.glob('lumen-backups-*.lock'))
            if locks and (root/'tools/vault/library.sqlite').exists(): break
            assert first.poll() is None, 'Native GUI exited during startup'
            time.sleep(.1)
        assert locks and (root/'tools/vault/library.sqlite').exists(), 'Cold helper startup failed without Lumen in PATH'
        for args in ([], ['--backups']):
            second = subprocess.run([str(binary), '--laboratory-only', *args], env=env, capture_output=True, timeout=5)
            assert second.returncode == 0, second.stderr.decode()
            assert first.poll() is None, 'Existing native window was replaced'
        print('VAULT_SINGLE_WINDOW_COLD_START_OK')
    finally:
        first.terminate(); first.wait(timeout=5)
        # Only the service started inside this temporary runtime; no user process.
        for lock in runtime.glob('lumen-backups-*.lock'):
            pid = int(lock.read_text().splitlines()[0])
            try: os.kill(pid, signal.SIGTERM)
            except ProcessLookupError: pass
