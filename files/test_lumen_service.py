"""Lumen's desktop service against its built program: start, restart after a kill, update, protocol
version, socket and folder rights. Every run uses its own private runtime folder. That the service
closes connections of another user unanswered cannot be tested without root."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import struct
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import lumen_service

try:
    PROGRAM = lumen_service.program()
except ValueError:
    PROGRAM = None


def ended(pid):
    """Waits until the process has ended; a zombie of this test process counts as ended."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            if Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                return True
        except (FileNotFoundError, ProcessLookupError):  # reaped meanwhile
            return True
        time.sleep(.02)
    return False


@unittest.skipUnless(PROGRAM, 'lumen-service is not built (LUMEN_BIN_DIR)')
class ServiceTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='lumen-service-')
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.runtime = self.root / 'run'
        self.runtime.mkdir(mode=0o700)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        shutil.copy2(PROGRAM, self.bin / 'lumen-service')
        self.enterContext(patch.dict(os.environ, XDG_RUNTIME_DIR=str(self.runtime), LUMEN_BIN_DIR=str(self.bin)))
        self.enterContext(patch.object(lumen_service, '_checked', None))
        self.addCleanup(self.quit)

    def raw(self, request):
        """The answer and process id of the running service, without starting one."""
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(5)
            connection.connect(str(self.runtime / 'lumen/service.sock'))
            pid = struct.unpack('iII', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[0]
            connection.sendall(request)
            connection.shutdown(socket.SHUT_WR)
            data = b''.join(iter(lambda: connection.recv(1 << 16), b''))
        return json.loads(data), pid

    def pid(self):
        return self.raw(b'{"v":1,"op":"hello"}')[1]

    def quit(self):
        try:
            pid = self.raw(b'{"v":1,"op":"quit"}')[1]
        except OSError:
            return
        self.assertTrue(ended(pid))

    def run_program(self, **env):
        return subprocess.run([str(self.bin / 'lumen-service')], env=env or None, capture_output=True, text=True, timeout=10)

    def test_starts_on_demand_as_one_idle_user_process_in_a_private_folder(self):
        build = hashlib.sha256((self.bin / 'lumen-service').read_bytes()).hexdigest()
        self.assertEqual(lumen_service.ask({'op': 'hello'}), {'build': build})
        folder, path = self.runtime / 'lumen', self.runtime / 'lumen/service.sock'
        self.assertEqual((stat.S_IMODE(folder.lstat().st_mode), folder.lstat().st_uid), (0o700, os.geteuid()))
        self.assertTrue(stat.S_ISSOCK(path.lstat().st_mode))
        self.assertEqual((stat.S_IMODE(path.lstat().st_mode), path.lstat().st_uid), (0o600, os.geteuid()))
        pid = self.pid()
        self.assertEqual(os.getsid(pid), pid)
        self.assertIn(b'ORT_DISABLE_TELEMETRY=1', Path(f'/proc/{pid}/environ').read_bytes().split(b'\0'))
        # A second service finds the lock taken and leaves; the first one goes on answering.
        self.assertEqual(self.run_program().returncode, 0)
        self.assertEqual(self.pid(), pid)
        # Waiting for requests costs no processor time.
        ticks = lambda: sum(map(int, Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[11:13]))
        time.sleep(.2)
        before = ticks()
        time.sleep(1)
        self.assertEqual(ticks(), before)

    def test_a_killed_service_is_started_again_by_the_next_request(self):
        lumen_service.ask({'op': 'hello'})
        pid = self.pid()
        os.kill(pid, signal.SIGKILL)
        self.assertTrue(ended(pid))
        self.assertTrue((self.runtime / 'lumen/service.sock').exists())
        build = hashlib.sha256((self.bin / 'lumen-service').read_bytes()).hexdigest()
        self.assertEqual(lumen_service.ask({'op': 'hello'}), {'build': build})
        self.assertNotEqual(self.pid(), pid)

    def test_an_update_makes_the_old_build_quit_and_the_new_one_answer(self):
        installed = self.bin / 'lumen-service'
        old = lumen_service.ask({'op': 'hello'})['build']
        pid = self.pid()
        # Like the installer: a new file takes the program's place while the old build runs.
        update = self.bin / '.lumen-service.new'
        update.write_bytes(installed.read_bytes() + b'\0another build')
        update.chmod(0o755)
        os.replace(update, installed)
        new = hashlib.sha256(installed.read_bytes()).hexdigest()
        self.assertNotEqual(new, old)
        self.assertEqual(self.raw(b'{"v":1,"op":"hello"}')[0]['build'], old)
        self.assertEqual(lumen_service.ask({'op': 'hello'}), {'build': new})
        self.assertTrue(ended(pid))
        self.assertNotEqual(self.pid(), pid)

    def test_another_protocol_version_gets_an_error_and_nothing_is_done(self):
        lumen_service.ask({'op': 'hello'})
        pid = self.pid()
        for request in (b'{"v":2,"op":"quit"}', b'{"op":"quit"}', b'{"v":"1","op":"quit"}'):
            self.assertEqual(self.raw(request)[0], {'v': 1, 'error': 'unsupported_version'})
        self.assertEqual(self.raw(b'[1]')[0], {'v': 1, 'error': 'invalid_request'})
        self.assertEqual(self.raw(b'{"v":1,"op":"forget"}')[0], {'v': 1, 'error': 'unknown_op'})
        self.assertEqual(self.pid(), pid)
        with self.assertRaises(ValueError):
            lumen_service.ask({'op': 'forget'})

    def test_memory_search_without_a_model_answers_the_text_fallback(self):
        answer = lumen_service.ask({'op': 'memory.search', 'home': str(self.root / 'no-model'), 'checksums': ['a', 'b', 'c'],
                                    'path': str(self.root / 'index.sqlite3'), 'query': 'Frage', 'entries': []})
        self.assertEqual(answer, {'mode': 'text', 'reason': 'unavailable', 'scores': []})
        self.pid()

    def test_only_a_private_runtime_folder_of_this_user_is_used(self):
        folder = self.runtime / 'lumen'
        folder.mkdir()
        folder.chmod(0o750)
        refused = self.run_program()
        self.assertEqual(refused.returncode, 1)
        self.assertIn('0700', refused.stderr)
        self.assertEqual(list(folder.iterdir()), [])
        with self.assertRaises(TimeoutError):
            lumen_service.ask({'op': 'hello'}, timeout=.5)
        folder.rmdir()
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir(mode=0o700)
        folder.symlink_to(elsewhere)
        self.assertEqual(self.run_program().returncode, 1)
        self.assertEqual(list(elsewhere.iterdir()), [])
        folder.unlink()
        self.runtime.chmod(0o755)
        self.assertEqual(self.run_program().returncode, 1)
        self.assertFalse(folder.exists())
        self.runtime.chmod(0o700)
        without = {key: value for key, value in os.environ.items() if key != 'XDG_RUNTIME_DIR'}
        refused = self.run_program(**without)
        self.assertEqual(refused.returncode, 1)
        self.assertIn('XDG_RUNTIME_DIR', refused.stderr)
        with patch.dict(os.environ, clear=True, **without), self.assertRaises(OSError):
            lumen_service.ask({'op': 'hello'})


if __name__ == '__main__':
    unittest.main()
