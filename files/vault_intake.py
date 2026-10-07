"""Transient references to user text. Never export resolved credentials to MCP.

Only numeric selectors cross the model/tool boundary. Native Vault receives the
resolved fields for a user-confirmed NEW entry, never an automatic save or grant.
Python strings cannot promise memory erasure; no sources are written to disk.
"""
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import threading
import time

TTL = 600
MAX_TEXT = 16384
FIELDS = {'username': 'UserName', 'secret': 'Password', 'url': 'URL'}


def select(text, selector):
    if not isinstance(selector, dict) or set(selector) - {'line', 'word', 'start', 'end'}:
        raise ValueError('Invalid selector.')
    if 'line' not in selector or any(type(v) is not int for v in selector.values()):
        raise ValueError('Invalid selector.')
    lines = text.split('\n')
    line = selector['line']
    if not 1 <= line <= len(lines):
        raise ValueError('Invalid selector.')
    value = lines[line - 1].removesuffix('\r')
    if 'word' in selector:
        words = re.findall(r'\S+', value)
        if not 1 <= selector['word'] <= len(words):
            raise ValueError('Invalid selector.')
        value = words[selector['word'] - 1]
    start, end = selector.get('start', 0), selector.get('end', len(value))
    if not 0 <= start < end <= len(value):
        raise ValueError('Invalid selector.')
    value = value[start:end]
    if not value or len(value.encode('utf-8')) > 4096 or '\x00' in value:
        raise ValueError('Invalid selected field.')
    return value


def runtime():
    path = Path(os.environ.get('XDG_RUNTIME_DIR', ''))
    info = path.lstat()
    if not path.is_absolute() or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Private desktop runtime unavailable.')
    return path


