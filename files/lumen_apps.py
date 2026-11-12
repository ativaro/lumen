"""Shared native app catalogue, launch routes and overview."""
from pathlib import Path
import sys
from PySide6.QtCore import QProcess, QSettings, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QScrollArea, QMessageBox)
from lumen_i18n import tr
from desktop_design import AppHeader, PAGE_MARGIN, PAGE_SPACING


def catalogue(*, include_utilities=False):
    apps = [
        ('lumen', 'Lumen', tr('Suchen, sprechen und in der Detailansicht weiterarbeiten'), 'lumen'),
        ('files', 'Lumen Files', tr('Dateien, Netzwerkorte und Vorschauen'), 'system-file-manager'),
        ('search', tr('Lumen Suche'), tr('Apps und Dateien finden, mit Lumen sprechen'), 'system-search'),
        ('companion', 'Lumen Companion', tr('Hilfe im gewählten Fenster · Schritt für Schritt'), 'video-display'),
        ('translate', 'Lumen Compose', tr('Übersetzen, umformulieren und korrigieren'), 'preferences-desktop-locale'),
        ('wissen', tr('Lumen Notes'), tr('Deine Notizen, Sammlungen und Quellen'), 'accessories-text-editor'),
        ('inbox', 'Lumen Inbox', tr('Nachrichten und Kalender an einem Ort'), 'mail-unread'),
        ('notification', 'Lumen Notification', tr('Meldungen, Ergebnisse und Erinnerungen'), 'notifications'),
        ('vault', 'Lumen Vault', tr('Passwörter und geschützte Einträge'), 'document-encrypt'),
        ('reader', 'Lumen Reader', tr('Lesen, markieren und vorlesen lassen'), 'application-pdf'),
        ('updater', 'Lumen Updater', tr('Lumen, Apps und Erweiterungen aktualisieren'), 'system-software-update'),
        ('system', 'Lumen System', tr('Geräte, Sound, Updates und Diagnose'), 'utilities-system-monitor'),
        ('meetings', tr('Lumen Audio Studio'), tr('Aufnahmen, Transkripte und dein persönliches Hörprogramm'), 'audio-input-microphone'),
        ('household', tr('Lumen Digitaler Haushalt'), tr('Dokumente und Fristen im Blick behalten'), 'view-calendar'),
        ('workbench', tr('Lumen Projekte'), tr('Projekte und ihre nächsten Schritte organisieren'), 'folder-development'),
        ('code', tr('Lumen Code & Automation'), tr('Werkzeuge, Automationen, Zeitpläne und Code-Projekte'), 'code-context'),
    ]

    return apps if include_utilities else [row for row in apps if row[0] not in ('search', 'updater', 'notification', 'companion', 'household', 'reader', 'translate')]


COMPANIONS = ('translate', 'wissen', 'inbox', 'vault', 'reader', 'meetings', 'household', 'workbench', 'radio', 'code')
from server_app_session import APP_NAMES
SERVER_APPS = {desktop.removeprefix('lumen-'): kind for kind, (_, desktop) in APP_NAMES.items()}


def startup_preference(app, key, settings=None):
    prefs = settings if settings is not None else QSettings('Lumen', 'Assistant')
    prefs.sync()
    return prefs.value(f'apps/{app}/{key}', True, type=bool)


def launch(app, *, area=None, page=None):
    known = {item[0] for item in catalogue(include_utilities=True)}
    if app not in known | {'apps', 'radio', 'sound'}: raise ValueError(tr('Unbekannte Lumen-App.'))
    if area is not None and (app != 'wissen' or area not in ('user', 'lumen')):
        raise ValueError(tr('Unbekannter Bereich.'))
    if app == 'sound': app, page = 'system', 'sound'
    if app == 'updater': app, page = 'system', 'updates'
    if page is not None and (app != 'system' or page not in ('system', 'sound', 'server', 'updates', 'diagnostics')):
        raise ValueError(tr('Unbekannter Systembereich.'))
    folder = Path(__file__).resolve().parent
    if app == 'notification':
        from lumen_notifications import open_center
        open_center()
        return
    if app in COMPANIONS and app != 'vault':
        args = [str(folder / 'tools_app.py'), app]
        if area: args += ['--area', area]
        executable = sys.executable
    else:
        name = {'lumen': 'lumen-agent-app', 'apps': 'lumen-agent-app', 'files': 'lumen-files', 'search': 'lumen-search', 'system': 'lumen-system', 'vault': 'lumen-vault', 'updater': 'lumen-updater', 'companion': 'lumen-companion'}[app]
        from lumen_launch import executable as resolve_executable
        executable = resolve_executable(name)
        args = ['--page', 'apps'] if app == 'apps' else ['--page', page] if page else []
    started, _ = QProcess.startDetached(executable, args)
    if not started: raise OSError(tr('Die App konnte nicht gestartet werden. Bitte die Lumen-Installation prüfen.'))


