from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
import lumen_connect as client
import lumen_service

try:
    PROGRAM = lumen_service.program()
except ValueError:
    PROGRAM = None


def download(content):
    """A stand-in for the service's download: writes the new file as it would."""
    def receive(config, path, file, limit, check):
        with open(os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as out:
            out.write(content)
        return dict(status=200, size=len(content), sha256=hashlib.sha256(content).hexdigest())
    return receive


class ArtifactTest(unittest.TestCase):
    def setUp(self):
        self.config = dict(server='https://lumen.example.test', token='synthetic', device_id=str(uuid4()))
        saved = patch.object(client, 'read_config', return_value=self.config)
        saved.start(); self.addCleanup(saved.stop)
    def test_scoped_copy_hash_and_replay(self):
        content=b'Synthetic result'
        action=dict(id=str(uuid4()),file_id=str(uuid4()),revision=1,mime='text/plain',size=len(content),sha256=hashlib.sha256(content).hexdigest())
        config=dict(server='https://lumen.example.test',token='synthetic')
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(client,'ROOT',Path(directory)),patch.object(client,'_receive',side_effect=download(content)):
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
                def child(*_a, **_k):
                    client.accept_delivery(identity, '--artifact', identity)
                    return type('Child', (), {'poll': lambda self: 0})()
                launch.side_effect = child
                client.desktop_requests(self.config);client.desktop_requests(self.config)
                self.assertEqual(launch.call_count,1)
                self.assertEqual(launch.call_args.args[0][-2:],['--artifact',identity])
                with closing(sqlite3.connect(root/'memory.sqlite3')) as db:
                    self.assertEqual(db.execute('SELECT id FROM desktop_requests').fetchone()[0],identity)

    def test_failed_launch_leaves_a_retryable_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); identity = str(uuid4())
            with patch.object(client, 'ROOT', root), patch.object(client, 'request', return_value=[{'id': identity}]), patch.object(client.subprocess, 'Popen', side_effect=OSError('synthetic launch failure')):
                with self.assertRaises(OSError): client.desktop_requests(self.config)
            with closing(sqlite3.connect(root/'memory.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM desktop_requests').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT count(*) FROM desktop_request_starts').fetchone()[0], 1)
            with patch.object(client, 'ROOT', root):
                self.assertFalse(client.accept_delivery(identity, '--launch', identity))
                self.assertTrue(client.accept_delivery(identity, '--artifact', identity))
                self.assertFalse(client.accept_delivery(identity, '--artifact', identity))

    def test_parent_restart_does_not_lose_an_unclaimed_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); identity = str(uuid4())
            child = type('Child', (), {'poll': lambda self: None})()
            with patch.object(client, 'ROOT', root), patch.object(client, 'request', return_value=[{'id': identity}]), patch.object(client.subprocess, 'Popen', return_value=child) as launch, patch.dict(client._delivery_children, {}, clear=True):
                client.desktop_requests(self.config); client.desktop_requests(self.config)
                self.assertEqual(launch.call_count, 1)
                client._delivery_children.clear()
                client.desktop_requests(self.config)
                self.assertEqual(launch.call_count, 2)
                self.assertTrue(client.accept_delivery(identity, '--artifact', identity))
                self.assertFalse(client.accept_delivery(identity, '--artifact', identity))
                client.desktop_requests(self.config)
                self.assertEqual(launch.call_count, 2)

    def test_unclaimed_start_cannot_cross_a_connection_change(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = str(uuid4()); root = Path(directory)
            with patch.object(client, 'ROOT', root), patch.object(client, 'request', return_value=[{'id': identity}]), patch.object(client.subprocess, 'Popen', side_effect=OSError('synthetic')):
                with self.assertRaises(OSError): client.desktop_requests(self.config)
            with patch.object(client, 'ROOT', root), patch.object(client, 'read_config', return_value=dict(self.config, server='https://another.example.test')):
                self.assertFalse(client.accept_delivery(identity, '--artifact', identity))

    def test_historical_receipts_are_not_replayed_or_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); identity = str(uuid4())
            with closing(sqlite3.connect(root/'memory.sqlite3')) as db, db:
                db.execute('CREATE TABLE desktop_requests(id TEXT PRIMARY KEY)')
                db.execute('INSERT INTO desktop_requests VALUES (?)', (identity,))
            with patch.object(client, 'ROOT', root), patch.object(client, 'request', return_value=[{'id': identity}]), patch.object(client.subprocess, 'Popen') as launch:
                client.desktop_requests(self.config)
                self.assertEqual(launch.call_count, 0)
            with closing(sqlite3.connect(root/'memory.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT id FROM desktop_requests').fetchall(), [(identity,)])

class FixtureCancelled(Exception):
    pass


