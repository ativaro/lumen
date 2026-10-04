"""Only synthetic repositories, private runtimes and an in-memory keyring."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from tools_data import Library
from lumen_jobs import Job
import vault_service as service


class BackupOperationsTest(unittest.TestCase):
    def test_restic_create_preview_backup_and_restore(self):
        binary = os.environ.get('LUMEN_TEST_RESTIC') or shutil.which('restic')
        if not binary: self.skipTest('Set LUMEN_TEST_RESTIC to a local restic binary')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); repo = root/'repo'; source = root/'source'; restored = root/'restored'
            for path in (repo, source, restored): path.mkdir()
            (source/'sample.txt').write_text('SYNTHETIC BACKUP CONTENT')
            library = Library('vault', root/'tools'); keys = {}
            def secret(app, identity, value=None):
                if value is not None: keys[identity] = value
                return keys[identity]
            with patch('vault_data.binary', return_value=binary), patch('vault_data.secret', side_effect=secret):
                job = Job(lambda _: None)
                def execute(op, **args): return service.execute(library, dict(op=op, **args), job)
                identity = execute('create', title='Synthetic', repository=str(repo), sources=[str(source)], password='SYNTHETIC ONLY PASSWORD')
                self.assertEqual(len(execute('list')), 1)
                self.assertGreater(execute('preview', id=identity)['total_files_processed'], 0)
                result = execute('backup', id=identity)
                snapshots = execute('snapshots', id=identity)
                self.assertEqual(snapshots[0]['id'], result['snapshot_id'])
                files = execute('files', id=identity, snapshot=snapshots[0]['id'])
                self.assertTrue(any(row['path'].endswith('sample.txt') for row in files))
                target = Path(execute('restore', id=identity, snapshot=snapshots[0]['id'], destination=str(restored)))
                self.assertEqual(next(target.rglob('sample.txt')).read_text(), 'SYNTHETIC BACKUP CONTENT')
                self.assertTrue((source/'sample.txt').exists())
                execute('check', id=identity)
                with self.assertRaises(ValueError): execute('remove_source', id=identity, path=str(source))
                with self.assertRaises(ValueError): execute('credential_unlock', id=identity)

    def test_private_service_reconnect_deduplication_and_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); runtime = root/'runtime'; runtime.mkdir(mode=0o700)
            env = dict(os.environ, HOME=tmp, XDG_RUNTIME_DIR=str(runtime), XDG_DATA_HOME=str(root/'data'),
                       XDG_CONFIG_HOME=str(root/'config'), LUMEN_TOOLS_DATA=str(root/'tools'),
                       PYTHONPATH=str(Path(__file__).parent))
            # Delay a harmless synthetic list request to exercise real socket/job lifetime.
            code = '''
import time
import vault_service as s
original = s.execute
def delayed(library, request, job):
    if request.get('delay'):
        for _ in range(12): time.sleep(.05); job.check()
    return original(library, request, job)
s.execute = delayed
raise SystemExit(s.main())
'''
            proc = subprocess.Popen([sys.executable, '-c', code], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                with patch.dict(os.environ, env): endpoint = service.socket_path()
                until = time.monotonic() + 8
                while not Path(endpoint).exists() and time.monotonic() < until: time.sleep(.03)
                self.assertTrue(Path(endpoint).exists())
                self.assertEqual(Path(endpoint).stat().st_mode & 0o077, 0)
                def rpc(request):
                    with socket.socket(socket.AF_UNIX) as peer:
                        peer.settimeout(5); peer.connect(endpoint)
                        peer.sendall(json.dumps(request).encode()+b'\n')
                        data = b''
                        while not data.endswith(b'\n'): data += peer.recv(65536)
                        return json.loads(data)
                request = dict(command='start', op='list', token='synthetic-job', delay=True)
                state = rpc(request); self.assertEqual(state['state'], 'running')
                self.assertEqual(rpc(request)['token'], 'synthetic-job')
                self.assertIn('error', rpc(dict(command='start', op='list', token='another')))
                # The original client is gone; a new client obtains the same operation.
                self.assertEqual(rpc(dict(command='status'))['token'], 'synthetic-job')
                time.sleep(.8)
                self.assertEqual(rpc(dict(command='status'))['state'], 'done')
                self.assertEqual(rpc(request)['state'], 'done')
                rpc(dict(command='start', op='list', token='cancel-me', delay=True))
                rpc(dict(command='cancel', token='cancel-me'))
                time.sleep(.2)
                self.assertEqual(rpc(dict(command='status'))['state'], 'error')
                self.assertIn('error', rpc(dict(command='start', op='credential_unlock')))
                # A second daemon must not steal the first daemon's endpoint.
                other = subprocess.run([sys.executable, '-c', 'import vault_service; raise SystemExit(vault_service.main())'], env=env, timeout=5)
                self.assertEqual(other.returncode, 0)
                self.assertEqual(rpc(dict(command='status'))['token'], 'cancel-me')
            finally:
                proc.terminate(); _, errors = proc.communicate(timeout=5)
                self.assertNotIn(b'Traceback', errors, errors.decode())


if __name__ == '__main__': unittest.main()
