"""The Qt views' binding to the engine conversations of lumen-service (native/service).

The service starts, supervises and ends the OpenCode engines, chooses the model under the model policy,
writes each mode's system text, the persona's style and the memory's context, checks and creates sessions,
runs one prompt per turn and learns from it afterwards (`memory.learn`). This binding sends what only the view
knows (directory, QSettings values, the window's language) and turns the service's answers and events into the
views' signals. The protocol is in native/service/README.md.
"""
from lumen_i18n import tr, worker_environment
import base64
import json
import os
import re
import secrets
import socket
import struct
import uuid
from pathlib import Path

import lumen_service
from lumen_qt import QObject, QSettings, QTimer, Signal
from PySide6.QtNetwork import QLocalSocket


class Channel(QObject):
    """One request to the service: `line(dict)` for every answer line, then `closed()` once."""

    def __init__(self, parent, request, line, closed):
        super().__init__(parent)
        self.line, self.closed, self.buffer, self.answered, self.retried = line, closed, b'', False, False
        self.data = (json.dumps({'v': lumen_service.VERSION, **request}) + '\n').encode()
        self.socket = QLocalSocket(self)
        self.socket.connected.connect(self.connected)
        self.socket.readyRead.connect(self.read)
        self.socket.disconnected.connect(self.finish)
        self.socket.errorOccurred.connect(self.error)
        self.open()

    def open(self):
        try: lumen_service.ensure(revive=self.retried)
        except (OSError, ValueError):
            QTimer.singleShot(0, self.finish); return
        self.socket.connectToServer(str(lumen_service.channel()))

    def connected(self):
        with socket.socket(fileno=os.dup(int(self.socket.socketDescriptor()))) as peer:
            _, uid, _ = struct.unpack('iII', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != os.geteuid(): self.socket.abort(); return
        self.socket.write(self.data)

    def send(self, value):
        line = (json.dumps(value) + '\n').encode()
        if self.socket.state() == QLocalSocket.ConnectedState: self.socket.write(line)
        else: self.data += line  # sent right after the request once connected

    def read(self):
        self.buffer += bytes(self.socket.readAll())
        while b'\n' in self.buffer and self.closed:
            raw, self.buffer = self.buffer.split(b'\n', 1)
            try: value = json.loads(raw)
            except ValueError: continue
            if isinstance(value, dict):
                self.answered = True
                self.line(value)

    def error(self, code):
        # A service that ended since its last answer is started again, once, before anything was sent.
        if not self.answered and not self.retried and code in (QLocalSocket.ServerNotFoundError,
                                                                QLocalSocket.ConnectionRefusedError):
            self.retried = True; self.socket.abort(); self.open(); return
        self.finish()

    def finish(self):
        if self.closed is None or self.socket.state() == QLocalSocket.ConnectingState: return
        self.read()
        closed, self.closed = self.closed, None
        self.close()
        closed()

    def close(self):
        self.closed = None
        self.socket.abort()
        self.deleteLater()


class OpenCodeBackend(QObject):
    apiDiagnostic = Signal(dict)
    messagesChanged = Signal(list)
    requestsChanged = Signal(list, list)
    sessionsChanged = Signal(list)
    sessionChanged = Signal(str)
    busyChanged = Signal(bool)
    statusChanged = Signal(str)
    failed = Signal(str)
    started = Signal(str, list, str)
    completed = Signal(bool, str)
    memoryStatus = Signal(str)
    memoryContextChanged = Signal(dict)
    personaChanged = Signal()

    def __init__(self, directory, parent=None, server_url='', password='', project_config=True):
        super().__init__(parent)
        self.settings = QSettings('Lumen', 'Assistant')
        if server_url and not re.fullmatch(r'http://127\.0\.0\.1:\d+', server_url):
            raise ValueError(tr('Die Engine muss auf dem lokalen Rechner laufen.'))
        self.directory = str(Path(directory).expanduser().absolute())
        self.project_config = project_config
        # A caller's own engine; otherwise the service runs one for this view's profile.
        self.server_url, self.password = server_url, password or secrets.token_urlsafe(32)
        self.generation = 0
        self.session = self.message_id = self.pending_persona = ''
        self.busy = self.polling = self.proposal = self.auto_approve = self.stopping = False
        self.permissions, self.questions, self.permission_replies = [], [], set()
        self.messages = []
        self.channels, self.turn, self.used, self.reachable = set(), None, False, False
        self.startup_diagnostic, self.database_source, self.engine_facts, self.facts = {'outcome': 'not_started'}, 'default', {}, {}
        self.background_task = self.read_only = self.screen_guidance = False
        self.presentation_enabled = self.rich_results_enabled = self.project_research = False
        self.selected_model = ''
        # The service keeps this view's learning queue under this name (`memory.learn`).
        self.view, self.learning = secrets.token_hex(8), set()
        self.memory_context = dict(version=1,message_id='',session_id='',phase='idle',sources=[],retrieval={})
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.poll)

    def set_busy(self, value):
        self.busy = value
        self.busyChanged.emit(value)

    def engine(self):
        # `env` also names the configuration folder whose pairing the persona is read with.
        if self.server_url:
            return dict(url=self.server_url, password=self.password, directory=self.directory, env=worker_environment())
        return dict(directory=self.directory, env=worker_environment(), project_config=self.project_config,
                    research=self.project_research)

    def payload(self, op, **values):
        from lumen_store import Store
        self.used = self.used or not self.server_url
        store = Store()
        return dict(op=op, engine=self.engine(), policy=store.setting('modelPolicy', {}), store=str(store.path),
                    texts=lumen_service.texts(), **values)

    def note(self, answer):
        facts = answer.get('engine')
        if isinstance(facts, dict):
            self.engine_facts = facts
            self.startup_diagnostic = facts.get('startup', self.startup_diagnostic)
            self.database_source = facts.get('database', self.database_source)
        if isinstance(answer.get('diagnostic'), dict): self.apiDiagnostic.emit(answer['diagnostic'])

    def ask(self, op, done, error=None, **values):
        """One service operation; its answer reaches `done` unless the view moved on since."""
        generation, answers = self.generation, []
        def closed():
            self.channels.discard(channel)
            QTimer.singleShot(0, lambda: answered(answers[0] if answers else None))
        def answered(answer):
            if generation != self.generation: return
            if not isinstance(answer, dict) or 'error' in answer:
                self.reachable = False
                (error or self.fail)(tr('Die Hintergrund-Engine antwortet nicht. Bitte erneut versuchen.')); return
            self.note(answer)
            if 'failed' in answer:
                self.reachable = False
                if answer.get('reset'): self.fail(answer['failed'], reset_conversation=True)
                else: (error or self.fail)(answer['failed'])
                return
            self.reachable = True
            done(answer)
        channel = Channel(self, self.payload(op, **values), answers.append, closed)
        self.channels.add(channel)

    def ensure_server(self, callback):
        if not self.reachable: self.statusChanged.emit(tr('Lumen wird bereit …'))
        self.ask('engine.start', lambda _: callback())

    def request(self, method, path, body=None, callback=None, error=None):
        """A setup or settings view's engine request (the service lets only those routes pass)."""
        def done(answer):
            self.facts = answer.get('facts', {})
            if not callback: return
            try: callback(answer.get('data'))
            except (TypeError, ValueError, KeyError, AttributeError) as exc:
                if isinstance(answer.get('diagnostic'), dict):
                    self.apiDiagnostic.emit(dict(answer['diagnostic'], callback_error=type(exc).__name__))
                (error or self.fail)(tr('Unerwartetes Datenformat der Engine. Bitte die Anbindung erneut prüfen.'))
        self.ask('engine.call', done, error, method=method, path=path, body=body)

    def program(self):
        """The engine program, for `--version` and the diagnosis."""
        return self.engine_facts.get('binary') or lumen_service.engine_info(worker_environment())['binary']

    def refresh_sessions(self):
        self.ask('engine.sessions', lambda answer: self.sessionsChanged.emit(answer['sessions']))

    def persona_choice(self):
        """The preset chosen for this conversation (the service keeps it with the conversation), or ''."""
        from lumen_store import Store
        choice = Store().setting('persona/session/' + self.session, '') if self.session else self.pending_persona
        return choice if isinstance(choice, str) and choice in lumen_service.persona_presets() else ''

    def set_persona(self, choice):
        from lumen_store import Store
        if self.busy or not isinstance(choice, str) or (choice and choice not in lumen_service.persona_presets()):
            return False
        if self.session:
            try: answer = lumen_service.ask(dict(op='persona.choose', store=str(Store().path), session=self.session,
                                                 choice=choice, texts=lumen_service.texts()))
            except (OSError, ValueError): return False
            if 'failed' in answer: return False
        else: self.pending_persona = choice
        self.personaChanged.emit()
        return True

    def new_conversation(self, directory=None):
        if self.busy:
            return False
        self.generation += 1
        self.timer.stop()
        self.polling = False
        self.session = self.message_id = ''
        self.memory_context = dict(version=1, message_id='', session_id='', phase='idle', server_stamp='',
                                   server_connection='', sources=[], retrieval={})
        self.memoryContextChanged.emit(self.memory_context)
        self.pending_persona = ''
        self.personaChanged.emit()
        if directory:
            directory = str(Path(directory).expanduser().absolute())
            if directory != self.directory:
                self.directory = directory
                self.sessionsChanged.emit([])
        self.messages = []
        self.permissions, self.questions = [], []
        self.permission_replies.clear()
        self.proposal = False
        self.messagesChanged.emit([])
        self.requestsChanged.emit([], [])
        self.sessionChanged.emit('')
        self.statusChanged.emit(tr('Bereit'))
        return True

    def select_session(self, session):
        if not self.new_conversation():
            return
        if not isinstance(session, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', session):return
        def opened(answer):
            self.session = session
            self.sessionChanged.emit(session)
            self.personaChanged.emit()
            self.conversation(answer)
        self.ask('engine.conversation', opened, session=session)

    def poll(self):
        """The conversation as it stands, while no turn of this view runs."""
        if self.turn or self.polling or not self.session:
            return
        self.polling = True
        def done(answer):
            self.polling = False
            self.conversation(answer)
        self.ask('engine.conversation', done, session=self.session)

    def conversation(self, answer):
        self.messages = answer['messages']
        self.messagesChanged.emit(self.messages)
        self.show_requests(answer['permissions'], answer['questions'])
        if answer['busy']:
            self.set_busy(True); self.statusChanged.emit(answer['status']); self.timer.start(1000)
        else:
            self.set_busy(False)
            if answer.get('reply_error'):
                self.statusChanged.emit(tr('Antwort nicht abgeschlossen')); self.failed.emit(answer['reply_error'])
            else: self.statusChanged.emit(answer['status'])

    def show_requests(self, permissions, questions):
        self.permissions, self.questions = permissions, questions
        self.permission_replies.intersection_update(p['id'] for p in permissions)
        self.publish_requests()

    def send(self, text, files=None, agent='build', title=None, proposal=False, memory_text=None,memory_context=False, context_data=None, project_task=False, web_research=False, screen_image=None):
        if self.busy or not text.strip():
            return
        self.project_research=project_task and web_research
        if proposal or project_task:
            self.new_conversation()
        self.proposal = proposal
        persona_choice = self.persona_choice()
        if not proposal and not self.screen_guidance:
            self.tracking_error = ''
            self.started.emit(text, files or [], agent)
            if self.tracking_error:
                self.fail(self.tracking_error); return
        self.set_busy(True)
        self.stopping = False
        self.message_id = 'msg_' + uuid.uuid4().hex
        self.statusChanged.emit(tr('Lumen arbeitet …'))
        self.settings.sync()
        model = self.selected_model or self.settings.value('model', '')
        # The service makes the persona from these QSettings values (native/service/src/persona.rs) and the
        # memory's context from the memory text (src/recall.rs).
        profile = self.settings.value('personaProfile', '')
        persona = dict(profile=profile if isinstance(profile, str) else '', choice=persona_choice,
                       override=self.settings.value('personaLocalOverride', False, type=bool))
        self.begin(dict(message=self.message_id, session=self.session, text=text, agent=agent, title=title,
            proposal=proposal, project_task=project_task, web_research=web_research,
            screen_guidance=self.screen_guidance, read_only=self.read_only, background=self.background_task,
            presentation=self.presentation_enabled, rich_results=self.rich_results_enabled,
            model=model if isinstance(model, str) else '', context_data=context_data,
            memory_text=text if memory_text is None else memory_text, memory_context=bool(memory_context),
            files=[[str(Path(path).absolute()), mime] for path, mime in files or []],
            screen_image=None if screen_image is None else
                base64.b64encode(screen_image).decode() if isinstance(screen_image, bytes) else False,
            persona=persona))

    def begin(self, turn):
        """The turn runs in the service; its events arrive until `end`."""
        events = []
        def line(event):
            events.append(event)
            QTimer.singleShot(0, lambda: self.turn_event(channel, events.pop(0)))
        def closed():
            QTimer.singleShot(0, lambda: self.turn_closed(channel))
        channel = Channel(self, self.payload('engine.turn', auto_approve=self.auto_approve, **turn), line, closed)
        self.turn = channel

    def turn_event(self, channel, event):
        if channel is not self.turn: return
        kind = event.get('event')
        if kind == 'engine': self.note(event)
        elif kind == 'session':
            # A conversation held with another persona or memory continues in a new session (the service decides).
            if event.get('created') and self.session:
                self.messages = []
                self.messagesChanged.emit([])
            self.session = event['id']
            if event.get('created'):
                self.personaChanged.emit()
                self.sessionChanged.emit(self.session)
                self.refresh_sessions()
        elif kind == 'persona': self.memoryStatus.emit(event['notice'])
        elif kind == 'memory':
            if 'context' in event:
                self.memory_context = event['context']; self.memoryContextChanged.emit(self.memory_context)
            if event.get('notice'): self.memoryStatus.emit(event['notice'])
        elif kind == 'messages':
            self.messages = event['messages']; self.messagesChanged.emit(self.messages)
        elif kind == 'requests': self.show_requests(event['permissions'], event['questions'])
        elif kind == 'status': self.statusChanged.emit(event['text'])
        elif kind == 'end':
            self.turn = None; channel.close(); self.note(event)
            if event.get('cancelled'): self.stopped(); return
            if 'failed' in event and not event.get('provider'):
                self.fail(event['failed'], reset_conversation=bool(event.get('reset'))); return
            self.set_busy(False)
            self.permissions, self.questions = [], []
            self.statusChanged.emit(event['status'])
            if 'failed' in event:
                self.failed.emit(event['failed']); self.completed.emit(False, event['failed']); return
            if event.get('learn'): self.learn()
            self.completed.emit(True, event['answer'])

    def turn_closed(self, channel):
        """The connection ended without `end`: the service ended or was replaced."""
        if channel is not self.turn: return
        self.turn = None
        if self.stopping: self.stopped()
        else: self.fail(tr('Die Hintergrund-Engine wurde beendet.'))

    def learn(self):
        """The service learns from the turn that just ended (`memory.learn`); its notices reach memoryStatus. Each
        view learns one turn after the other; stopping or closing the view ends its learning."""
        def line(event):
            if event.get('notice'):
                QTimer.singleShot(0, lambda notice=event['notice']: self.memoryStatus.emit(notice))
        model = self.selected_model or self.settings.value('model', '')
        channel = Channel(self, self.payload('memory.learn', message=self.message_id, view=self.view,
                                             model=model if isinstance(model, str) else ''),
                          line, lambda: self.learning.discard(channel))
        self.learning.add(channel)

    def end_learning(self):
        for channel in list(self.learning):
            channel.close()
        self.learning.clear()

    def set_auto_approve(self, enabled):
        self.auto_approve = bool(enabled)
        if self.turn: self.turn.send({'op': 'auto_approve', 'enabled': self.auto_approve})
        self.publish_requests()

    def publish_requests(self):
        self.requestsChanged.emit([p for p in self.permissions if p['id'] not in self.permission_replies], self.questions)

    def permission_reply(self, request_id, allow):
        if request_id not in self.permission_replies and any(p['id'] == request_id for p in self.permissions):
            self.permission_replies.add(request_id)
            self.publish_requests()
            self.ask('engine.reply', lambda _: self.poll(), kind='permission', id=request_id, allow=bool(allow))

    def question_reply(self, request_id, answers=None):
        if any(q['id'] == request_id for q in self.questions):
            self.ask('engine.reply', lambda _: self.poll(), kind='question', id=request_id, answers=answers)

    def stop(self):
        self.end_learning()
        self.generation += 1
        self.timer.stop()
        self.polling = False
        self.permissions, self.questions = [], []
        self.permission_replies.clear()
        self.requestsChanged.emit([], [])
        if self.turn:
            self.stopping = True
            self.turn.send({'op': 'cancel'})
            self.statusChanged.emit(tr('Wird abgebrochen …'))
        else:
            self.stopped()

    def stopped(self):
        self.release()
        self.set_busy(False)
        self.permissions, self.questions = [], []
        self.requestsChanged.emit([], [])
        self.statusChanged.emit(tr('Abgebrochen'))
        self.completed.emit(False, 'Abgebrochen')

    def fail(self, message, reset_conversation=False):
        self.timer.stop()
        self.polling = False
        # The engine of a failed turn is not used again.
        self.shutdown()
        self.set_busy(False)
        self.permissions, self.questions = [], []
        self.requestsChanged.emit([], [])
        if reset_conversation:
            self.new_conversation()
            self.sessionsChanged.emit([])
        self.failed.emit(message)
        self.statusChanged.emit(tr('Anfrage fehlgeschlagen'))
        self.completed.emit(False, message)

    def release(self):
        """Ends this view's engine in the service; a turn of another view keeps it until it ends."""
        if self.used and not self.server_url:
            self.used = False
            try: lumen_service.ask(dict(self.payload('engine.stop')), timeout=2)
            except (OSError, ValueError): pass
            self.used = False

    def shutdown(self):
        self.end_learning()
        self.generation += 1
        self.permission_replies.clear()
        self.timer.stop()
        # A closed turn connection aborts the run in the service.
        for channel in list(self.channels) + ([self.turn] if self.turn else []):
            channel.close()
        self.channels.clear()
        self.turn = None
        self.release()
        self.reachable = False
