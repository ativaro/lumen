"""Bounded native save acknowledgements before application backup staging.

This is a save barrier, not a global transaction or a lock on external writers.
Each acknowledgement records when that app's existing save operation finished.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid
from lumen_i18n import tr

APPS = ('wissen', 'reader', 'workbench', 'household', 'meetings', 'radio', 'inbox', 'sound')


def server_name(library_root):
    return 'lumen-tool-'+str(os.getuid())+'-'+hashlib.sha256(str(Path(library_root).resolve()).encode()).hexdigest()[:20]


def serve_flush(window, connection, request, timeout_ms=10000):
    """Dispatch on the app's GUI thread; answer only after its real save completes."""
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    token = request.get('vault_flush', '')
    state = dict(done=False, requested=False)
    timer = QTimer(connection); timer.setSingleShot(True)
    poll = QTimer(connection); poll.setInterval(50)
    def answer(ok, error=''):
        if state['done']: return
        state['done'] = True; timer.stop(); poll.stop()
        result = dict(ok=ok, app=window.name, token=token)
        if ok: result['flushed_at'] = time.time()
        else: result['error'] = str(error)[:2000]
        try:
            connection.write(json.dumps(result).encode()+b'\n'); connection.flush(); connection.disconnectFromServer()
        except RuntimeError: pass
    if not isinstance(token, str) or not re.fullmatch('[a-f0-9]{32}', token) or set(request) != {'vault_flush'}:
        answer(False, tr('Ungültige Speicheranfrage von Lumen Vault.')); return
    def saved():
        if state['done']: return
        if getattr(window, 'conflict', False): answer(False, tr('Zuerst den Notizkonflikt auflösen oder den Entwurf als Kopie speichern.')); return
        if getattr(window, 'dirty', False) or getattr(window, 'job', None): return
        answer(True)
    def attempt():
        if state['done']: return
        if getattr(window, 'conflict', False): answer(False, tr('Zuerst den Notizkonflikt auflösen oder den Entwurf als Kopie speichern.')); return
        if getattr(window, 'engine', None) and window.engine.busy:
            answer(False, tr('Der KI-Vorgang läuft noch. Danach erneut sichern.')); return
        if QApplication.activeModalWidget() is not None:
            answer(False, tr('Den offenen Dialog in dieser Lumen-Anwendung zuerst speichern oder schließen.')); return
        if getattr(window, 'job', None):
            if window.name == 'wissen' and getattr(window, 'writing', False): return
            answer(False, tr('Ein Vorgang läuft noch. Danach erneut sichern.')); return
        if state['requested']:
            if window.name == 'wissen' and not getattr(window, 'poller', None): saved()
            return
        try:
            state['requested'] = True
            if window.name == 'wissen': window.save_note(saved)
            else: window.save(); saved()
        except Exception as error: answer(False, error)
    timer.timeout.connect(lambda: answer(False, tr('Speichern wurde nicht rechtzeitig bestätigt. Anwendung prüfen und erneut sichern.')))
    poll.timeout.connect(attempt)
    connection.disconnected.connect(timer.stop); connection.disconnected.connect(poll.stop)
    timer.start(timeout_ms); poll.start(); attempt()


def _live_lock(path):
    """An unreachable but live native window must not be treated as a closed app."""
    try:
        if path.is_symlink(): return True
        with path.open('r') as source: value = source.read(1000).splitlines()
        pid = int(value[0])
        if pid <= 0: return True
        os.kill(pid, 0); return True
    except ProcessLookupError: return False
    except FileNotFoundError: return False
    except (ValueError, PermissionError, OSError): return True


def request_flush(library_root, job, timeout=12):
    """Blocking worker-side IPC; never starts an app that is not already open."""
    from PyQt5.QtNetwork import QLocalSocket
    job.check(); connection = QLocalSocket(); token = uuid.uuid4().hex; deadline = time.monotonic()+timeout
    try:
        connection.connectToServer(server_name(library_root))
        if not connection.waitForConnected(200):
            if _live_lock(Path(library_root)/'window.lock'):
                raise ValueError(tr('Das offene Lumen-Fenster ist nicht erreichbar. Anwendung prüfen und erneut sichern.'))
            return None
        connection.write(json.dumps(dict(vault_flush=token)).encode()+b'\n')
        if not connection.waitForBytesWritten(max(1,min(1000,int((deadline-time.monotonic())*1000)))): raise ValueError(tr('Speicheranfrage konnte nicht zugestellt werden.'))
        buffer = bytearray()
        while time.monotonic() < deadline:
            job.check()
            if connection.bytesAvailable() or connection.waitForReadyRead(100): buffer.extend(bytes(connection.readAll()))
            if len(buffer) > 8192: raise ValueError(tr('Ungültige Speicherantwort einer Lumen-Anwendung.'))
            if b'\n' in buffer:
                result = json.loads(buffer.split(b'\n', 1)[0])
                if not isinstance(result, dict) or result.get('token') != token or result.get('app') != Path(library_root).name:
                    raise ValueError(tr('Ungültige Speicherantwort einer Lumen-Anwendung.'))
                if not result.get('ok'): raise ValueError(result.get('error') or tr('Die Anwendung konnte ihre Änderungen nicht speichern.'))
                if not isinstance(result.get('flushed_at'), (int, float)):
                    raise ValueError(tr('Ungültige Speicherantwort einer Lumen-Anwendung.'))
                return dict(app=result['app'], flushed_at=result['flushed_at'])
            if connection.state() == QLocalSocket.UnconnectedState:
                raise ValueError(tr('Das offene Lumen-Fenster unterstützt die Speicheranfrage noch nicht. Anwendung erneut öffnen.'))
        raise ValueError(tr('Speichern wurde nicht rechtzeitig bestätigt. Anwendung prüfen und erneut sichern.'))
    finally: connection.abort()


def flush_for_plan(root, plan, job, timeout=30):
    from interop_vault import discover_sources, APP_NAMES
    root = Path(root); selected = [Path(path) for path in plan.get('sources', [])]
    apps = set()
    for row in [*discover_sources(root), *plan.get('app_sources', [])]:
        path = Path(row['path'])
        if row['app'] in APPS and any(path.is_relative_to(source) or source.is_relative_to(path) for source in selected): apps.add(row['app'])
    acknowledgements = []; deadline = time.monotonic()+timeout
    for app in APPS:
        if app not in apps: continue
        job.check(); remaining = deadline-time.monotonic()
        if remaining <= 0: raise ValueError(tr('Nicht alle Lumen-Anwendungen konnten rechtzeitig speichern. Erneut sichern.'))
        job.progress.emit(tr('Lumen Vault wartet auf gespeicherte Änderungen: {0}', tr(APP_NAMES[app])))
        try: value = request_flush(root/app, job, timeout=min(12, remaining))
        except ValueError as error: raise ValueError(tr('{0}: {1}', tr(APP_NAMES[app]), str(error))) from error
        if value: acknowledgements.append(value)
    return acknowledgements
