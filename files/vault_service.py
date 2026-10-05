"""Headless Restic jobs for the native Vault tabs; copies only encrypted KDBX files.

The service outlives GUI credential-memory retirement. Requests and results stay
in an owner-only runtime socket; only backup metadata is stored by Library.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import uuid
from PySide6.QtCore import QCoreApplication, QObject, QLockFile, QTimer
from PySide6.QtNetwork import QLocalServer
from lumen_jobs import Job
from tools_data import Library
import vault_data as vault

MAX_REQUEST = 128 * 1024
MAX_REPLY = 36 * 1024**2
OPERATIONS = {'list', 'create', 'backup', 'preview', 'snapshots', 'files', 'restore',
              'check', 'schedule', 'add_source', 'remove_source', 'discover',
              'merge_sources', 'preflight', 'archive', 'setup_inventory', 'network',
              'test_target', 'configure', 'finish_setup'}


def socket_path():
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    st = runtime.lstat()
    if not runtime.is_absolute() or runtime.is_symlink() or not runtime.is_dir() or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise ValueError('Private runtime directory required')
    root = Path(os.path.abspath(os.environ.get('LUMEN_TOOLS_DATA') or Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'lumen-tools'))
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    return str(runtime / ('lumen-backups-' + digest))


def execute(library, request, job):
    """Explicit allowlist. Never accept arbitrary code, commands or keyring keys."""
    op = request['op']
    if op not in OPERATIONS: raise ValueError('Unknown backup operation')
    identity = request.get('id', '')
    if op in ('setup_inventory', 'network', 'test_target', 'configure', 'finish_setup'):
        import backup_setup
        if op == 'setup_inventory': return backup_setup.inventory()
        if op == 'network': return backup_setup.network(request, job)
        if op == 'test_target': return backup_setup.probe(request['path'])
        if op == 'configure': return backup_setup.configure(library, request, job)
        return backup_setup.finish_setup(library, identity, job)
    if op == 'list': return library.all(archived=bool(request.get('archived')))
    if op == 'discover':
        from interop_vault import discover_sources
        return discover_sources(library.root.parent)
    if op == 'create':
        sources = request.get('sources', [])
        if request.get('desktop'): sources = sources + vault.config_sources()
        identity = vault.create(library, request['title'], request['repository'], sources,
                                request['password'], job, interval=request.get('interval', 0))
        if request.get('interval'): vault.schedule(library, identity, request['interval'], job)
        return identity
    if op in {'backup', 'preview', 'snapshots', 'files', 'restore', 'check'}:
        return vault.run(library, identity, op, job,
                         **{k: request[k] for k in ('snapshot', 'selected', 'destination', 'full') if k in request})
    if op == 'schedule':
        with vault.lease(library, identity):
            return vault.schedule(library, identity, request['interval'], job)
    if op == 'preflight':
        from interop_vault import preflight
        return preflight(library.get(identity))
    if op in {'add_source', 'merge_sources'}:
        from interop_vault import merge_sources, discover_sources
        rows = [request['path']] if op == 'add_source' else [
            row for row in discover_sources(library.root.parent) if row['path'] in request['paths']]
        if request.get('inbox_local'):
            rows = [dict(row, kind='inbox-local', slot='inbox-local') if isinstance(row, dict) and row.get('app') == 'inbox' else row for row in rows]
        return merge_sources(library, identity, rows)
    with vault.lease(library, identity):
        if op == 'archive':
            vault.schedule(library, identity, 0, job)
            library.archive(identity, bool(request.get('archived', True)))
            return True
        plan = library.get(identity)
        sources = [p for p in plan['sources'] if p != request['path']]
        if not sources: raise ValueError('Mindestens eine Quelle muss erhalten bleiben.')
        library.update(identity, sources=sources, groups={g: [p for p in rows if p in sources] for g, rows in plan.get('groups', {}).items()}, remote_sources=[r for r in plan.get('remote_sources', []) if r['path'] in sources], app_sources=[r for r in plan.get('app_sources', []) if r['path'] in sources])
        return True


class Service(QObject):
    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.library, self.job = library, None
        self.peers = set()
        self.state = {'state': 'idle'}
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.newConnection.connect(self.accept)
        self.expiry = QTimer(self)
        self.expiry.setInterval(30 * 60 * 1000)
        self.expiry.timeout.connect(self.expire)
        self.expiry.start()

    def expire(self):
        if self.job is None: QCoreApplication.quit()

    def accept(self):
        while self.server.hasPendingConnections():
            peer = self.server.nextPendingConnection()
            if len(self.peers) >= 16:
                peer.abort(); peer.deleteLater(); continue
            self.peers.add(peer)
            peer.disconnected.connect(lambda peer=peer: self.peers.discard(peer))
            peer.setReadBufferSize(MAX_REQUEST + 1)
            timer = QTimer(peer); timer.setSingleShot(True)
            timer.timeout.connect(peer.abort); timer.start(5000)
            data = bytearray()
            def receive(peer=peer, timer=timer, data=data):
                data.extend(bytes(peer.readAll()))
                if len(data) > MAX_REQUEST:
                    peer.abort(); return
                if b'\n' not in data: return
                timer.stop()
                try:
                    request = json.loads(data)
                    if not isinstance(request, dict): raise ValueError('Invalid request')
                    response = self.dispatch(request)
                except Exception as error:
                    response = {'error': str(error)[:3000]}
                finally:
                    data[:] = b'\0' * len(data); data.clear()
                encoded = json.dumps(response, ensure_ascii=False).encode() + b'\n'
                if len(encoded) > MAX_REPLY: encoded = b'{"error":"Backup result exceeds limit"}\n'
                peer.write(encoded); peer.disconnectFromServer()
                self.expiry.start()
            peer.readyRead.connect(receive)
            peer.disconnected.connect(peer.deleteLater)

    def dispatch(self, request):
        command = request.get('command')
        if command == 'status': return self.state
        if command == 'cancel':
            if self.job and request.get('token') == self.state.get('token'):
                self.job.cancelled.set()
            return self.state
        if command != 'start' or request.get('op') not in OPERATIONS:
            raise ValueError('Unknown backup request')
        if request.get('token') and request['token'] == self.state.get('token'): return self.state
        if self.job: raise ValueError('Ein Sicherungsvorgang läuft bereits.')
        self.state = {'state': 'running', 'token': request.get('token') or uuid.uuid4().hex,
                      'op': request['op'], 'id': request.get('id', '')}
        self.job = Job(lambda job: execute(self.library, request, job), self)
        self.job.result.connect(self.result)
        self.job.failed.connect(self.failed)
        self.job.finished.connect(self.finished)
        self.job.start()
        return self.state

    def result(self, result): self.state.update(result=result)
    def failed(self, message): self.state.update(error=message[:3000])
    def finished(self):
        self.state['state'] = 'error' if 'error' in self.state else 'done'
        self.job.function = None  # release create-password closure immediately
        self.job.deleteLater(); self.job = None


def main():
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    import ctypes
    if ctypes.CDLL(None).prctl(4, 0, 0, 0, 0) != 0: return 1  # PR_SET_DUMPABLE
    app = QCoreApplication(sys.argv)
    path = socket_path()
    lock = QLockFile(path + '.lock')
    if not lock.tryLock(0): return 0
    QLocalServer.removeServer(path)
    service = Service(Library('vault'))
    if not service.server.listen(path): return 1
    try: return app.exec()
    finally: service.server.close(); lock.unlock()


if __name__ == '__main__': sys.exit(main())
