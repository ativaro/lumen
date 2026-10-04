"""Qt 6 state for one search/composer, using Lumen's existing engine and voice."""
import json
import os
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, QProcess, QSettings, QUrl, QFileSystemWatcher
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPalette, QColor
from lumen_i18n import tr, worker_process
from assistant_backend import OpenCodeBackend
from appearance_tokens import COLORS, RADII, DEFAULT_DESIGN, normalize_design
from lumen_tracking import TaskTracker
from lumen_jobs import Job
from voice_session import VoiceSession
from search_document import message_rows


class SearchController(QObject):
    queryChanged = Signal()
    resultsChanged = Signal()
    selectionChanged = Signal()
    stateChanged = Signal()
    messagesChanged = Signal()
    requestsChanged = Signal()
    sessionsChanged = Signal()
    themeChanged = Signal()
    voiceChanged = Signal()
    hideRequested = Signal()
    focusRequested = Signal()

    def __init__(self, directory=None, backend=None, applications=None, parent=None):
        super().__init__(parent)
        self.directory = str(directory or Path.home())
        self.settings = QSettings('Lumen', 'Assistant')
        self.backend = backend or OpenCodeBackend(self.directory, self)
        self.backend.settings = self.settings
        from rich_controller import RichController
        self.rich = RichController(self.backend, self, file_results=True)
        self.rich.submitted.connect(self.submit_view)
        self.rich.failed.connect(self.show_error)
        from search_home import SearchHome
        self.home = SearchHome(self); self.home.failed.connect(self.show_error)
        self.tracker = TaskTracker(self.backend, self)
        self._attachments = []
        self._query = ''; self._results = []; self._selection = 0
        self._conversation = False; self._messages = []; self._permissions = []; self._questions = []
        self._sessions = [dict(id='', title=tr('Neues Gespräch'))]; self._theme = {}; self._hint = ''; self._error = ''; self._status = tr('Bereit')
        self._mode = self.settings.value('defaultMode', 'build')
        self._auto_approve = False; self._learn = False; self.last_prompt = ''; self.last_answer = ''
        self.process = None; self.scan_jobs = []; self.generation = 0; self.last_query = ''
        self.navigated = False; self.memory_job = None; self._voice_level = 0.
        self.debounce = QTimer(self); self.debounce.setSingleShot(True); self.debounce.setInterval(220)
        self.debounce.timeout.connect(self.search)
        self.voice = VoiceSession(self.backend, self.settings, self)
        self.voice.started.connect(self.start_voice)
        self.voice.transcribedText.connect(self.voice_submit)
        self.voice.changed.connect(self.voiceChanged)
        self.voice.levelChanged.connect(self.set_voice_level)
        self.voice.failed.connect(self.show_error)
        self.voice.setupRequested.connect(self.open_setup)
        self.backend.messagesChanged.connect(self.update_messages)
        self.backend.requestsChanged.connect(self.update_requests)
        self.backend.sessionsChanged.connect(self.update_sessions)
        self.backend.sessionChanged.connect(lambda _: self.sessionsChanged.emit())
        self.backend.personaChanged.connect(self.sessionsChanged)
        self.backend.busyChanged.connect(lambda _: self.stateChanged.emit())
        self.backend.statusChanged.connect(self.set_status)
        self.backend.memoryStatus.connect(self.set_status)
        self.backend.failed.connect(self.failed)
        self.watcher = QFileSystemWatcher(self)
        self.theme_timer = QTimer(self); self.theme_timer.setSingleShot(True)
        self.theme_timer.timeout.connect(self.reload_settings)
        self.watcher.fileChanged.connect(lambda _: self.theme_timer.start(60))
        self.watcher.directoryChanged.connect(lambda _: self.theme_timer.start(60))
        self.reload_settings()
        if applications is None:
            from gi.repository import Gio
            applications = [(a.get_display_name(), a.get_id()) for a in Gio.AppInfo.get_all() if a.should_show() and a.get_id()]
        self.applications = sorted(applications, key=lambda item: item[0].casefold())
        self.search()

    attachments = Property('QVariantList', lambda self: self._attachments, notify=stateChanged)
    query = Property(str, lambda self: self._query, notify=queryChanged)
    homeView = Property(QObject, lambda self: self.home, constant=True)
    richView = Property(QObject, lambda self: self.rich, constant=True)
    results = Property('QVariantList', lambda self: self._results, notify=resultsChanged)
    selectedIndex = Property(int, lambda self: self._selection, notify=selectionChanged)
    conversation = Property(bool, lambda self: self._conversation, notify=stateChanged)
    busy = Property(bool, lambda self: self.backend.busy, notify=stateChanged)
    hint = Property(str, lambda self: self._hint, notify=stateChanged)
    status = Property(str, lambda self: self._status, notify=stateChanged)
    error = Property(str, lambda self: self._error, notify=stateChanged)
    messages = Property('QVariantList', lambda self: self._messages, notify=messagesChanged)
    permissions = Property('QVariantList', lambda self: self._permissions, notify=requestsChanged)
    questions = Property('QVariantList', lambda self: self._questions, notify=requestsChanged)
    sessions = Property('QVariantList', lambda self: self._sessions, notify=sessionsChanged)
    persona = Property(str, lambda self: self.backend.persona_choice(), notify=sessionsChanged)
    personaOptions = Property('QVariantList', lambda self: self.persona_options(), constant=True)
    session = Property(str, lambda self: self.backend.session, notify=sessionsChanged)
    theme = Property('QVariantMap', lambda self: self._theme, notify=themeChanged)
    mode = Property(str, lambda self: self._mode, notify=stateChanged)
    autoApprove = Property(bool, lambda self: self._auto_approve, notify=stateChanged)
    learn = Property(bool, lambda self: self._learn, notify=stateChanged)
    voiceActive = Property(bool, lambda self: self.voice.active, notify=voiceChanged)
    voiceState = Property(str, lambda self: self.voice.state, notify=voiceChanged)
    voiceStatus = Property(str, lambda self: self.voice.status, notify=voiceChanged)
    voiceLevel = Property(float, lambda self: self._voice_level, notify=voiceChanged)

    @Slot(result=bool)
    def clipboard_protected(self):
        from vault_privacy import protected_clipboard
        return protected_clipboard(QGuiApplication.clipboard())

    @Slot(str, result=str)
    def text(self, source):
        return tr(source)

    def persona_options(self):
        from lumen_persona import PRESETS
        return [dict(id='', title=tr('Persönlichkeit · Globale Einstellung'))] + [dict(id=key, title=tr(row[0])) for key, row in PRESETS.items()]

    @Slot(str)
    def set_persona(self, choice):
        self.backend.set_persona(choice)

    @Slot()
    def reload_settings(self):
        self.settings.sync()
        name = normalize_design(self.settings.value('appearance', DEFAULT_DESIGN))
        values = COLORS.get(name)
        if values is None:
            palette = QGuiApplication.palette()
            values = tuple(palette.color(role).name() for role in (QPalette.Window, QPalette.Base,
                QPalette.AlternateBase, QPalette.Text, QPalette.Button, QPalette.Mid, QPalette.Dark,
                QPalette.Highlight, QPalette.HighlightedText))
        theme = dict(zip(('window', 'base', 'hover', 'text', 'button', 'border', 'muted', 'accent', 'onAccent'), values))
        theme.update(name=name, radius=RADII[name], light=QColor(theme['window']).lightness() >= 128)
        from ui_typography import metrics
        theme.update(metrics(self.settings))
        if theme != self._theme:
            self._theme = theme; self.themeChanged.emit(); self.update_messages(self.backend.messages)
        self._auto_approve = self.settings.value('autoApproveTools', False, type=bool)
        self.backend.set_auto_approve(self._auto_approve); self.stateChanged.emit()
        file = Path(self.settings.fileName()); file.parent.mkdir(parents=True, exist_ok=True)
        for path in (file, file.parent):
            if path.exists() and str(path) not in self.watcher.files()+self.watcher.directories(): self.watcher.addPath(str(path))

    @Slot(str)
    def set_query(self, text):
        if text == self._query: return
        self._query = text[:100000]; self.queryChanged.emit()
        if not self._conversation: self.debounce.start()

    def set_hint(self, text):
        self._hint = text; self.stateChanged.emit()

    def set_status(self, text):
        self._status = text; self.stateChanged.emit()

    def show_error(self, text):
        self._error = text; self.stateChanged.emit()

    def failed(self, text):
        if not self._query: self.set_query(self.last_prompt)
        self.show_error(text)

    def cancel_scan(self):
        self.generation += 1
        if self.process: self.process.kill(); self.process = None

    @staticmethod
    def result(title, detail, kind, value, icon):
        return dict(title=title, detail=detail, kind=kind, value=value, icon=icon)

    def publish_results(self):
        self.resultsChanged.emit(); self.selectionChanged.emit()

    @Slot()
    def search(self):
        if self._conversation: return
        self.cancel_scan(); self._results = []; self._selection = 0; self.navigated = False
        query = self._query.strip(); self.last_query = query
        if not query:
            self._results = [self.result(title, tr('Anwendung'), 'app', identity, identity.removesuffix('.desktop')) for title, identity in self.applications[:6]]
            self.set_hint(tr('Apps und Dateien finden. Fragen werden im selben Fenster beantwortet.'))
            self.publish_results(); return
        query = query[:300]
        self.set_hint(tr('Enter startet · Umschalt+Enter für eine neue Zeile'))
        question = '?' in query or query.lower().split()[0] in ('wie', 'warum', 'was', 'welche', 'welcher', 'wieso', 'kannst', 'erkläre', 'how', 'why', 'what', 'which', 'who', 'where', 'when', 'can', 'could', 'explain')
        ask = self.result(query, tr('Hier mit Lumen besprechen'), 'question', query, 'lumen')
        if question: self._results.append(ask)
        for title, identity in self.applications:
            if all(term in title.casefold() for term in query.casefold().split()):
                self._results.append(self.result(title, tr('Anwendung'), 'app', identity, identity.removesuffix('.desktop')))
            if len(self._results) >= 20: break
        if not question: self._results.append(ask)
        self.publish_results()
        generation = self.generation; process = worker_process(self); self.process = process
        self.scan_jobs.append(process); buffer = bytearray(); finished = False
        timer = QTimer(process); timer.setSingleShot(True); timer.timeout.connect(process.kill)
        def read():
            buffer.extend(bytes(process.readAllStandardOutput()))
            selected = self._results[self._selection] if 0 <= self._selection < len(self._results) else None
            changed = False
            while b'\n' in buffer:
                line, _, rest = buffer.partition(b'\n'); buffer[:] = rest
                if generation != self.generation: continue
                try: value = json.loads(line)
                except ValueError: continue
                if isinstance(value, dict) and 'path' in value:
                    row = self.result(value['name'], str(Path(value['path']).parent), 'file', value['path'], 'folder' if value['directory'] else 'text-x-generic')
                    self._results.insert(len(self._results) if question else len(self._results)-1, row); changed = True
            if changed:
                self._selection = self._results.index(selected) if self.navigated and selected in self._results else 0
                self.publish_results()
        def done(code=0, *_):
            nonlocal finished
            if finished: return
            finished = True; timer.stop(); read()
            if process in self.scan_jobs: self.scan_jobs.remove(process)
            if self.process is process:
                self.process = None
                self.set_hint(tr('Dateisuche unterbrochen. Apps und Gespräch sind weiterhin verfügbar.') if code else tr('Enter startet · Umschalt+Enter für eine neue Zeile · Dateisuche im persönlichen Ordner'))
            process.deleteLater()
        process.readyReadStandardOutput.connect(read); process.finished.connect(done)
        process.errorOccurred.connect(lambda error: done(-1) if error == QProcess.FailedToStart else None)
        process.start(sys.executable, [str(Path(__file__).with_name('file_spaces.py'))])
        process.write((json.dumps(dict(root=self.directory, query=query, hidden=False, limit=100))+'\n').encode())
        process.closeWriteChannel(); timer.start(8000)

    @Slot(int)
    def move_selection(self, offset):
        self.navigated = True
        self._selection = max(0, min(len(self._results)-1, self._selection+offset)); self.selectionChanged.emit()

    @Slot(int)
    def activate_result(self, index):
        if 0 <= index < len(self._results): self._selection = index; self.submit(False)

    @Slot('QVariantList')
    def add_attachments(self, urls):
        if self.backend.busy:return
        for value in urls[:24]:
            url=QUrl(str(value))
            if url.isLocalFile() and url.toLocalFile() not in self._attachments:
                self._attachments.append(url.toLocalFile())
        self._attachments=self._attachments[:24];self.stateChanged.emit()

    @Slot()
    def clear_attachments(self):
        if not self.backend.busy:self._attachments=[];self.stateChanged.emit()

    @Slot(bool)
    def submit(self, ask=False):
        if self.backend.busy: return
        self.debounce.stop()
        if not self._conversation and self.last_query != self._query.strip(): self.search()
        query = self._query.strip()
        if self._conversation or ask:
            if not query: return
            self.cancel_scan(); self._conversation = True; self.last_prompt = query; self._error = ''
            self.set_hint(tr('Gespräch · Antworten und Rückfragen bleiben in dieser Suche.'))
            self.set_query('')
            prompt = query + (tr('\n\nErkläre die wesentlichen Schritte, ihre Wirkung und wie ich sie selbst wiederholen kann.') if self._learn else '')
            self.backend.background_task = False
            import mimetypes
            files=[]
            if self._attachments:
                prompt += tr('\n\nAusgewählte Pfade (Kontext):\n')+'\n'.join(self._attachments)
                for path in self._attachments:
                    mime=mimetypes.guess_type(path)[0] or ''
                    if mime.startswith('image/') or mime=='application/pdf':files.append((path,mime))
            self.backend.send(prompt, files, agent=self._mode, memory_text=query)
            self.focusRequested.emit(); return
        if not self._results: self.submit(True); return
        row = self._results[self._selection]
        if row['kind'] == 'question': self.submit(True); return
        try:
            if row['kind'] == 'app':
                from lumen_actions import desktop_file
                subprocess.Popen(['gio', 'launch', str(desktop_file(row['value']))], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            elif not QDesktopServices.openUrl(QUrl.fromLocalFile(row['value'])):
                raise ValueError(tr('Der Treffer konnte nicht geöffnet werden.'))
            self.hideRequested.emit()
        except (OSError, ValueError) as error: self.show_error(str(error))

    @Slot()
    def browse(self):
        self._conversation = False; self.stateChanged.emit()
        self.home.start()

    @Slot()
    def show_conversation(self):
        self._conversation = True; self.stateChanged.emit()

    def update_messages(self, messages):
        rows, answer = message_rows(messages)
        self.last_answer = answer
        if rows != self._messages: self._messages = rows; self.messagesChanged.emit()

    def submit_view(self, text, data):
        if self.backend.busy: return
        self._conversation = True; self._error = ''; self.last_prompt = text
        self.backend.send(text, [], agent=self._mode, memory_text=text, context_data=data)
        self.stateChanged.emit()

    def update_requests(self, permissions, questions):
        names = {'edit': tr('Dateien ändern'), 'bash': tr('Befehl ausführen'),
                 'external_directory': tr('Auf Ordner zugreifen'), 'read': tr('Dateien lesen'),
                 'webfetch': tr('Website abrufen'), 'task': tr('Teilaufgabe ausführen')}
        permissions = [dict(request, label=names.get(request.get('permission'), tr('Aktion ausführen'))) for request in permissions]
        if self._permissions == permissions and self._questions == questions: return
        self._permissions = permissions; self._questions = questions; self.requestsChanged.emit()

    def update_sessions(self, sessions):
        self._sessions = [dict(id='', title=tr('Neues Gespräch'))] + [dict(id=s['id'], title=s.get('title') or tr('Gespräch')) for s in sorted(sessions, key=lambda s: s.get('time', {}).get('updated', 0), reverse=True)]
        if self.backend.session and not any(s['id'] == self.backend.session for s in self._sessions):
            self._sessions.append(dict(id=self.backend.session, title=tr('Aktuelles Gespräch')))
        self.sessionsChanged.emit()

    @Slot(str)
    def select_session(self, identity):
        if self.backend.busy: return
        self.voice.stop(); self._conversation = bool(identity); self._error = ''
        self.backend.select_session(identity) if identity else self.reset()
        self.stateChanged.emit()

    @Slot()
    def load_sessions(self): self.backend.refresh_sessions()

    @Slot(str, bool)
    def permission_reply(self, identity, allow): self.backend.permission_reply(identity, allow)

    @Slot(str, 'QVariantList')
    def question_reply(self, identity, answers):
        request = next((q for q in self._questions if q['id'] == identity), None)
        if not request: return
        if len(answers) != len(request['questions']) or any(not isinstance(a, list) or not a or any(not isinstance(v, str) or not v.strip() for v in a) for a in answers):
            self.show_error(tr('Bitte jede Frage beantworten oder die Rückfrage überspringen.')); return
        self._error = ''; self.stateChanged.emit(); self.backend.question_reply(identity, answers)

    @Slot(str)
    def skip_question(self, identity): self.backend.question_reply(identity)

    @Slot(bool)
    def set_auto_approve(self, enabled):
        self._auto_approve = enabled; self.settings.setValue('autoApproveTools', enabled); self.settings.sync()
        self.backend.set_auto_approve(enabled); self.stateChanged.emit()

    @Slot(str)
    def set_mode(self, mode):
        if mode in ('build', 'plan') and not self.backend.busy: self._mode = mode; self.stateChanged.emit()

    @Slot(bool)
    def set_learn(self, enabled): self._learn = enabled; self.stateChanged.emit()

    @Slot()
    def reset(self):
        if self.backend.busy: return
        self.voice.stop(); self.backend.new_conversation(); self._conversation = False
        self._error = ''; self.last_prompt = ''; self._attachments=[]; self.set_query(''); self.search(); self.stateChanged.emit(); self.focusRequested.emit()

    @Slot()
    def stop(self): self.voice.stop(); self.backend.stop()

    @Slot()
    def toggle_voice(self): self.voice.toggle()

    @Slot()
    def interrupt_voice(self): self.voice.interrupt()

    def set_voice_level(self, level): self._voice_level = level; self.voiceChanged.emit()

    def start_voice(self):
        self.cancel_scan(); self._conversation = True; self.stateChanged.emit()

    def voice_submit(self, text): self.set_query(text); self.submit(True)

    @Slot()
    def hidden(self): self.home.stop(); self.debounce.stop(); self.voice.stop(); self.cancel_scan()

    @Slot()
    def copy_answer(self): QGuiApplication.clipboard().setText(self.last_answer)

    @Slot(str)
    def open_link(self, link):
        url = QUrl(link)
        if url.scheme() in ('https', 'http'): QDesktopServices.openUrl(url)

    @Slot()
    def open_setup(self):
        from lumen_launch import executable
        try: subprocess.Popen([executable('lumen-settings')], start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as error: self.show_error(str(error))

    @Slot(bool)
    def capture_knowledge(self, remember):
        if self.memory_job or not self.last_answer.strip(): return
        if len(self.last_answer) > 20000: self.show_error(tr('Bitte einen Abschnitt bis 20.000 Zeichen auswählen.')); return
        from lumen_memory import worker as memory_worker
        from wissen_data import worker as notebook_worker
        title = (self.last_prompt or tr('Gespräch mit Lumen')).splitlines()[0][:120]
        source = tr('Von dir gespeichert · Gespräch „')+title+'“'; text = self.last_answer
        job = Job(lambda job: memory_worker(job, self.tracker.store, 'remember', title=title, text=text, source=source) if remember else notebook_worker(job, self.tracker.store, 'save_memory', title=title, text=text, source=source), self)
        self.memory_job = job
        job.result.connect(lambda _: self.set_status(tr('Im Lumen-Gedächtnis gespeichert.') if remember else tr('In deinem Notizbuch gespeichert.')))
        job.failed.connect(self.show_error)
        def done(): self.memory_job = None; job.deleteLater()
        job.finished.connect(done); job.start()

    def recovery_state(self):
        messages = [dict(info=dict(role=m.get('info', {}).get('role')), parts=[dict(type='text', text='\n\n'.join(p.get('text', '') for p in m.get('parts', []) if p.get('type') == 'text' and not p.get('synthetic'))[:20000])]) for m in self.backend.messages[-20:]]
        return dict(conversation=self._conversation, rich_view=self.rich.recovery_state(), chat=dict(directory=self.backend.directory, session=self.backend.session, draft=self._query[:100000], messages=messages, paths=self._attachments, mode=self._mode, persona=self.backend.persona_choice()))

    def restore_recovery(self, state):
        if self.backend.busy: raise ValueError(tr('Bitte den laufenden Auftrag zuerst abschließen.'))
        chat = state.get('chat')
        if not isinstance(chat, dict) or not isinstance(chat.get('messages', []), list): raise ValueError(tr('Keine gültige Sitzungssicherung.'))
        self.backend.new_conversation(chat.get('directory') or self.directory)
        self.backend.session = str(chat.get('session', '')); self.backend.messages = chat.get('messages', [])
        if not self.backend.session: self.backend.set_persona(chat.get('persona', ''))
        self._attachments=[p for p in chat.get('paths',[]) if isinstance(p,str) and p.startswith('/')][:24]
        self._conversation = bool(state.get('conversation')); self._mode = 'plan' if chat.get('mode') == 'plan' else 'build'
        self.update_messages(self.backend.messages); self.set_query(str(chat.get('draft', ''))[:100000])
        self.rich.restore(state.get('rich_view'))
        self.set_status(tr('Wiederhergestellt · Kein Auftrag wurde erneut gestartet')); self.sessionsChanged.emit()
        if not self._conversation: self.search()

    def shutdown(self):
        self.home.shutdown()
        self.debounce.stop(); self.theme_timer.stop(); self.cancel_scan(); self.voice.stop()
        for process in self.scan_jobs[:]: process.kill(); process.waitForFinished(1000)
        if self.memory_job: self.memory_job.cancelled.set(); self.memory_job.wait(3000)
        self.tracker.interrupt(); self.backend.shutdown()