class AppCenter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self); outer.setContentsMargins(PAGE_MARGIN, 20, PAGE_MARGIN, PAGE_SPACING); outer.setSpacing(PAGE_SPACING)
        header = AppHeader('Lumen Apps', tr('Ein Zuhause für deine Lumen-Apps.'))
        self.notifications = QPushButton(QIcon.fromTheme('notifications'), tr('Meldungen'))
        self.notifications.clicked.connect(lambda: self.open('notification'))
        header.actions.addWidget(self.notifications); outer.addWidget(header)
        self.search = QLineEdit(); self.search.setPlaceholderText(tr('App finden …')); self.search.setAccessibleName(tr('Lumen-Apps durchsuchen')); outer.addWidget(self.search)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget(); self.grid = QGridLayout(content); self.grid.setContentsMargins(0, 0, 0, 0); self.grid.setSpacing(14)
        scroll.setWidget(content); outer.addWidget(scroll, 1)
        self.cards = []
        for app, title, description, icon in catalogue():
            card = QFrame(); card.setObjectName('appCard'); card.setFrameShape(QFrame.StyledPanel)
            box = QVBoxLayout(card); box.setContentsMargins(20, 18, 20, 18); box.setSpacing(10)
            top = QHBoxLayout(); mark = QLabel(); mark.setPixmap(QIcon.fromTheme('lumen' if app == 'lumen' else 'lumen-' + app, QIcon.fromTheme(icon)).pixmap(40, 40)); top.addWidget(mark)
            name = QLabel(title); name.setWordWrap(True); font = name.font(); font.setBold(True); name.setFont(font); top.addWidget(name, 1); box.addLayout(top)
            detail = QLabel(description); detail.setWordWrap(True); detail.setObjectName('muted'); box.addWidget(detail); box.addStretch()
            row = QHBoxLayout()
            for text, callback in ((tr('Öffnen'), lambda _=False, key=app: self.open(key)),
                                   (tr('Einstellungen'), lambda _=False, key=app: self.settings(key))):
                if app == 'vault' and text == tr('Einstellungen'): continue
                b = QPushButton(text); b.setAccessibleName(title + ' · ' + text); b.clicked.connect(callback); row.addWidget(b)
            box.addLayout(row); self.cards.append((card, (title + ' ' + description).casefold()))
        self.empty = QLabel(tr('Keine passende App gefunden.')); outer.addWidget(self.empty)
        self.search.textChanged.connect(self.reflow); self.reflow()

    def resizeEvent(self, event):
        super().resizeEvent(event); self.reflow()

    def reflow(self):
        if not hasattr(self, 'cards'): return
        while self.grid.count(): self.grid.takeAt(0)
        for row in range(self.grid.rowCount()): self.grid.setRowStretch(row, 0)
        query = self.search.text().strip().casefold(); columns = 3 if self.width() >= 1080 else 2 if self.width() >= 650 else 1
        visible = 0
        for card, haystack in self.cards:
            match = query in haystack; card.setVisible(match)
            if match: self.grid.addWidget(card, visible // columns, visible % columns); visible += 1
        self.empty.setVisible(not visible)
        self.grid.setRowStretch((visible + columns - 1) // columns, 1)

    def open(self, app):
        try: launch(app)
        except (ValueError, OSError) as error: QMessageBox.warning(self, 'Lumen Apps', str(error))

    def settings(self, app):
        from settings_dialog import SettingsDialog
        dialog = SettingsDialog(self, application=app)
        host = self.window()
        if hasattr(host, 'chat'): dialog.preferencesChanged.connect(host.chat.reload_settings)
        if getattr(host, 'file_window', None) is not None: dialog.preferencesChanged.connect(host.file_window.reload_settings)
        dialog.exec(); dialog.deleteLater()
