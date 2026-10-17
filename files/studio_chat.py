"""Studio presentation of the shared chat, retaining its interaction contract."""
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QWidget, QFrame, QHBoxLayout, QVBoxLayout, QPushButton, QMenu
from assistant import ChatPanel
from lumen_i18n import tr
from preview import label
from studio_design import surface, icon


def clear_layout(layout, parking):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget(): item.widget().setParent(parking)
        elif item.layout():
            clear_layout(item.layout(), parking); item.layout().deleteLater()


def icon_button(title, name, callback):
    control = QPushButton(); control.setObjectName('studioIcon')
    control.setIcon(icon(name)); control.setIconSize(QSize(18, 18)); control.setFixedSize(28, 28)
    control.setAccessibleName(title); control.setToolTip(title); control.clicked.connect(callback)
    return control


class StudioChat(ChatPanel):
    resultChanged = Signal(object)
    answerChanged = Signal()
    taskRequested = Signal(str)
    previewRequested = Signal()

    def __init__(self, directory, **kwargs):
        super().__init__(directory, **kwargs)
        self.studio_ready = False
        self.presentation = None
        self.backend.presentation_enabled = True
        self.backend.messagesChanged.connect(self.update_results)
        self.parking = QWidget(self); self.parking.hide()
        root = self.layout(); clear_layout(root, self.parking)
        root.setContentsMargins(18, 0, 18, 14); root.setSpacing(10)
        self.setObjectName('studioChat'); surface(self)
        top = QHBoxLayout(); top.setContentsMargins(4, 0, 0, 0)
        caption = label(tr('Gespräch'), 'studioSection'); caption.setMinimumHeight(48); top.addWidget(caption, 1)
        self.execution.setMaximumWidth(160)
        self.preview_button = icon_button(tr('Ergebnis öffnen'), 'view-preview', self.previewRequested.emit)
        from conversation_actions import continue_elsewhere, teach
        self.continue_button = icon_button(tr('Auf anderen Geräten fortsetzen'), 'computer', lambda: continue_elsewhere(self))
        top.addWidget(self.continue_button)
        self.backend.busyChanged.connect(lambda busy: self.continue_button.setEnabled(not busy))
        top.addWidget(self.preview_button)
        root.addLayout(top)
        self.context_chip = label('', 'studioContext')
        self.options_box = QWidget(); options = QVBoxLayout(self.options_box); options.setContentsMargins(0, 0, 0, 0)
        for widget in (self.sessions, self.server_retry, self.server_model, self.persona, self.mode, self.dont_ask, self.context_tools.learn): options.addWidget(widget)
        root.addWidget(self.options_box)
        self.options.toggled.connect(self.options_box.setVisible); self.options_box.hide()
        from studio_transcript import StudioTranscript
        self.transcript = StudioTranscript(self.transcript, self)
        from rich_controller import RichController
        from rich_widget import RichWidget
        self.rich = RichController(self.backend, self)
        self.rich.failed.connect(self.show_error)
        self.rich.submitted.connect(self.submit_view)
        self.rich_widget = RichWidget(self.rich, self.settings, self)
        self.transcript.box.insertWidget(self.transcript.box.count()-1, self.rich_widget)
        root.addWidget(self.transcript, 1); root.addWidget(self.requests); root.addWidget(self.error)
        root.addWidget(self.action_buttons); root.addWidget(self.progress)
        voice = self.context_tools.conversation
        if voice: root.addWidget(voice.indicator)
        self.composer_surface = QFrame(); self.composer_surface.setObjectName('studioComposer')
        composer_box = QVBoxLayout(self.composer_surface); composer_box.setContentsMargins(10, 8, 10, 7); composer_box.setSpacing(1)
        compose = QHBoxLayout(); compose.setSpacing(6); composer_box.addLayout(compose)
        self.attach = icon_button(tr('Dateien und Kontext hinzufügen'), 'list-add', lambda: None)
        menu = QMenu(self.attach)
        menu.addAction(tr('Dateien hinzufügen'), self.context_tools.files)
        menu.addAction(tr('Bildschirm aufnehmen'), self.context_tools.screenshot)
        menu.addAction(tr('Lumen begleitet mich'), self.context_tools.companion)
        menu.addAction(tr('Zwischenablage einfügen'), self.context_tools.clipboard)
        menu.addAction(self.context_tools.voice)
        menu.addSeparator(); menu.addAction(tr('Kontext entfernen'), self.context_tools.clear)
        if voice: menu.addAction(tr('Sprachgespräch einstellen …'), voice.controls)
        self.attach.setMenu(menu); compose.addWidget(self.attach)
        self.composer.setObjectName('studioInput'); self.composer.setFixedHeight(54)
        self.composer.setPlaceholderText(tr('Weiter mit Lumen besprechen …')); compose.addWidget(self.composer, 1)
        if voice:
            self.mic = icon_button(tr('Sprachgespräch starten oder beenden'), 'audio-input-microphone', voice.toggle)
            self.mic.setCheckable(True); voice.changed.connect(self.voice_changed); compose.addWidget(self.mic)
            self.interrupt_voice = icon_button(tr('Unterbrechen'), 'media-playback-pause', voice.interrupt)
            self.interrupt_voice.hide(); compose.addWidget(self.interrupt_voice)
        self.send_button.setText('↑'); self.send_button.setAccessibleName(tr('Senden')); self.send_button.setToolTip(tr('Senden'))
        self.send_button.setFixedSize(30, 30); compose.addWidget(self.send_button)
        meta = QHBoxLayout(); meta.addWidget(self.context_chip, 1)
        self.mode_hint = label('', 'studioContext'); meta.addWidget(self.mode_hint); composer_box.addLayout(meta)
        self.mode.currentIndexChanged.connect(self.update_context)
        self.dont_ask.toggled.connect(self.update_context)
        root.addWidget(self.composer_surface)
        footer = QHBoxLayout(); footer.addWidget(self.status, 1)
        self.pause_task = QPushButton(tr('Pausieren')); self.pause_task.clicked.connect(self.tracker.pause); footer.addWidget(self.pause_task)
        self.open_task = QPushButton(tr('Auftrag')); self.open_task.clicked.connect(lambda: self.taskRequested.emit(self.tracker.task_id)); footer.addWidget(self.open_task)
        footer.addWidget(self.stop); footer.addWidget(self.close_action)
        self.backend.busyChanged.connect(self.update_task_controls); self.backend.sessionChanged.connect(self.update_task_controls)
        self.tracker.changed.connect(self.update_task_controls); self.update_task_controls()
        self.output_menu = QMenu(self)
        for title, control in [(tr('Kopieren'), self.copy), (tr('Für mich speichern'), self.save_note_button),
                (tr('Merk dir das'), self.remember_button), (tr('Als Dateiaktion speichern …'), self.save_file_action)]:
            action = self.output_menu.addAction(title, control.click)
            self.output_menu.aboutToShow.connect(lambda a=action, c=control: a.setEnabled(c.isEnabled() and bool(self.last_answer) and (c is not self.save_file_action or not c.isHidden())))
        from lumen_detail_routes import launch
        self.save_tool_action = self.output_menu.addAction(tr('Als Werkzeug speichern'), lambda: launch('lumen-code', ['--save-task', self.tracker.task_id]))
        self.output_menu.aboutToShow.connect(lambda: self.save_tool_action.setEnabled(bool(self.tracker.task_id) and not self.backend.busy))
        from note_reviews import show_reviews
        reviews = QPushButton(tr('Vorschläge & Verlauf'))
        reviews.clicked.connect(lambda: show_reviews(self)); footer.addWidget(reviews)
        self.teach_action = self.output_menu.addAction(tr('Als Lösungsweg lernen …'), lambda: teach(self))
        self.output_menu.aboutToShow.connect(lambda: self.teach_action.setEnabled(bool(self.last_answer) and not self.backend.busy and not self.memory_capture_job))
        output = icon_button(tr('Antwort verwenden'), 'view-more-symbolic', lambda: None)
        output.setMenu(self.output_menu); footer.addWidget(output); root.addLayout(footer)
        root.addWidget(self.memory_status)
        root.addWidget(self.memory_sources,0,Qt.AlignLeft)
        self.studio_ready = True
        self.update_context(); self.show_options(False); self.rendered = None; self.show_messages(self.backend.messages)
        self.backend.sessionChanged.connect(lambda _: self.update_title())
        self.backend.sessionsChanged.connect(lambda _: self.update_title())
        self.update_title(); self.apply_typography()
        # Widgets moved out of the hidden parking container retain their explicit
        # visibility; transient states still come from the shared chat controller.
        for widget in (self.transcript, self.composer, self.send_button, self.status): widget.show()
        self.execution.setVisible(hasattr(self.backend, 'set_execution'))
        self.requests.setVisible(bool(self.request_ids)); self.error.hide(); self.action_buttons.hide(); self.progress.hide()
        self.stop.hide(); self.close_action.hide(); self.memory_status.hide()

    def voice_changed(self):
        voice = self.context_tools.conversation
        self.mic.setChecked(voice.active); self.mic.setToolTip(voice.status)
        self.interrupt_voice.setVisible(voice.active and voice.state in ('thinking', 'preparing', 'speaking'))

    def update_results(self, messages):
        from studio_results import from_messages
        result = from_messages(messages)
        if result == self.presentation: return
        self.presentation = result
        self.resultChanged.emit(result)

    def show_messages(self, messages):
        super().show_messages(messages)
        if getattr(self, 'studio_ready', False): self.answerChanged.emit()

    def update_task_controls(self, *_):
        active = self.backend.busy and self.tracker.lease is not None
        self.pause_task.setVisible(active and getattr(self.backend, 'execution', 'local') == 'local')
        self.open_task.setVisible(active)

    def reload_settings(self, filename, keys):
        super().reload_settings(filename, keys)
        if filename == self.settings.fileName() and {'textSize', 'contentDensity'} & set(keys):
            self.transcript.refresh_typography()
            self.apply_typography()

    def apply_typography(self):
        from ui_typography import metrics
        values = metrics(self.settings)
        size = max(13, values['fontSize']-4)
        self.setStyleSheet('QWidget#studioChat { font-family: "DM Sans 9pt"; }'
            +'QPlainTextEdit#studioInput, QWidget#studioChat QTextBrowser { font-size: '+str(size)+'px; }')
        self.composer.setFixedHeight(size*2+8)
        if hasattr(self, 'rich_widget'): self.rich_widget.refresh()

    def changeEvent(self, event):
        super().changeEvent(event)
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.PaletteChange and hasattr(self, 'rich_widget'):
            self.rich_widget.refresh()

    def submit_view(self, text, data):
        if self.backend.busy: return
        self.last_prompt = text; self.error.hide()
        self.backend.send(text, [], agent=self.mode.currentData(), memory_text=text, context_data=data)

    def recovery_state(self):
        state = super().recovery_state()
        state['presentation'] = self.presentation
        state['rich_view'] = self.rich.recovery_state()
        return state

    def restore_recovery(self, state):
        super().restore_recovery(state)
        from studio_results import validate
        try: result = validate(state.get('presentation'))
        except ValueError: result = None
        self.presentation = result
        self.resultChanged.emit(result)
        self.rich.restore(state.get('rich_view'))

    def update_title(self):
        if self.action: return
        index = self.sessions.findData(self.backend.session) if self.backend.session else -1
        title = self.sessions.itemText(index) if index >= 0 else tr('Neues Gespräch')
        self.heading.setText(title); self.heading.setWordWrap(False)

    def show_options(self, visible):
        super().show_options(visible)
        if getattr(self, 'studio_ready', False): self.options_box.setVisible(visible)

    def update_context(self):
        super().update_context()
        if not getattr(self, 'studio_ready', False): return
        directory = Path(self.backend.directory).name or '/'
        self.context_chip.setText(tr('{0} · {1} Dateien', directory, len(self.paths)) if len(self.paths) > 1 else
            Path(self.paths[0]).name if self.paths else directory)
        self.context_chip.setToolTip(self.context.toolTip())
        self.mode_hint.setText(tr('Nur lesen') if self.mode.currentData() == 'plan' else
            tr('Automatische Freigabe') if self.dont_ask.isChecked() else tr('Mit Freigaben'))

    def set_action(self, action):
        super().set_action(action)
        if getattr(self, 'studio_ready', False):
            self.composer_surface.setVisible(not self.action); self.update_title()

    def position_messages(self, position, answer_index):
        if not getattr(self, 'studio_ready', False):
            return super().position_messages(position, answer_index)
        self.transcript.entries(self.rendered, self.action)
        self.transcript.position_turn(position, answer_index)
