"""Streaming native folder import and the private loopback application preview."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import queue
import re
import secrets
import select
import stat
import subprocess
import signal
import time
import tempfile
import tarfile
import threading
from urllib.parse import urlsplit, parse_qsl
import urllib.request
import lumen_connect

HOP = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
       'te', 'trailer', 'transfer-encoding', 'upgrade', 'content-length'}


def clone_git(remote, target, check):
    """Use the Desktop's normal Git credentials and SSH agent, never the model runtime."""
    if not isinstance(remote, str) or not remote or any(ord(c)<32 for c in remote) or remote.startswith('-'):
        raise ValueError('Bitte eine gültige Git-Adresse angeben.')
    url = urlsplit(remote)
    network = url.scheme in ('https','http','ssh','git') and url.hostname
    scp = '://' not in remote and '::' not in remote and re.fullmatch(r'(?:[^/\s:@]+@)?[^/\s:]+:.+', remote)
    if not network and not scp:
        raise ValueError('Für lokale Projekte „Ordner öffnen“ verwenden; zum Klonen eine Git-Netzwerkadresse angeben.')
    if url.password or any(name.lower() in ('access_token','token','password','api_key','key') for name,_ in parse_qsl(url.query)):
        raise ValueError('Zugangsdaten gehören in deine Git-Anmeldung, nicht in die Git-Adresse.')
    environment = {key:value for key,value in os.environ.items() if not key.startswith('GIT_TRACE') and key!='GIT_CURL_VERBOSE'}
    environment['GIT_TERMINAL_PROMPT'] = '0'
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(['git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
            'clone','--',remote,str(target)], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            env=environment, start_new_session=True)
        try:
            while process.poll() is None:
                check(); time.sleep(.1)
            check()
            if process.returncode:
                log.seek(0); error = log.read().decode(errors='replace').lower()
                messages = [('permission denied','Die SSH-Anmeldung wurde abgewiesen. Bitte deine Desktop-Git-Anmeldung prüfen.'),
                            ('authentication failed','Die Git-Anmeldung wurde abgewiesen. Bitte deine Desktop-Git-Anmeldung prüfen.'),
                            ('could not read username','Bitte die Git-Anmeldung auf deinem Desktop einrichten und erneut klonen.'),
                            ('certificate','Das Git-Zertifikat wird auf deinem Desktop nicht vertraut.'),
                            ('host key verification','Der SSH-Hostschlüssel ist auf deinem Desktop nicht bestätigt.'),
                            ('not found','Das Repository wurde nicht gefunden oder ist für deine Anmeldung nicht freigegeben.'),
                            ('resolve','Der Git-Server konnte nicht aufgelöst werden.')]
                raise ValueError(next((message for needle,message in messages if needle in error),
                                     'Git-Klonen fehlgeschlagen (Exitcode '+str(process.returncode)+'). Bitte Adresse und Desktop-Git-Anmeldung prüfen.'))
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.wait()


class RawResponse(http.client.HTTPResponse):
    def __init__(self, socket, *args, **kwargs):
        super().__init__(socket, *args, **kwargs)
        self.fp.close()
        self.fp = socket.makefile('rb', buffering=0)


def folder_archive(folder, check):
    """Open each selected child without following links; retain the complete hierarchy."""
    output = queue.Queue(maxsize=2)
    cancelled = threading.Event()
    def checked():
        check()
        if cancelled.is_set():
            raise InterruptedError('Ordnerimport abgebrochen.')
    def put(value):
        while True:
            checked()
            try:
                output.put(value, timeout=.2)
                return
            except queue.Full:
                pass
    class Sink(io.RawIOBase):
        def writable(self): return True
        def write(self, value):
            put(bytes(value))
            return len(value)
    def produce():
        def walk(archive, descriptor, prefix=''):
            for name in sorted(os.listdir(descriptor)):
                checked()
                info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                relative = prefix + name
                item = tarfile.TarInfo(relative)
                item.mode, item.mtime = stat.S_IMODE(info.st_mode), info.st_mtime
                if stat.S_ISLNK(info.st_mode):
                    item.type, item.linkname = tarfile.SYMTYPE, os.readlink(name, dir_fd=descriptor)
                    archive.addfile(item)
                elif stat.S_ISDIR(info.st_mode):
                    child = os.open(name, os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                    try:
                        opened = os.fstat(child)
                        if (opened.st_ino, opened.st_dev) != (info.st_ino, info.st_dev):
                            raise ValueError('Ein Ordner wurde während des Imports ersetzt: ' + relative)
                        item.type = tarfile.DIRTYPE
                        archive.addfile(item)
                        walk(archive, child, relative + '/')
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
                    with os.fdopen(child, 'rb') as source:
                        opened = os.fstat(source.fileno())
                        if not stat.S_ISREG(opened.st_mode) or (opened.st_ino, opened.st_dev) != (info.st_ino, info.st_dev):
                            raise ValueError('Eine Datei wurde während des Imports ersetzt: ' + relative)
                        item.size = opened.st_size
                        archive.addfile(item, source)
                        after = os.fstat(source.fileno())
                        if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns):
                            raise ValueError('Eine Datei wurde während des Imports geändert: ' + relative)
                else:
                    raise ValueError('Diese Datei ist kein importierbarer Projektinhalt: ' + relative)
        try:
            root = os.open(folder, os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                with tarfile.open(fileobj=Sink(), mode='w|', format=tarfile.PAX_FORMAT) as archive:
                    walk(archive, root)
            finally:
                os.close(root)
            put(None)
        except BaseException as error:
            if not cancelled.is_set():
                try: put(error)
                except BaseException: pass
    worker = threading.Thread(target=produce, daemon=True)
    worker.start()
    try:
        while True:
            checked()
            try: value = output.get(timeout=.2)
            except queue.Empty: continue
            if value is None: return
            if isinstance(value, BaseException): raise value
            yield value
    finally:
        cancelled.set()
        worker.join(timeout=1)


def import_folder(config, identity, revision, folder, check):
    url = config['server'] + '/bridge/code-library/' + identity + '/runtime/import?revision=' + str(revision)
    request = urllib.request.Request(url, data=folder_archive(folder, check),
        headers={'Authorization': 'Bearer ' + config['token'], 'Content-Type': 'application/x-tar'}, method='POST')
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=lumen_connect.tls_context(config)), lumen_connect.NoRedirect())
    with opener.open(request, timeout=60) as response:
        check()
        return json.load(response)


