"""The same native conversation surface in Lumen and Lumen Files."""
import html
import mimetypes
from pathlib import Path

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QKeySequence, QTextDocument
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                             QScrollArea, QShortcut, QTextBrowser, QVBoxLayout, QWidget)
from assistant_backend import OpenCodeBackend
from preview import label


class SafeDocument(QTextDocument):
    def loadResource(self, _kind, _url):
        return None


class Transcript(QTextBrowser):
    def loadResource(self, _kind, _url):
        # Model output must never fetch remote images or local files implicitly.
        return None


class ChatPanel(QWidget):
    def __init__(self, directory, parent=None, backend=None):
        super().__init__(parent)
        self.backend = backend or OpenCodeBackend(directory, self)
        self.paths = []
        self.last_answer = ''
        self.last_prompt = ''
        self.rendered = None
        self.request_ids = None
        self.setMinimumWidth(350)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(label('lumen', 'brand'))
        top.addStretch()
        self.new = QPushButton('Neues Gespräch')
        self.new.clicked.connect(self.new_conversation)
        top.addWidget(self.new)
        layout.addLayout(top)
        self.sessions = QComboBox()
        self.sessions.setAccessibleName('Gespräch auswählen')
        self.sessions.addItem('Neues Gespräch', '')
        self.sessions.activated.connect(self.open_session)
        layout.addWidget(self.sessions)
        self.context = label('', 'muted')
        self.context.setWordWrap(True)
        self.context.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.context)
        self.mode = QComboBox()
        self.mode.setAccessibleName('Arbeitsweise von Lumen')
        self.mode.addItem('Aufgaben erledigen', 'build')
        self.mode.addItem('Lesen & prüfen', 'plan')
        self.mode.setToolTip('Lesen & prüfen analysiert, ohne Dateien zu bearbeiten.')
        layout.addWidget(self.mode)
        self.transcript = Transcript()
        self.transcript.setAccessibleName('Gespräch mit Lumen')
        self.transcript.setOpenLinks(False)
        self.transcript.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url)
                                              if url.scheme() in ('https', 'http') else None)
        layout.addWidget(self.transcript, 1)
        self.requests = QScrollArea()
        self.requests.setWidgetResizable(True)
        self.requests.setMaximumHeight(280)
        self.requests.hide()
        layout.addWidget(self.requests)
        self.error = label('', 'error')
        self.error.setWordWrap(True)
        self.error.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.error.hide()
        layout.addWidget(self.error)
        self.composer = QPlainTextEdit()
        self.composer.setPlaceholderText('Was möchtest du tun?\nStrg+Enter zum Senden')
        self.composer.setAccessibleName('Nachricht an Lumen')
        self.composer.setMaximumHeight(115)
        layout.addWidget(self.composer)
        bottom = QHBoxLayout()
        self.status = label('Bereit', 'muted')
        bottom.addWidget(self.status, 1)
        self.copy = QPushButton('Kopieren')
        self.copy.setToolTip('Letzte Antwort kopieren')
        self.copy.setEnabled(False)
        self.copy.clicked.connect(lambda: QApplication.clipboard().setText(self.last_answer))
        bottom.addWidget(self.copy)
        self.stop = QPushButton('Abbrechen')
        self.stop.clicked.connect(self.backend.stop)
        self.stop.hide()
        bottom.addWidget(self.stop)
        self.send_button = QPushButton('Senden')
        self.send_button.setObjectName('primary')
        self.send_button.clicked.connect(self.send)
        bottom.addWidget(self.send_button)
        layout.addLayout(bottom)
        QShortcut(QKeySequence('Ctrl+Return'), self, activated=self.send)
        self.backend.messagesChanged.connect(self.show_messages)
        self.backend.requestsChanged.connect(self.show_requests)
        self.backend.sessionsChanged.connect(self.show_sessions)
        self.backend.sessionChanged.connect(self.select_session_item)
        self.backend.busyChanged.connect(self.set_busy)
        self.backend.statusChanged.connect(self.status.setText)
        self.backend.failed.connect(self.request_failed)
        self.update_context()
        self.show_messages([])

    def request_failed(self, text):
        if self.last_prompt and not self.composer.toPlainText():
            self.composer.setPlainText(self.last_prompt)
        self.show_error(text)

    def show_error(self, text):
        self.error.setText(text)
        self.error.show()

    def set_busy(self, busy):
        self.send_button.setEnabled(not busy)
        self.new.setEnabled(not busy)
        self.mode.setEnabled(not busy)
        self.sessions.setEnabled(not busy)
        self.stop.setVisible(busy)

    def show_sessions(self, sessions):
        self.sessions.clear()
        self.sessions.addItem('Neues Gespräch', '')
        for session in sorted(sessions, key=lambda s: s.get('time', {}).get('updated', 0), reverse=True):
            self.sessions.addItem(session.get('title') or 'Gespräch', session['id'])
        self.select_session_item(self.backend.session)

    def select_session_item(self, session):
        index = self.sessions.findData(session)
        if index < 0:
            self.sessions.addItem('Aktuelles Gespräch', session)
            index = self.sessions.count() - 1
        self.sessions.setCurrentIndex(index)

    def open_session(self, index):
        if self.backend.busy:
            return
        self.paths = []
        self.update_context()
        self.error.hide()
        self.backend.select_session(self.sessions.itemData(index))

    def new_conversation(self):
        if self.backend.new_conversation():
            self.error.hide()
            self.last_prompt = ''
            self.mode.setCurrentIndex(0)
            self.composer.setFocus()

    def update_context(self):
        names = ' · '.join(Path(p).name for p in self.paths)
        self.context.setText(('Auswahl: ' + names + '\n' if names else '') + self.backend.directory)
        self.context.setToolTip('\n'.join(self.paths) or self.backend.directory)

    def begin_context(self, action='open', paths=None, directory=None, prompt=''):
        if self.backend.busy:
            self.show_error('Bitte den laufenden Vorgang abwarten oder abbrechen, bevor du den Kontext wechselst.')
            return
        paths = [str(Path(p).expanduser().absolute()) for p in (paths or [])]
        if directory is None and paths:
            first = Path(paths[0])
            directory = str(first if first.is_dir() else first.parent)
        if directory and directory != self.backend.directory:
            self.backend.new_conversation(directory)
        self.paths = paths
        self.mode.setCurrentIndex(1 if action in ('explain', 'review') else 0)
        self.update_context()
        self.error.hide()
        self.backend.refresh_sessions()
        prompts = {
            'explain': 'Erkläre die ausgewählten Dateien oder den Ordner in zwei bis drei verständlichen Sätzen. Ändere keine Dateien. Biete bei Bedarf eine genauere Erklärung an.',
            'review': 'Prüfe den aktuellen Git-Diff im ausgewählten Ordner auf Fehler und Risiken. Ändere keine Dateien.',
            'fix': 'Untersuche die ausgewählten Dateien oder den Ordner auf Fehler. Behebe bestätigte Fehler und prüfe die Änderungen.'}
        prompt = prompt or prompts.get(action, '')
        if prompt:
            self.composer.setPlainText(prompt)
            self.send()
        self.composer.setFocus()

    def send(self):
        text = self.composer.toPlainText().strip()
        if not text or self.backend.busy:
            return
        self.error.hide()
        self.last_prompt = text
        files = []
        if self.paths:
            text += '\n\nAusgewählte Pfade (Kontext):\n' + '\n'.join(self.paths)
            for path in self.paths:
                mime = mimetypes.guess_type(path)[0] or ''
                if Path(path).is_file() and (mime.startswith('image/') or mime == 'application/pdf'):
                    files.append((path, mime))
        self.backend.send(text, files, self.mode.currentData())
        self.composer.clear()

    def show_messages(self, messages):
        entries = []
        self.last_answer = ''
        for message in messages:
            role = message.get('info', {}).get('role')
            if role not in ('assistant', 'user'):
                continue
            parts = message.get('parts', [])
            text = '\n\n'.join(p.get('text', '') for p in parts if p.get('type') == 'text' and not p.get('synthetic'))
            activity = [p.get('state', {}).get('title') or p.get('tool', 'Werkzeug') for p in parts
                        if p.get('type') == 'tool' and p.get('state', {}).get('status') in ('running', 'pending')]
            if role == 'assistant' and text:
                self.last_answer = text
            if text or activity:
                entries.append((role, text, activity))
        self.copy.setEnabled(bool(self.last_answer))
        if entries == self.rendered:
            return
        self.rendered = entries
        scroll = self.transcript.verticalScrollBar()
        bottom = scroll.value() >= scroll.maximum() - 30
        position = scroll.value()
        document = []
        for role, text, activity in entries:
            # Qt's Markdown parser handles formatting without interpreting raw HTML.
            md = SafeDocument()
            md.setMarkdown(text, QTextDocument.MarkdownFeatures(QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML))
            body = md.toHtml().split('<body', 1)[1].split('>', 1)[1].rsplit('</body>', 1)[0]
            document.append('<p style="color:#9bdcca;font-size:11px"><b>' + ('DU' if role == 'user' else 'LUMEN') + '</b></p>')
            document.append(body)
            if activity:
                document.append('<p style="color:#a3b0c2">' + html.escape(' · '.join(activity)) + ' …</p>')
            document.append('<hr>')
        self.transcript.setHtml(''.join(document) or '<h2>Wobei kann ich dir helfen?</h2><p>Dateien verstehen, etwas prüfen oder eine Aufgabe erledigen.</p>')
        scroll.setValue(scroll.maximum() if bottom else position)

    def show_requests(self, permissions, questions):
        ids = tuple(p['id'] for p in permissions) + tuple(q['id'] for q in questions)
        if ids == self.request_ids:
            return
        self.request_ids = ids
        content = QWidget()
        layout = QVBoxLayout(content)
        for request in permissions:
            title = label('Freigabe benötigt: ' + request['permission'])
            title.setWordWrap(True)
            layout.addWidget(title)
            detail = label('\n'.join(request.get('patterns', [])), 'muted')
            detail.setWordWrap(True)
            detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(detail)
            row = QHBoxLayout()
            for caption, allow in [('Ablehnen', False), ('Einmal erlauben', True)]:
                button = QPushButton(caption)
                button.clicked.connect(lambda _=False, rid=request['id'], yes=allow: self.backend.permission_reply(rid, yes))
                row.addWidget(button)
            layout.addLayout(row)
        for request in questions:
            inputs = []
            for question in request['questions']:
                title = label(question['question'])
                title.setWordWrap(True)
                layout.addWidget(title)
                choices = []
                combo = None
                if question.get('multiple'):
                    for option in question['options']:
                        check = QCheckBox(option['label'])
                        check.setToolTip(option.get('description', ''))
                        layout.addWidget(check)
                        choices.append(check)
                else:
                    combo = QComboBox()
                    combo.addItem('Bitte wählen …', None)
                    for option in question['options']:
                        combo.addItem(option['label'], option['label'])
                        combo.setItemData(combo.count() - 1, option.get('description', ''), Qt.ToolTipRole)
                    layout.addWidget(combo)
                custom = QLineEdit() if question.get('custom', True) else None
                if custom:
                    custom.setPlaceholderText('Eigene Antwort')
                    custom.setAccessibleName('Eigene Antwort auf: ' + question['question'])
                    layout.addWidget(custom)
                inputs.append((choices, combo, custom))
            row = QHBoxLayout()
            dismiss = QPushButton('Überspringen')
            dismiss.clicked.connect(lambda _=False, rid=request['id']: self.backend.question_reply(rid))
            reply = QPushButton('Antwort senden')
            reply.clicked.connect(lambda _=False, rid=request['id'], fields=inputs: self.answer_question(rid, fields))
            row.addWidget(dismiss)
            row.addWidget(reply)
            layout.addLayout(row)
        old = self.requests.takeWidget()
        if old:
            old.deleteLater()
        self.requests.setWidget(content)
        self.requests.setVisible(bool(ids))

    def answer_question(self, request_id, fields):
        answers = []
        for choices, combo, custom in fields:
            answer = [c.text() for c in choices if c.isChecked()]
            if combo and combo.currentData():
                answer.append(combo.currentData())
            if custom and custom.text().strip():
                if combo:
                    answer = []
                answer.append(custom.text().strip())
            if not answer:
                self.show_error('Bitte jede Frage beantworten oder die Rückfrage überspringen.')
                return
            answers.append(answer)
        self.error.hide()
        self.backend.question_reply(request_id, answers)

    def can_close(self):
        return not self.backend.busy or QMessageBox.question(
            self, 'Lumen arbeitet noch', 'Den laufenden Vorgang abbrechen und schließen?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes
