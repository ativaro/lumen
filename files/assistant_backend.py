"""Private local OpenCode process and asynchronous HTTP client for both Lumen UIs."""
import base64
import json
import os
import re
import secrets
import shutil
import time
import uuid
from pathlib import Path

from PyQt5.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, QUrl, QUrlQuery, pyqtSignal
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply


class OpenCodeBackend(QObject):
    messagesChanged = pyqtSignal(list)
    requestsChanged = pyqtSignal(list, list)
    sessionsChanged = pyqtSignal(list)
    sessionChanged = pyqtSignal(str)
    busyChanged = pyqtSignal(bool)
    statusChanged = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, directory, parent=None, server_url='', password=''):
        super().__init__(parent)
        if server_url and not re.fullmatch(r'http://127\.0\.0\.1:\d+', server_url):
            raise ValueError('Die Engine muss auf dem lokalen Rechner laufen.')
        self.directory = str(Path(directory).expanduser().absolute())
        self.url, self.password = server_url, password or secrets.token_urlsafe(32)
        self.network = QNetworkAccessManager(self)
        self.proc = None
        self.replies = set()
        self.waiting = []
        self.generation = 0
        self.session = ''
        self.message_id = ''
        self.idle_since = None
        self.busy = False
        self.polling = False
        self.permissions, self.questions = [], []
        self.messages = []
        self.related_sessions = {}
        self.log = b''
        self.start_timer = QTimer(self)
        self.start_timer.setSingleShot(True)
        self.start_timer.timeout.connect(lambda: self.start_failed('Die Hintergrund-Engine antwortet nicht. Bitte erneut versuchen.'))
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.poll)

    def set_busy(self, value):
        self.busy = value
        self.busyChanged.emit(value)

    def request(self, method, path, body=None, callback=None, error=None):
        url = QUrl(self.url + path)
        query = QUrlQuery(url)
        query.addQueryItem('directory', self.directory)
        url.setQuery(query)
        request = QNetworkRequest(url)
        request.setHeader(QNetworkRequest.ContentTypeHeader, 'application/json')
        token = base64.b64encode(('opencode:' + self.password).encode())
        request.setRawHeader(b'Authorization', b'Basic ' + token)
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy)
        reply = self.network.sendCustomRequest(request, method.encode(), json.dumps(body).encode() if body is not None else b'')
        self.replies.add(reply)
        generation = self.generation
        timeout = QTimer(reply)
        timeout.setSingleShot(True)
        timeout.timeout.connect(reply.abort)
        timeout.start(20000)

        def finished():
            self.replies.discard(reply)
            timeout.stop()
            if generation != self.generation:
                reply.deleteLater()
                return
            code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0
            raw = bytes(reply.readAll())
            try:
                data = json.loads(raw) if raw else None
            except (ValueError, UnicodeError):
                data = None
            if reply.error() != QNetworkReply.NoError or not 200 <= code < 300:
                detail = (data.get('data', {}).get('message') or data.get('message')) if isinstance(data, dict) else ''
                (error or self.fail)(detail or f'Verbindung zur Engine fehlgeschlagen ({code or reply.errorString()}).')
            elif callback:
                try:
                    callback(data)
                except (TypeError, ValueError, KeyError, AttributeError) as exc:
                    self.fail('Unerwartete Antwort der Engine: ' + str(exc))
            reply.deleteLater()
        reply.finished.connect(finished)

    def ensure_server(self, callback):
        if self.url:
            callback()
            return
        self.waiting.append((self.generation, callback))
        if self.proc:
            return
        binary = os.environ.get('LUMEN_OPENCODE_BIN') or shutil.which('opencode') or str(Path.home() / '.opencode/bin/opencode')
        self.statusChanged.emit('Lumen wird bereit …')
        proc = QProcess(self)
        self.proc = proc
        environment = QProcessEnvironment.systemEnvironment()
        for key in ('OPENCODE', 'OPENCODE_PID'):
            environment.remove(key)
        environment.insert('OPENCODE_SERVER_PASSWORD', self.password)
        environment.insert('OPENCODE_SERVER_USERNAME', 'opencode')
        proc.setProcessEnvironment(environment)
        proc.setWorkingDirectory(self.directory)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda: self.read_startup(proc))
        proc.errorOccurred.connect(lambda code: self.start_failed('OpenCode konnte nicht gestartet werden. Installation und Pfad prüfen.')
                                  if code == QProcess.FailedToStart and self.proc is proc else None)
        proc.finished.connect(lambda *_: self.start_failed('Die Hintergrund-Engine wurde beendet.') if self.proc is proc else None)
        proc.start(binary, ['serve', '--hostname', '127.0.0.1', '--port', '0'])
        self.start_timer.start(25000)

    def read_startup(self, proc):
        self.log = (self.log + bytes(proc.readAllStandardOutput()))[-8000:]
        if self.url:
            return
        match = re.search(rb'http://127\.0\.0\.1:(\d+)', self.log)
        if match:
            self.url = 'http://127.0.0.1:' + match[1].decode()
            self.start_timer.stop()
            callbacks, self.waiting = self.waiting, []
            self.statusChanged.emit('Bereit')
            for generation, callback in callbacks:
                if generation == self.generation:
                    callback()

    def refresh_sessions(self):
        self.ensure_server(lambda: self.request('GET', '/session?limit=200', callback=lambda sessions:
            self.sessionsChanged.emit([s for s in (sessions or []) if s.get('metadata', {}).get('client') == 'lumen'
                                      and s.get('directory') == self.directory])))

    def new_conversation(self, directory=None):
        if self.busy:
            return False
        self.generation += 1
        self.timer.stop()
        self.polling = False
        self.session = self.message_id = ''
        if directory:
            directory = str(Path(directory).expanduser().absolute())
            if directory != self.directory:
                self.directory = directory
                self.sessionsChanged.emit([])
        self.messages = []
        self.related_sessions = {}
        self.permissions, self.questions = [], []
        self.messagesChanged.emit([])
        self.requestsChanged.emit([], [])
        self.sessionChanged.emit('')
        self.statusChanged.emit('Bereit')
        return True

    def select_session(self, session):
        if not self.new_conversation():
            return
        self.session = session
        self.sessionChanged.emit(session)
        self.ensure_server(self.poll)

    def send(self, text, files=None, agent='build'):
        if self.busy or not text.strip():
            return
        self.log = b'' if not self.url else self.log
        self.set_busy(True)
        self.message_id = 'msg_' + uuid.uuid4().hex
        self.idle_since = None
        self.statusChanged.emit('Lumen arbeitet …')
        parts = [{'type': 'text', 'text': text}]
        for path, mime in files or []:
            parts.append({'type': 'file', 'mime': mime, 'filename': Path(path).name,
                          'url': QUrl.fromLocalFile(str(Path(path).absolute())).toString()})
        body = {'messageID': self.message_id, 'agent': agent, 'parts': parts,
                'system': 'Du bist Lumen, der persönliche Desktop-Assistent. Antworte auf Deutsch, knapp und verständlich. '
                          'Nutze die bereitgestellten Werkzeuge. Zeige keine Terminal-Banner oder internen Protokolle. '
                          'Behaupte Änderungen nur, wenn die Werkzeuge sie bestätigt haben.'}

        def submit():
            self.request('POST', f'/session/{self.session}/prompt_async', body, lambda _: self.poll())

        def created(session):
            self.session = session['id']
            self.sessionChanged.emit(self.session)
            submit()
            self.refresh_sessions()

        def ready():
            if self.session:
                submit()
            else:
                self.request('POST', '/session', {'title': text.splitlines()[0][:70], 'metadata': {'client': 'lumen'}}, created)
        self.ensure_server(ready)

    def poll(self):
        if self.polling or not self.session:
            return
        self.polling = True

        def messages(data):
            self.messages = data or []
            self.messagesChanged.emit(self.messages)
            self.request('GET', '/permission', callback=permissions)

        def permissions(data):
            pending_permissions = data or []
            self.request('GET', '/question', callback=lambda questions: resolve_requests(pending_permissions, questions or []))

        def resolve_requests(permissions, questions):
            sessions = iter({r.get('sessionID', '') for r in permissions + questions})
            allowed = {self.session}
            def next_session():
                session = next(sessions, None)
                if session is None:
                    self.permissions = [p for p in permissions if p.get('sessionID') in allowed]
                    self.questions = [q for q in questions if q.get('sessionID') in allowed]
                    self.requestsChanged.emit(self.permissions, self.questions)
                    self.request('GET', '/session/status', callback=status)
                    return
                def resolved(related):
                    if related:
                        allowed.add(session)
                    next_session()
                self.is_related_session(session, resolved)
            next_session()

        def status(data):
            self.polling = False
            state = (data or {}).get(self.session, {}).get('type', 'idle')
            assistants = [m['info'] for m in self.messages if m['info'].get('role') == 'assistant'
                          and (not self.message_id or m['info'].get('parentID') == self.message_id)]
            completed = assistants and assistants[-1].get('time', {}).get('completed')
            if state == 'idle' and (completed or not self.busy) and not self.permissions and not self.questions:
                self.set_busy(False)
                error = assistants[-1].get('error') if assistants else None
                if error:
                    self.statusChanged.emit('Antwort nicht abgeschlossen')
                    self.failed.emit(error.get('data', {}).get('message') or error.get('name', 'Anfrage fehlgeschlagen.'))
                else:
                    self.statusChanged.emit('Bereit')
            else:
                if state == 'idle' and not self.permissions and not self.questions:
                    self.idle_since = self.idle_since or time.monotonic()
                    if time.monotonic() - self.idle_since > 30:
                        self.fail('Die Engine hat keine abgeschlossene Antwort geliefert. Bitte erneut versuchen.')
                        return
                else:
                    self.idle_since = None
                self.set_busy(True)
                self.statusChanged.emit('Deine Antwort wird benötigt' if self.permissions or self.questions else
                                        'Verbindung wird erneut versucht …' if state == 'retry' else 'Lumen arbeitet …')
                self.timer.start(450)
        self.request('GET', f'/session/{self.session}/message?limit=100', callback=messages)

    def is_related_session(self, session, callback, seen=None):
        if session == self.session:
            callback(True)
            return
        if session in self.related_sessions:
            callback(self.related_sessions[session])
            return
        seen = (seen or set()) | {session}
        def resolved(related):
            self.related_sessions[session] = related
            callback(related)
        def loaded(data):
            parent = (data or {}).get('parentID')
            if parent and parent not in seen:
                self.is_related_session(parent, resolved, seen)
            else:
                resolved(False)
        # Child agents have their own session IDs. Never infer ownership from a tool label.
        if not re.fullmatch(r'ses_[A-Za-z0-9_]+', session):
            resolved(False)
            return
        self.request('GET', '/session/' + session, callback=loaded, error=lambda _: resolved(False))

    def permission_reply(self, request_id, allow):
        if any(p['id'] == request_id for p in self.permissions):
            self.request('POST', f'/permission/{request_id}/reply', {'reply': 'once' if allow else 'reject'}, lambda _: self.poll())

    def question_reply(self, request_id, answers=None):
        if any(q['id'] == request_id for q in self.questions):
            suffix = 'reply' if answers is not None else 'reject'
            self.request('POST', f'/question/{request_id}/{suffix}', {'answers': answers} if answers is not None else {}, lambda _: self.poll())

    def stop(self):
        self.generation += 1
        self.timer.stop()
        self.polling = False
        self.waiting.clear()
        if self.url and self.session:
            self.request('POST', f'/session/{self.session}/abort', {}, self.stopped)
            self.statusChanged.emit('Wird abgebrochen …')
        else:
            self.stopped()

    def stopped(self, _data=None):
        if self.proc:
            self.shutdown()
        self.set_busy(False)
        self.permissions, self.questions = [], []
        self.requestsChanged.emit([], [])
        self.statusChanged.emit('Abgebrochen')

    def fail(self, message):
        self.timer.stop()
        self.polling = False
        # Stop our private engine before allowing another request after a transport failure.
        self.shutdown()
        self.set_busy(False)
        self.permissions, self.questions = [], []
        self.requestsChanged.emit([], [])
        self.failed.emit(message)
        self.statusChanged.emit('Anfrage fehlgeschlagen')

    def start_failed(self, message):
        self.shutdown()
        self.fail(message)

    def shutdown(self):
        self.generation += 1
        self.start_timer.stop()
        self.timer.stop()
        self.waiting.clear()
        for reply in list(self.replies):
            reply.abort()
        if self.proc:
            proc, self.proc = self.proc, None
            proc.terminate()
            if not proc.waitForFinished(2000):
                proc.kill()
                proc.waitForFinished(1000)
            proc.deleteLater()
        self.url = ''
        self.log = b''