class Preview:
    def __init__(self, config, identity, check, *, port=0):
        self.config, self.identity, self.check = dict(config), identity, check
        self.secret = secrets.token_urlsafe(32)
        owner = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version, rbufsize = 'HTTP/1.1', 0
            def log_message(self, *_): pass
            def body(self):
                if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
                    while True:
                        size = int(self.rfile.readline().split(b';', 1)[0], 16)
                        if not size:
                            while self.rfile.readline() not in (b'\r\n', b''): pass
                            return
                        while size:
                            owner.check()
                            data = self.rfile.read(min(size, 65536))
                            if not data: raise EOFError()
                            size -= len(data)
                            yield data
                        if self.rfile.readline(3) != b'\r\n': raise ValueError('Ungültige Übertragung.')
                else:
                    size = int(self.headers.get('Content-Length', 0))
                    while size:
                        owner.check()
                        data = self.rfile.read(min(size, 65536))
                        if not data: raise EOFError()
                        size -= len(data)
                        yield data
            def route(self):
                owner.check()
                protocols = [p.strip() for p in self.headers.get('Sec-WebSocket-Protocol', '').split(',') if p.strip()]
                private = 'lumen-preview.' + owner.secret
                private_requested = private in protocols
                permitted = secrets.compare_digest(self.headers.get('X-Lumen-Preview', ''), owner.secret) or private in protocols
                origin = self.headers.get('Origin')
                if not permitted or origin and origin != owner.origin:
                    self.send_error(403); return
                target = urlsplit(owner.config['server'])
                upstream = http.client.HTTPSConnection(target.hostname, target.port or 443,
                    context=lumen_connect.tls_context(owner.config), timeout=60)
                headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP | {
                    'host', 'authorization', 'cookie', 'sec-websocket-protocol', 'x-lumen-preview'}}
                headers['Authorization'] = 'Bearer ' + owner.config['token']
                headers['X-Lumen-Preview-Host'] = '127.0.0.1:' + str(owner.server.server_port)
                if self.headers.get('Authorization'): headers['X-Lumen-App-Authorization'] = self.headers['Authorization']
                if self.headers.get('Cookie'): headers['X-Lumen-App-Cookie'] = self.headers['Cookie']
                protocols = [p for p in protocols if p != private]
                if protocols: headers['Sec-WebSocket-Protocol'] = ', '.join(protocols)
                websocket = self.headers.get('Upgrade', '').lower() == 'websocket'
                if websocket:
                    headers.update(Upgrade='websocket', Connection='Upgrade')
                    upstream.response_class = RawResponse
                path = '/bridge/code-library/' + owner.identity + '/preview' + self.path
                response = None
                try:
                    body = self.body() if self.command not in ('GET', 'HEAD') else None
                    upstream.request(self.command, path, body=body, headers=headers, encode_chunked=body is not None)
                    transport = upstream.sock
                    response = upstream.getresponse()
                    self.send_response(response.status)
                    self.response_started = True
                    for key, value in response.getheaders():
                        if key.lower() not in HOP:
                            if key.lower() == 'location' and value.startswith(owner.config['server'] + '/bridge/code-library/' + owner.identity + '/preview/'):
                                value = owner.origin + value.split('/preview', 1)[1]
                            self.send_header(key, value)
                    if websocket and response.status == 101:
                        self.send_header('Upgrade', 'websocket'); self.send_header('Connection', 'Upgrade')
                        if private_requested and not protocols and not response.getheader('Sec-WebSocket-Protocol'):
                            self.send_header('Sec-WebSocket-Protocol', private)
                    else: self.send_header('Connection', 'close')
                    self.end_headers(); self.close_connection = True
                    if websocket and response.status == 101:
                        self.wfile.flush()
                        sockets = [self.connection, transport]
                        while True:
                            owner.check()
                            ready = [transport] if transport.pending() else select.select(sockets, [], [], 1)[0]
                            for source in ready:
                                data = source.recv(65536)
                                if not data: return
                                sockets[1 if source is sockets[0] else 0].sendall(data)
                    else:
                        while chunk := response.read1(65536):
                            owner.check(); self.wfile.write(chunk); self.wfile.flush()
                finally:
                    if response is not None: response.close()
                    upstream.close()
            def dispatch(self):
                try: self.route()
                except (BrokenPipeError, ConnectionResetError): pass
                except Exception:
                    self.close_connection = True
                    if not getattr(self, 'response_started', False):
                        self.send_error(502, 'Die App-Vorschau ist noch nicht erreichbar.')
            do_GET = do_HEAD = do_OPTIONS = do_POST = do_PUT = do_PATCH = do_DELETE = dispatch
        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.server.daemon_threads = True
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
