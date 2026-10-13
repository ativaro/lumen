"""Stable navigation with directly accessible conversation history."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QMenu)
from lumen_i18n import tr
from preview import label
from studio_design import icon, surface


class StudioNavigation(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.session_limit = 5; self.sessions = []; self.session_directory = window.chat.backend.directory
        self.window = window; self.setObjectName('studioNavigation'); surface(self)
        self.setMinimumWidth(200); self.setMaximumWidth(420)
        self.root = QVBoxLayout(self); self.root.setContentsMargins(16, 20, 16, 12); self.root.setSpacing(6)
        self.create = self.entry(tr('Neues Gespräch'), 'list-add', self.new_chat)
        self.create.setObjectName('studioNewChat'); self.root.addWidget(self.create); self.root.addSpacing(12)
        self.buttons = {}
        conversations = self.entry(tr('Gespräche'), 'dialog-messages', lambda: self.navigate(0))
        conversations.setCheckable(True); self.buttons[0] = conversations; self.root.addWidget(conversations)
        self.history = QWidget(); box = QVBoxLayout(self.history); box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(label(tr('Letzte Gespräche'), 'studioEyebrow'))
        self.recent = QListWidget(); self.recent.setObjectName('studioRecent'); self.recent.setSpacing(2)
        self.recent.setMinimumHeight(70); self.recent.setAccessibleName(tr('Letzte Gespräche'))
        self.recent.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.recent.itemActivated.connect(self.open_session); self.recent.itemClicked.connect(self.open_session)
        box.addWidget(self.recent, 1)
        self.load_more = QPushButton(tr('Mehr laden')); self.load_more.setObjectName('studioNav'); self.load_more.clicked.connect(self.show_more); box.addWidget(self.load_more)
        self.empty = label(tr('Deine Gespräche erscheinen hier.'), 'muted'); self.empty.setWordWrap(True); box.addWidget(self.empty); box.addStretch()
        self.root.addWidget(self.history, 1)
        self.maintenance = self.entry(tr('Wartung & Diagnose'), 'go-next', lambda: None)
        self.maintenance.setCheckable(True); self.root.addWidget(self.maintenance)
        self.diagnostics = QWidget(); diagnostics = QVBoxLayout(self.diagnostics)
        diagnostics.setContentsMargins(8, 0, 0, 0); diagnostics.setSpacing(0)
        for index, title, name in [(4, tr('Alle Tasks anzeigen'), 'view-task'), (1, tr('Systemstatus'), 'dialog-information')]:
            control = self.entry(title, name, lambda _=False, i=index: self.navigate(i)); control.setCheckable(True)
            diagnostics.addWidget(control); self.buttons[index] = control
        self.root.addWidget(self.diagnostics); self.diagnostics.hide()
        self.maintenance.toggled.connect(self.diagnostics.setVisible)
        self.maintenance.toggled.connect(lambda opened: self.maintenance.setIcon(icon('go-down' if opened else 'go-next')))
        menu = QMenu(self)
        for index, title in [(3, tr('Dateien')), (5, tr('Notes')), (6, tr('Abläufe')), (7, tr('Modelle')), (9, tr('Apps'))]:
            menu.addAction(title, lambda i=index: self.navigate(i))
        menu.addAction(tr('Persönlich'), lambda: self.navigate(8))
        menu.addSeparator(); menu.addAction(tr('Ordner wählen'), window.choose_directory)
        menu.addAction(tr('Einstellungen'), window.show_settings)
        self.account = self.entry(tr('Lumen-Menü'), 'view-more-symbolic', lambda: None); self.account.setMenu(menu)
        self.account.setObjectName('studioAccount'); self.root.addWidget(self.account)
        self.account_hint = label(tr('Auf diesem Desktop'), 'studioEyebrow'); self.root.addWidget(self.account_hint)
        backend = window.chat.backend
        backend.sessionsChanged.connect(self.set_sessions); backend.sessionChanged.connect(self.select_session)
        backend.busyChanged.connect(lambda busy: self.recent.setEnabled(not busy))
        self.set_sessions([]); self.show_page(0)

    def entry(self, title, name, callback):
        control = QPushButton(title.replace('&', '&&')); control.setObjectName('studioNav'); control.setIcon(icon(name))
        control.setProperty('label', title); control.setToolTip(title); control.setAccessibleName(title)
        control.setIconSize(QSize(18, 18)); control.setMinimumHeight(36); control.clicked.connect(callback)
        return control

    def show_page(self, index):
        if index in (1, 4): self.maintenance.setChecked(True)
        for key, control in self.buttons.items(): control.setChecked(key == index)

    def navigate(self, index):
        self.window.show_page(index)

    def new_chat(self):
        self.window.show_page(0); self.window.chat.new_conversation()

    def set_sessions(self, sessions):
        directory = self.window.chat.backend.directory
        if directory != self.session_directory: self.session_limit = 5; self.session_directory = directory
        self.sessions = sorted(sessions, key=lambda s: s.get('time', {}).get('updated', 0), reverse=True)
        self.render_sessions()

    def show_more(self):
        position = self.recent.verticalScrollBar().value(); self.session_limit += 5
        self.render_sessions(); self.recent.verticalScrollBar().setValue(position)

    def render_sessions(self):
        self.recent.clear()
        for session in self.sessions[:self.session_limit]:
            title = session.get('title') or tr('Gespräch')
            item = QListWidgetItem(icon('dialog-messages'), title)
            item.setData(Qt.UserRole, session['id']); item.setToolTip(title); item.setSizeHint(QSize(0, 38)); self.recent.addItem(item)
        self.recent.setMaximumHeight(max(70, self.recent.count() * 42 + 4))
        self.load_more.setVisible(len(self.sessions) > self.session_limit)
        self.recent.setVisible(bool(self.recent.count())); self.empty.setVisible(not self.recent.count()); self.select_session(self.window.chat.backend.session)

    def select_session(self, session):
        self.recent.setCurrentRow(next((i for i in range(self.recent.count()) if self.recent.item(i).data(Qt.UserRole) == session), -1))

    def open_session(self, item):
        chat = self.window.chat
        if chat.backend.busy or item.data(Qt.UserRole) == chat.backend.session:
            self.select_session(chat.backend.session); return
        if chat.composer.toPlainText().strip() or chat.paths:
            self.select_session(chat.backend.session)
            chat.show_error(tr('Bitte den Entwurf oder angehängte Dateien zuerst abschließen.')); return
        index = chat.sessions.findData(item.data(Qt.UserRole))
        if index >= 0: chat.open_session(index); self.window.show_page(0)
