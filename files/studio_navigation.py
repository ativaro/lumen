"""Quiet primary navigation and actual conversation history for the desktop app."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem, QMenu
from lumen_i18n import tr
from preview import label


class StudioNavigation(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window; self.setObjectName('studioNavigation'); self.setFixedWidth(224)
        root = QVBoxLayout(self); root.setContentsMargins(16, 24, 16, 18); root.setSpacing(10)
        brand = QHBoxLayout(); mark = label(''); mark.setPixmap(QIcon.fromTheme('lumen').pixmap(34, 34)); brand.addWidget(mark)
        brand.addWidget(label('Lumen', 'studioBrand'), 1); root.addLayout(brand); root.addSpacing(28)
        self.buttons = {}
        for index, title, icon in [(0, tr('Gespräche'), 'dialog-messages'), (4, tr('Aufträge'), 'view-task'), (8, tr('Arbeitsräume'), 'folder-open')]:
            control = self.entry(title, icon, lambda _=False, i=index: window.show_page(i)); control.setCheckable(True)
            root.addWidget(control); self.buttons[index] = control
        root.addSpacing(20); root.addWidget(label(tr('Letzte Gespräche'), 'muted'))
        self.recent = QListWidget(); self.recent.setObjectName('studioRecent'); self.recent.setSpacing(4)
        self.recent.setAccessibleName(tr('Letzte Gespräche')); self.recent.setWordWrap(False)
        self.recent.itemActivated.connect(self.open_session); self.recent.itemClicked.connect(self.open_session)
        root.addWidget(self.recent, 1)
        self.empty = label(tr('Deine Gespräche erscheinen hier.'), 'muted'); self.empty.setWordWrap(True); root.addWidget(self.empty)
        more = self.entry(tr('Mehr'), 'view-more-symbolic', lambda: None); menu = QMenu(more)
        for index, title in [(1, tr('Systemstatus')), (3, tr('Dateien')), (5, tr('Wissen')), (6, tr('Abläufe')), (7, tr('Modelle'))]:
            menu.addAction(title, lambda i=index: window.show_page(i))
        menu.addSeparator(); menu.addAction(tr('Ordner wählen'), window.choose_directory)
        menu.addAction(tr('Datei-Arbeitsräume'), window.show_rooms); more.setMenu(menu); root.addWidget(more)
        apps = self.entry(tr('Apps'), 'view-grid', lambda: window.show_page(9)); apps.setCheckable(True)
        self.buttons[9] = apps; root.addWidget(apps)
        root.addWidget(self.entry(tr('Einstellungen'), 'configure', window.show_settings))
        backend = window.chat.backend
        backend.sessionsChanged.connect(self.set_sessions); backend.sessionChanged.connect(self.select_session)
        backend.busyChanged.connect(lambda busy: self.recent.setEnabled(not busy))
        self.set_sessions([])

    def entry(self, title, icon, callback):
        control = QPushButton(title); control.setObjectName('studioNav'); control.setIcon(QIcon.fromTheme(icon))
        control.setIconSize(QSize(20, 20)); control.setMinimumHeight(46); control.clicked.connect(callback)
        return control

    def set_sessions(self, sessions):
        self.recent.clear()
        for session in sorted(sessions, key=lambda s: s.get('time', {}).get('updated', 0), reverse=True)[:20]:
            title = session.get('title') or tr('Gespräch')
            item = QListWidgetItem(QIcon.fromTheme('dialog-messages'), title)
            item.setData(Qt.UserRole, session['id']); item.setToolTip(title); item.setSizeHint(QSize(180, 44)); self.recent.addItem(item)
        self.empty.setVisible(not self.recent.count()); self.select_session(self.window.chat.backend.session)

    def select_session(self, session):
        self.recent.setCurrentRow(next((i for i in range(self.recent.count()) if self.recent.item(i).data(Qt.UserRole) == session), -1))

    def open_session(self, item):
        chat = self.window.chat
        if chat.backend.busy or item.data(Qt.UserRole) == chat.backend.session: return
        index = chat.sessions.findData(item.data(Qt.UserRole))
        if index >= 0: chat.open_session(index); self.window.show_page(0)
