"""Complete selected directories are streamed without file count or text-only gates."""
import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from server_code_transport import folder_archive, clone_git


class FolderStreamTest(unittest.TestCase):
    def test_configuration_binary_empty_directory_executable_and_external_link(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); folder = root / 'selected'; folder.mkdir()
            (folder / 'empty').mkdir(); (folder / '.env.example').write_text('EXAMPLE=1')
            (folder / 'start.sh').write_text('#!/bin/sh\n'); (folder / 'start.sh').chmod(0o755)
            (folder / 'binary.bin').write_bytes(bytes(range(256))*4096)
            (root / 'outside.txt').write_text('not selected')
            (folder / 'outside').symlink_to(root / 'outside.txt')
            for index in range(260): (folder / str(index)).write_text('module')
            data = b''.join(folder_archive(folder, lambda: None))
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                self.assertEqual(len(archive.getmembers()), 265)
                self.assertEqual(archive.getmember('start.sh').mode, 0o755)
                self.assertTrue(archive.getmember('empty').isdir())
                self.assertTrue(archive.getmember('outside').issym())
                self.assertEqual(archive.extractfile('binary.bin').read(), bytes(range(256))*4096)
                self.assertNotIn('outside.txt', archive.getnames())

    def test_cancelled_import_does_not_continue_reading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'file').write_bytes(b'x'*1024*1024)
            def cancelled(): raise InterruptedError('cancelled')
            with self.assertRaises(InterruptedError):
                b''.join(folder_archive(root, cancelled))


class GitCloneTest(unittest.TestCase):
    def test_private_git_uses_native_credentials_without_saving_them_in_project(self):
        import base64, subprocess, threading, sys
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'source'; source.mkdir()
            environment = {**os.environ, 'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':'/dev/null'}
            def git(*args): subprocess.run(['git',*args],env=environment,cwd=source,check=True,capture_output=True)
            git('init'); (source / 'index.html').write_text('Complete private Git app')
            git('add','.'); git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','fixture')
            bare = root / 'repo.git'; git('clone','--bare',str(source),str(bare)); git('--git-dir='+str(bare),'update-server-info')
            auth = 'Basic ' + base64.b64encode(b'fixture:synthetic-private-token').decode()
            allowed = []
            class Handler(SimpleHTTPRequestHandler):
                def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(root),**kwargs)
                def log_message(self,*_): pass
                def do_GET(self):
                    if self.headers.get('Authorization') != auth:
                        self.send_response(401); self.send_header('WWW-Authenticate','Basic realm="fixture"'); self.end_headers(); return
                    allowed.append(True); super().do_GET()
            server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
            worker = threading.Thread(target=server.serve_forever,daemon=True); worker.start()
            askpass = root / 'askpass'
            askpass.write_text('#!'+sys.executable+"\nimport sys\nprint('fixture' if 'Username' in sys.argv[1] else 'synthetic-private-token')\n")
            askpass.chmod(0o755)
            try:
                with patch.dict(os.environ, {'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null', 'GIT_CONFIG_COUNT':'0','GIT_ASKPASS':str(askpass)}):
                    clone_git('http://127.0.0.1:'+str(server.server_port)+'/repo.git', root / 'cloned', lambda: None)
                self.assertTrue(allowed)
                self.assertEqual((root/'cloned/index.html').read_text(),'Complete private Git app')
                self.assertNotIn('synthetic-private-token',(root/'cloned/.git/config').read_text())
            finally:
                server.shutdown(); server.server_close(); worker.join(timeout=5)

    def test_local_paths_embedded_passwords_and_external_helpers_are_not_native_git_inputs(self):
        for remote in ('/home/user/private', 'file:///home/user/private', 'ext::malicious', 'https://user:password@example.invalid/repo.git'):
            with self.subTest(remote=remote), self.assertRaises(ValueError):
                clone_git(remote, Path('/unused'), lambda: None)


if __name__ == '__main__': unittest.main()
