from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
import lumen_connect as client


class ArtifactTest(unittest.TestCase):
    def test_scoped_copy_hash_and_replay(self):
        content=b'Synthetic result'
        action=dict(id=str(uuid4()),file_id=str(uuid4()),revision=1,mime='text/plain',size=len(content),sha256=hashlib.sha256(content).hexdigest())
        config=dict(server='https://lumen.example.test',token='synthetic')
        with tempfile.TemporaryDirectory() as directory,patch.object(client,'tls_context'):
            with patch.object(client,'ROOT',Path(directory)),patch.object(client.urllib.request,'build_opener') as opener:
                opener.return_value.open.side_effect=lambda *a,**k:io.BytesIO(content)
                with patch.object(client,'request',side_effect=[dict(revision=2),dict(state='claimed',revision=2)]):
                    result=client.receive_artifact(config,action)
                self.assertEqual(Path(result['path']).read_bytes(),content)
                self.assertEqual(Path(result['path']).stat().st_mode&0o777,0o600)
                with patch.object(client,'request',return_value=dict(revision=2,replayed=True)):
                    with self.assertRaises(ValueError):client.receive_artifact(config,action)
                with patch.object(client,'request',return_value=dict(revision=2)):
                    with self.assertRaises(ValueError):client.receive_artifact(config,dict(action,sha256='0'*64))
                self.assertEqual(len(list((Path(directory)/'received').iterdir())),1)

    def test_duplicate_delivery_launches_one_native_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            identity=str(uuid4());root=Path(directory)
            with patch.object(client,'ROOT',root),patch.object(client,'request',return_value=[{'id':identity}]),patch.object(client.subprocess,'Popen') as launch:
                client.desktop_requests({});client.desktop_requests({})
                self.assertEqual(launch.call_count,1)
                self.assertEqual(launch.call_args.args[0][-2:],['--artifact',identity])
                with closing(sqlite3.connect(root/'memory.sqlite3')) as db:
                    self.assertEqual(db.execute('SELECT id FROM desktop_requests').fetchone()[0],identity)

class FixtureCancelled(Exception):
    pass