@unittest.skipUnless(PROGRAM, 'lumen-service is not built (LUMEN_BIN_DIR)')
class ArtifactCancellationTest(unittest.TestCase):
    """Real service, TLS and file I/O against a synthetic protocol fixture, not server auth/RLS."""

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
            'extendedKeyUsage=serverAuth\nsubjectAltName=IP:127.0.0.1\nauthorityKeyIdentifier=keyid\n')
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
        # A runtime folder of its own: the test never reaches or replaces the user's running service, and the
        # service it starts ends itself once the folder is removed.
        runtime = self.enterContext(tempfile.TemporaryDirectory(prefix='lumen-run-'))
        self.enterContext(patch.dict(os.environ, XDG_RUNTIME_DIR=runtime))
        self.enterContext(patch.object(lumen_service, '_checked', None))
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
        self.prefix_sent = threading.Event()
        self.release = threading.Event()
        self.requests = []
        self.events = []
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
                if self.path in ('/bridge/refused','/bridge/moved','/bridge/large'):
                    fixture.requests.append(self.path)
                    body = (b' '*(4*1024*1024+1) if self.path == '/bridge/large' else b'{"detail":"nein"}')
                    self.send_response({'/bridge/refused':403,'/bridge/moved':302}.get(self.path,200))
                    self.send_header('Content-Length',str(len(body)))
                    self.send_header('X-Detail','refused')
                    self.send_header('Location',fixture.config['server']+'/bridge/me')
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == '/bridge/actions/'+fixture.action['id']:
                    fixture.requests.append('latest')
                    self.reply(dict(state='claimed',revision=3 if fixture.mode=='stale' else 2))
                elif self.path == '/bridge/artifacts/'+fixture.action['file_id']:
                    fixture.requests.append('artifact')
                    self.send_response(200)
                    self.send_header('Content-Length',str(len(fixture.payload)))
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
        import inspect
        from contextlib import ExitStack
        original_request = client.request
        original_receive = client._receive
        original_replace = os.replace

        def request(*args,**kwargs):
            result = original_request(*args,**kwargs)
            self.trigger('claim' if len(args)>2 else 'latest')
            return result

        def receive(*args,**kwargs):
            result = original_receive(*args,**kwargs)
            self.trigger('received')
            return result

        def replace(*args):
            original_replace(*args)
            self.trigger('replace')

        with ExitStack() as stack:
            for owner,name,value in ((client,'ROOT',self.root),(client,'request',request),
                    (client,'_receive',receive),(os,'replace',replace)):
                stack.enter_context(patch.object(owner,name,value))
            kwargs = {'job':self.job} if use_job and 'job' in inspect.signature(client.receive_artifact).parameters else {}
            return client.receive_artifact(self.config,self.action,**kwargs)

    def assert_clean(self):
        self.assertEqual(list(self.root.glob('received/.receive-*')),[])

    def test_bridge_requests_raise_what_urllib_raised(self):
        import ssl
        import urllib.error
        import urllib.request
        with self.assertRaises(urllib.error.HTTPError) as refused:
            client.request(self.config,'/bridge/refused')
        error = refused.exception
        self.assertEqual((error.code,error.geturl(),error.headers['x-detail'],json.loads(error.read(4096))),
                         (403,self.config['server']+'/bridge/refused','refused',{'detail':'nein'}))
        error.close()
        # A redirect is refused, not followed.
        with self.assertRaises(urllib.error.HTTPError) as moved:
            client.request(self.config,'/bridge/moved')
        self.assertEqual(moved.exception.code,302)
        with self.assertRaisesRegex(ValueError,'Serverantwort ist zu groß'):
            client.request(self.config,'/bridge/large')
        self.assertEqual(self.requests,['/bridge/refused','/bridge/moved','/bridge/large'])
        # Without the CA file the throwaway CA is unknown; a closed port refuses.
        with self.assertRaises(urllib.error.URLError) as unknown:
            client.request(dict(self.config,ca_file=''),'/bridge/me',timeout=3)
        self.assertIsInstance(unknown.exception.reason,ssl.SSLCertVerificationError)
        with self.assertRaises(urllib.error.URLError) as closed:
            client.request(dict(self.config,server='https://127.0.0.1:1'),'/bridge/me',timeout=3)
        self.assertIsInstance(closed.exception.reason,ConnectionRefusedError)
        # The Qt side's own connections trust what the service trusts.
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=client.tls_context(self.config)))
        reply = opener.open(urllib.request.Request(self.config['server']+'/bridge/actions/'+self.action['id'],
                                                   headers={'Authorization':'Bearer fixture-only'}),timeout=5)
        with reply:
            self.assertEqual(json.loads(reply.read())['state'],'claimed')
        with self.assertRaises(urllib.error.URLError):
            urllib.request.build_opener(urllib.request.HTTPSHandler(context=client.tls_context({}))).open(
                self.config['server']+'/bridge/me',timeout=5)

    def test_cancellation_boundaries_stop_following_io(self):
        for stage in ('preclaim','claim','received','latest','replace'):
            with self.subTest(stage=stage):
                self.stage = stage
                self.cancelled.clear()
                self.requests.clear()
                self.events.clear()
                if stage == 'preclaim':
                    self.cancelled.set()
                with self.assertRaises(FixtureCancelled):
                    self.receive()
                self.assertEqual(self.events.count('replace'),int(stage=='replace'))
                self.assertEqual(self.requests.count('failed'),int(stage!='preclaim'))
                self.assertEqual(self.requests.count('artifact'),int(stage not in ('preclaim','claim')))
                self.assertEqual(self.requests.count('latest'),int(stage in ('latest','replace')))
                self.assertNotIn('completed',self.requests)
                self.assert_clean()
                self.assertEqual(self.target.exists(),stage=='replace')
                if self.target.exists():
                    self.assertEqual(self.target.read_bytes(),self.payload)
                    self.target.unlink()
                print(json.dumps(dict(boundary=stage,events=self.events,requests=self.requests,partials=0)),flush=True)

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
            self.assertFalse(done.is_set())
            self.cancelled.set()
            # The view's cancel ends the transfer while the server still holds the rest of the body.
            self.assertTrue(done.wait(2))
        finally:
            self.release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertIsInstance(outcome[0],FixtureCancelled)
        self.assertEqual(self.requests,['claimed','artifact','failed'])
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_existing_verified_cache_survives_cancel(self):
        self.target.parent.mkdir(mode=0o700)
        self.target.write_bytes(self.payload)
        self.target.chmod(0o600)
        self.stage = 'received'
        with self.assertRaises(FixtureCancelled):
            self.receive()
        self.assertEqual(self.target.read_bytes(),self.payload)
        self.assertEqual(self.target.stat().st_mode&0o777,0o600)
        self.assert_clean()

    def test_default_caller_keeps_verified_download(self):
        result = self.receive(use_job=False)
        self.assertEqual(result,dict(path=str(self.target),revision=2,id=self.action['id']))
        self.assertEqual(self.target.read_bytes(),self.payload)
        self.assertEqual(self.target.stat().st_mode&0o777,0o600)
        self.assertEqual(self.target.parent.stat().st_mode&0o777,0o700)
        self.assertEqual(self.requests,['claimed','artifact','latest'])
        self.assert_clean()

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
                self.assert_clean()

    def test_unknown_claim_ack_is_not_retried_or_failed(self):
        self.mode = 'lost-ack'
        with self.assertRaises(ConnectionError):
            self.receive()
        self.assertTrue(self.cancelled.is_set())
        self.assertEqual(self.requests,['claimed'])
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_missing_claim_revision_does_not_start_transfer(self):
        self.mode = 'malformed-ack'
        with self.assertRaises(KeyError):
            self.receive()
        self.assertEqual(self.requests,['claimed'])
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_stale_revision_does_not_publish(self):
        self.mode = 'stale'
        with self.assertRaisesRegex(ValueError,'Freigabe'):
            self.receive()
        self.assertFalse(self.target.exists())
        self.assertEqual(self.requests,['claimed','artifact','latest','failed'])
        self.assert_clean()

    def claim_ack_revision(self,revision,*,mutate_action_to=None):
        handler_class = self.server.RequestHandlerClass
        original_reply = handler_class.reply
        def reply(handler,value):
            if handler.command == 'POST' and value.get('state') == 'claimed':
                value = dict(state='claimed',revision=revision)
                if mutate_action_to is not None:
                    self.action['revision'] = mutate_action_to
            return original_reply(handler,value)
        return patch.object(handler_class,'reply',reply)

    def test_malformed_claim_revision_remains_unknown(self):
        for revision in (None,True,False,'2',2.0,3,1,0,-1):
            for cancel_after_ack in (False,True):
                with self.subTest(revision=revision,type=type(revision).__name__,cancel_after_ack=cancel_after_ack):
                    self.target.unlink(missing_ok=True)
                    self.cancelled.clear()
                    self.requests.clear()
                    self.events.clear()
                    self.stage = 'claim' if cancel_after_ack else ''
                    with self.claim_ack_revision(revision):
                        with self.assertRaises((ValueError,FixtureCancelled)):
                            self.receive()
                    self.assertEqual(self.requests,['claimed'])
                    self.assertFalse(self.target.exists())
                    self.assert_clean()
                    print(json.dumps(dict(ack_revision=revision,ack_type=type(revision).__name__,
                                          cancel_after_ack=cancel_after_ack,requests=self.requests,
                                          transfers=0,failed_receipts=0)),flush=True)

    def test_fresh_claim_without_replayed_field_is_accepted(self):
        with self.claim_ack_revision(2):
            result = self.receive()
        self.assertEqual(result,dict(path=str(self.target),revision=2,id=self.action['id']))
        self.assertEqual(self.target.read_bytes(),self.payload)
        self.assertEqual(self.requests,['claimed','artifact','latest'])
        self.assert_clean()

    def test_cancel_after_valid_fresh_ack_allows_one_failed_receipt(self):
        self.stage = 'claim'
        with self.claim_ack_revision(2):
            with self.assertRaises(FixtureCancelled):
                self.receive()
        self.assertEqual(self.requests,['claimed','failed'])
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_claim_successor_uses_revision_captured_before_http(self):
        with self.claim_ack_revision(2,mutate_action_to=10):
            result = self.receive()
        self.assertEqual(self.action['revision'],10)
        self.assertEqual(result['revision'],2)
        self.assertEqual(self.target.read_bytes(),self.payload)
        self.assertEqual(self.requests,['claimed','artifact','latest'])
        self.assert_clean()


if __name__=='__main__':unittest.main()