class IntakeSources:
    def __init__(self):
        self.sources = {}
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.active = set()
        self.key = secrets.token_hex(16)
        self.path = runtime() / ('lumen-intake-' + self.key)
        self.server = socket.socket(socket.AF_UNIX)
        self.server.bind(str(self.path))
        self.path.chmod(0o600)
        self.server.listen(2)
        self.server.settimeout(.5)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def add(self, text):
        if not text or len(text.encode('utf-8')) > MAX_TEXT or '\x00' in text:
            return ''
        key = secrets.token_hex(16)
        with self.lock:
            self.sources = {k: v for k, v in self.sources.items() if v[0] > time.monotonic()}
            while len(self.sources) >= 16:
                del self.sources[next(iter(self.sources))]
            self.sources[key] = (time.monotonic() + TTL, text)
        return self.key + '.' + key

    def _track(self, sock):
        with self.lock:
            if self.stopped.is_set():
                sock.close()
                raise ValueError('Source closed.')
            self.active.add(sock)

    def retain(self, reference):
        with self.lock:
            key = reference.partition('.')[2]
            self.sources = {k: v for k, v in self.sources.items() if k == key}

    def close(self):
        self.stopped.set()
        with self.lock:
            self.sources.clear()
            for sock in self.active:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            self.active.clear()
        self.server.close()
        self.path.unlink(missing_ok=True)

    def _serve(self):
        while not self.stopped.is_set():
            # Drop expired text even without another user turn or tool request.
            with self.lock:
                self.sources = {k: v for k, v in self.sources.items() if v[0] > time.monotonic()}
            try:
                client, _ = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with client:
                try:
                    self._track(client)
                    client.settimeout(3)
                    data = bytearray()
                    deadline = time.monotonic() + 3
                    while b'\n' not in data and len(data) <= 8192:
                        client.settimeout(max(.001, deadline - time.monotonic()))
                        chunk = client.recv(8193 - len(data))
                        if not chunk:
                            raise ValueError('Incomplete request.')
                        data.extend(chunk)
                    if len(data) > 8192 or not data.endswith(b'\n') or data.count(b'\n') != 1:
                        raise ValueError('Invalid request.')
                    response = self._store(json.loads(data), client)
                except Exception:
                    # Never stringify exceptions: they may originate in secret parsing.
                    response = {'error': 'intake_failed'}
                try:
                    client.sendall(json.dumps(response).encode() + b'\n')
                except OSError:
                    pass
                with self.lock:
                    self.active = {s for s in self.active if s.fileno() >= 0 and s is not client}

    def _store(self, args, client):
        if not isinstance(args, dict) or set(args) != {'source', 'title', 'kind', 'fields'}:
            return {'error': 'invalid_request'}
        if args['kind'] not in ('login', 'token') or not isinstance(args['title'], str) or not 1 <= len(args['title'].strip()) <= 120:
            return {'error': 'invalid_request'}
        if not isinstance(args['source'], str) or not re.fullmatch(self.key + r'\.[0-9a-f]{32}', args['source']):
            return {'error': 'source_expired'}
        with self.lock:
            source = self.sources.get(args['source'].split('.')[1])
        if not source or source[0] <= time.monotonic():
            return {'error': 'source_expired'}
        fields = args['fields']
        if not isinstance(fields, dict) or not fields or set(fields) - FIELDS.keys() or 'secret' not in fields:
            return {'error': 'invalid_request'}
        prefill = {FIELDS[name]: select(source[1], selector) for name, selector in fields.items()}
        for field, value in prefill.items():
            limit = 4096 if field == 'Password' or (field == 'UserName' and args['kind'] == 'token') else 1024
            if len(value.encode('utf-16-le')) // 2 > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
                return {'error': 'invalid_request'}
        key = args['source'].split('.')[1]
        with self.lock:
            if self.stopped.is_set() or key not in self.sources:
                return {'error': 'source_consumed'}
            # One confirmation attempt per message. Alternate selectors must not
            # reopen a cancelled/saved/uncertain request for the same credentials.
            self.sources.pop(key)
        from vault_access import request, VaultError
        def cancelled():
            if self.stopped.is_set():
                return True
            try:
                # More input is invalid too: one request per connection.
                client.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT)
                return True
            except BlockingIOError:
                return False
            except OSError:
                return True
        client.setblocking(False)
        try:
            reply = request(dict(operation='store', title=args['title'], kind=args['kind'], prefill=prefill),
                            launch=True, on_connect=self._track, cancelled=cancelled)
        except VaultError as error:
            if error.code in ('unlock_vault_then_retry', 'vault_busy'):
                with self.lock:
                    if not self.stopped.is_set() and source[0] > time.monotonic():
                        self.sources[key] = source
                return {'error': error.code}
            return {'error': 'entry_not_saved' if error.code == 'entry_not_saved' else 'intake_outcome_unknown'}
        except ValueError:
            # The native request may have reached Save. Do not advise blind retry.
            return {'error': 'intake_outcome_unknown'}
        # Never forward unexpected native fields or exception text to a model.
        if reply.get('saved') is True and isinstance(reply.get('reference'), str) and re.fullmatch(r'vault:[0-9a-fA-F-]{36}', reply['reference']):
            return {'saved': True, 'reference': reply['reference']}
        return {'error': 'intake_failed'}


def store_from_chat(args):
    source = args.get('source', '')
    if not isinstance(source, str) or not re.fullmatch(r'[0-9a-f]{32}\.[0-9a-f]{32}', source):
        raise ValueError('Invalid source reference.')
    endpoint = runtime() / ('lumen-intake-' + source.split('.')[0])
    try:
        info = endpoint.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Invalid source endpoint.')
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(105)
            client.connect(str(endpoint))
            payload = json.dumps(args).encode() + b'\n'
            if len(payload) > 8192:
                raise ValueError('Intake request too large.')
            client.sendall(payload)
            data = bytearray()
            while b'\n' not in data and len(data) <= 1024:
                chunk = client.recv(1025 - len(data))
                if not chunk:
                    break
                data.extend(chunk)
        reply = json.loads(data)
        if reply.get('saved') is True and set(reply) == {'saved', 'reference'} and re.fullmatch(r'vault:[0-9a-fA-F-]{36}', reply['reference']):
            return reply
        if reply.get('error') in ('unlock_vault_then_retry', 'vault_busy'):
            from vault_access import VaultError
            raise VaultError(reply['error'])
        if reply.get('error') == 'entry_not_saved':
            raise ValueError('The user cancelled. Nothing was saved; do not ask again or retry automatically.')
        if reply.get('error') == 'source_expired':
            raise ValueError('Source expired or already used. Do not retry or open another confirmation automatically. Manual entry only if the user asks; never repeat credentials in tool arguments.')
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass
    raise ValueError('Vault intake did not confirm a save. Check Vault before retrying; do not repeat automatically.')