class ArtifactCancellationTest(unittest.TestCase):
    """Real SDK/TLS/file I/O against a synthetic protocol fixture, not server auth/RLS."""

    @classmethod
    def setUpClass(cls):
        import subprocess
        cls.certificates = tempfile.TemporaryDirectory(prefix='artifact-cancel-ca-')
        cls.addClassCleanup(cls.certificates.cleanup)
        root = Path(cls.certificates.name)
        (root/'openssl.cnf').write_text(
            '[req]\ndistinguished_name=dn\n[dn]\n[v3_ca]\n'
            'basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n'
            'subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always\n')
        (root/'server.ext').write_text(
            'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n'
            'extendedKeyUsage=serverAuth\nsubjectAltName=IP:127.0.0.1\n')
        commands = [
            ['req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=SDK Fixture CA',
             '-config','openssl.cnf','-extensions','v3_ca','-keyout','ca.key','-out','ca.pem'],
            ['req','-new','-newkey','rsa:2048','-nodes','-subj','/CN=127.0.0.1',
             '-config','openssl.cnf','-keyout','server.key','-out','server.csr'],
            ['x509','-req','-days','1','-in','server.csr','-CA','ca.pem','-CAkey','ca.key',
             '-set_serial','2','-extfile','server.ext','-out','server.pem'],
        ]
        for command in commands:
            subprocess.run(['openssl',*command],cwd=root,check=True,capture_output=True,timeout=10)

    def setUp(self):
        import ssl
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        self.directory = tempfile.TemporaryDirectory(prefix='artifact-cancel-cache-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.payload = b'Synthetic cancellation payload\n' * 9000
        self.action = dict(id=str(uuid4()),file_id=str(uuid4()),revision=1,mime='text/plain',
                           size=len(self.payload),sha256=hashlib.sha256(self.payload).hexdigest())
        self.target = self.root/'received'/(self.action['file_id']+'.txt')
        self.mode = 'fresh'
        self.stage = ''
        self.cancelled = threading.Event()
        self.read_started = threading.Event()
        self.prefix_sent = threading.Event()
        self.release = threading.Event()
        self.requests = []
        self.events = []
        self.responses = []
        self.outputs = []
        self.owner = self
        fixture = self

        class Job:
            def check(self):
                if fixture.cancelled.is_set():
                    raise FixtureCancelled('Synthetic cancelled')
        self.job = Job()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):
                pass

            def setup(self):
                super().setup()
                self.connection.settimeout(5)

            def reply(self,value):
                body = json.dumps(value).encode()
                self.send_response(200)
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fixture.requests.append(body['state'])
                if self.path != '/bridge/actions/'+fixture.action['id'] or self.headers.get('Authorization') != 'Bearer fixture-only':
                    self.send_error(403)
                    return
                if body['state'] == 'claimed' and fixture.mode == 'lost-ack':
                    import socket
                    fixture.cancelled.set()
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                if body['state'] == 'claimed' and fixture.mode == 'malformed-ack':
                    self.reply(dict(state='claimed'))
                    return
                self.reply(dict(state=body['state'],revision=2,replayed=fixture.mode=='replay'))

            def do_GET(self):
                if self.headers.get('Authorization') != 'Bearer fixture-only':
                    self.send_error(403)
                    return
                if self.path == '/bridge/actions/'+fixture.action['id']:
                    fixture.requests.append('latest')
                    self.reply(dict(state='claimed',revision=3 if fixture.mode=='stale' else 2))
                elif self.path == '/bridge/artifacts/'+fixture.action['file_id']:
                    fixture.requests.append('artifact')
                    self.send_response(200)
                    self.send_header('Content-Length',str(len(fixture.payload)))
                    self.send_header('X-SDK-Fixture','artifact')
                    self.end_headers()
                    try:
                        if fixture.stage == 'held-read':
                            self.wfile.write(fixture.payload[:4096])
                            self.wfile.flush()
                            fixture.prefix_sent.set()
                            if not fixture.release.wait(5):
                                raise TimeoutError('Test did not release the HTTPS body')
                            self.wfile.write(fixture.payload[4096:])
                        else:
                            self.wfile.write(fixture.payload)
                    except (ConnectionError,ssl.SSLError):
                        fixture.events.append('peer-closed')
                else:
                    self.send_error(404)

        class Server(ThreadingHTTPServer):
            daemon_threads = False

        self.server = Server(('127.0.0.1',0),Handler)
        cert = Path(self.certificates.name)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert/'server.pem',cert/'server.key')
        self.server.socket = context.wrap_socket(self.server.socket,server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.01})
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.config = dict(server='https://127.0.0.1:'+str(self.server.server_port),
                           token='fixture-only',ca_file=str(cert/'ca.pem'))

    def stop_server(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
        self.assertFalse(self.thread.is_alive())

    def trigger(self,stage):
        self.events.append(stage)
        if self.stage == stage:
            self.cancelled.set()

    def receive(self,*,use_job=True):
        import http.client
        import inspect
        import os
        import urllib.request
        from contextlib import ExitStack
        fixture = self
        original_request = client.request
        original_open = urllib.request.OpenerDirector.open
        original_read = http.client.HTTPResponse.read
        original_fdopen = os.fdopen
        original_fsync = os.fsync
        original_replace = os.replace
        original_hash = hashlib.sha256

        def request(*args,**kwargs):
            result = original_request(*args,**kwargs)
            self.trigger('claim' if len(args)>2 else 'latest')
            return result

        def open_response(opener,request,*args,**kwargs):
            response = original_open(opener,request,*args,**kwargs)
            if '/bridge/artifacts/' in request.full_url:
                self.responses.append(response)
                self.trigger('open')
            return response

        def read(response,*args,**kwargs):
            artifact = response.getheader('X-SDK-Fixture') == 'artifact'
            if artifact:
                self.read_started.set()
                self.events.append('read-start')
            data = original_read(response,*args,**kwargs)
            if artifact:
                self.trigger('read' if data else 'eof')
            return data

        class Output:
            def __init__(self,file):
                self.file = file
                fixture.outputs.append(file)
            def __enter__(self):
                self.file.__enter__()
                return self
            def __exit__(self,*args):
                return self.file.__exit__(*args)
            def write(self,data):
                result = self.file.write(data)
                fixture.trigger('write')
                return result
            def flush(self):
                self.file.flush()
                fixture.trigger('flush')
            def fileno(self):
                return self.file.fileno()

        class Digest:
            def __init__(self,*args,**kwargs):
                self.digest = original_hash(*args,**kwargs)
            def update(self,data):
                self.digest.update(data)
                fixture.trigger('digest')
            def hexdigest(self):
                return self.digest.hexdigest()

        def fsync(fd):
            original_fsync(fd)
            self.trigger('fsync')

        def replace(*args):
            original_replace(*args)
            self.trigger('replace')

        with ExitStack() as stack:
            for owner,name,value in ((client,'ROOT',self.root),(client,'request',request),
                    (urllib.request.OpenerDirector,'open',open_response),
                    (http.client.HTTPResponse,'read',read),
                    (os,'fdopen',lambda *a,**k:Output(original_fdopen(*a,**k))),
                    (os,'fsync',fsync),(os,'replace',replace),(hashlib,'sha256',Digest)):
                stack.enter_context(patch.object(owner,name,value))
            # The unchanged RED driver omits only the unsupported keyword on the old API.
            kwargs = {'job':self.job} if use_job and 'job' in inspect.signature(client.receive_artifact).parameters else {}
            return client.receive_artifact(self.config,self.action,**kwargs)

    def assert_closed_and_clean(self):
        self.assertTrue(all(response.closed for response in self.responses))
        self.assertTrue(all(output.closed for output in self.outputs))
        self.assertEqual(list(self.root.glob('received/.receive-*')),[])

    def test_cancellation_boundaries_stop_following_io(self):
        limits = {'preclaim':(0,0,0,0),'claim':(0,0,0,0),'open':(0,0,0,0),
                  'read':(1,0,0,0),'digest':(1,0,0,0),'write':(1,1,0,0),
                  'eof':(4,3,0,0),'flush':(4,3,1,0),'fsync':(4,3,1,1),
                  'latest':(4,3,1,1),'replace':(4,3,1,1)}
        for stage,expected in limits.items():
            with self.subTest(stage=stage):
                self.stage = stage
                self.cancelled.clear()
                self.requests.clear()
                self.events.clear()
                self.responses.clear()
                self.outputs.clear()
                if stage == 'preclaim':
                    self.cancelled.set()
                with self.assertRaises(FixtureCancelled):
                    self.receive()
                self.assertEqual(tuple(self.events.count(e) for e in ('read-start','write','flush','fsync')),expected)
                self.assertEqual(self.events.count('replace'),int(stage=='replace'))
                self.assertEqual(self.requests.count('failed'),int(stage!='preclaim'))
                self.assertEqual(self.requests.count('artifact'),int(stage not in ('preclaim','claim')))
                self.assertNotIn('completed',self.requests)
                self.assert_closed_and_clean()
                self.assertEqual(self.target.exists(),stage=='replace')
                if self.target.exists():
                    self.assertEqual(self.target.read_bytes(),self.payload)
                    self.target.unlink()
                print(json.dumps(dict(boundary=stage,events=self.events,requests=self.requests,
                                      responses_closed=True,outputs_closed=True,partials=0)),flush=True)

    def test_cancel_during_actual_blocked_https_read(self):
        import threading
        self.stage = 'held-read'
        done = threading.Event()
        outcome = []
        def receive():
            try:
                outcome.append(self.receive())
            except Exception as error:
                outcome.append(error)
            finally:
                done.set()
        worker = threading.Thread(target=receive)
        worker.start()
        try:
            self.assertTrue(self.prefix_sent.wait(3))
            self.assertTrue(self.read_started.wait(3))
            self.assertFalse(done.is_set())
            self.cancelled.set()
        finally:
            self.release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertIsInstance(outcome[0],FixtureCancelled)
        self.assertEqual(self.events.count('read-start'),1)
        self.assertNotIn('write',self.events)
        self.assertEqual(self.requests,['claimed','artifact','failed'])
        self.assertFalse(self.target.exists())
        self.assert_closed_and_clean()

    def test_existing_verified_cache_survives_cancel(self):
        self.target.parent.mkdir(mode=0o700)
        self.target.write_bytes(self.payload)
        self.target.chmod(0o600)
        self.stage = 'read'
        with self.assertRaises(FixtureCancelled):
            self.receive()
        self.assertEqual(self.target.read_bytes(),self.payload)
        self.assertEqual(self.target.stat().st_mode&0o777,0o600)
        self.assert_closed_and_clean()

    def test_default_caller_keeps_verified_download(self):
        result = self.receive(use_job=False)
        self.assertEqual(result,dict(path=str(self.target),revision=2,id=self.action['id']))
        self.assertEqual(self.target.read_bytes(),self.payload)
        self.assertEqual(self.target.stat().st_mode&0o777,0o600)
        self.assertEqual(self.target.parent.stat().st_mode&0o777,0o700)
        self.assertEqual(self.requests,['claimed','artifact','latest'])
        self.assert_closed_and_clean()

    def test_replay_has_no_download_or_failed_receipt(self):
        self.mode = 'replay'
        for cancel_after_ack in (False,True):
            with self.subTest(cancel_after_ack=cancel_after_ack):
                self.stage = 'claim' if cancel_after_ack else ''
                self.cancelled.clear()
                self.requests.clear()
                with self.assertRaises((FixtureCancelled,ValueError)):
                    self.receive()
                self.assertEqual(self.requests,['claimed'])
                self.assertFalse(self.target.exists())
                self.assert_closed_and_clean()

    def test_unknown_claim_ack_is_not_retried_or_failed(self):
        self.mode = 'lost-ack'
        with self.assertRaises(ConnectionError):
            self.receive()
        self.assertTrue(self.cancelled.is_set())
        self.assertEqual(self.requests,['claimed'])
        self.assertFalse(self.target.exists())
        self.assert_closed_and_clean()

    def test_missing_claim_revision_does_not_start_transfer(self):
        self.mode = 'malformed-ack'
        with self.assertRaises(KeyError):
            self.receive()
        self.assertEqual(self.requests,['claimed'])
        self.assertFalse(self.target.exists())
        self.assert_closed_and_clean()

    def test_stale_revision_does_not_publish(self):
        self.mode = 'stale'
        with self.assertRaisesRegex(ValueError,'Freigabe'):
            self.receive()
        self.assertFalse(self.target.exists())
        self.assertEqual(self.requests,['claimed','artifact','latest','failed'])
        self.assert_closed_and_clean()


if __name__=='__main__':unittest.main()
