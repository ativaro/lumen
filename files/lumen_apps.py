"""Shared native app catalogue, launch routes and overview."""
from pathlib import Path
import sys
from PySide6.QtCore import QProcess, QSettings, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QScrollArea, QMessageBox)
from lumen_i18n import tr


def catalogue():
    return [
        ('lumen', 'Lumen', tr('Gespräche, Aufträge und dein System'), 'lumen'),
        ('files', 'Lumen Files', tr('Dateien, Netzwerkorte und Vorschauen'), 'system-file-manager'),
        ('search', tr('Lumen Suche'), tr('Apps und Dateien finden, mit Lumen sprechen'), 'system-search'),
        ('translate', 'Lumen Translate', tr('Übersetzen, umformulieren und korrigieren'), 'preferences-desktop-locale'),
        ('wissen', tr('Lumen Wissen'), tr('Deine Notizen und Lumens Gedächtnis'), 'accessories-text-editor'),
        ('inbox', 'Lumen Inbox', tr('Nachrichten und Kalender an einem Ort'), 'mail-unread'),
        ('vault', 'Lumen Vault', tr('Sicherungen planen und wiederherstellen'), 'document-save'),
        ('reader', 'Lumen Reader', tr('Lesen, markieren und vorlesen lassen'), 'application-pdf'),
        ('sound', 'Lumen Sound', tr('Audioausgabe und Lautstärke steuern'), 'audio-volume-high'),
        ('meetings', tr('Lumen Meeting-Werkstatt'), tr('Aufnahmen transkribieren und zusammenfassen'), 'audio-input-microphone'),
        ('household', tr('Lumen Digitaler Haushalt'), tr('Dokumente und Fristen im Blick behalten'), 'view-calendar'),
        ('workbench', tr('Lumen Projekt-Werkbank'), tr('Projekte und ihre nächsten Schritte organisieren'), 'folder-development'),
        ('radio', tr('Lumen Persönliches Radio'), tr('Deine Inhalte als Hörprogramm'), 'media-playback-start'),
    ]


COMPANIONS = ('translate', 'wissen', 'inbox', 'vault', 'reader', 'sound', 'meetings', 'household', 'workbench', 'radio')


def startup_preference(app, key, settings=None):
    prefs = settings if settings is not None else QSettings('Lumen', 'Assistant')
    prefs.sync()
    return prefs.value(f'apps/{app}/{key}', True, type=bool)


def launch(app, *, area=None):
    known = {item[0] for item in catalogue()}
    if app not in known | {'apps'}: raise ValueError(tr('Unbekannte Lumen-App.'))
    if area is not None and (app != 'wissen' or area not in ('user', 'lumen')):
        raise ValueError(tr('Unbekannter Wissensbereich.'))
    folder = Path(__file__).resolve().parent
    if app in COMPANIONS:
        args = [str(folder / 'tools_app.py'), app]
        if area: args += ['--area', area]
        executable = sys.executable
    else:
        name = {'lumen': 'lumen-agent-app', 'apps': 'lumen-agent-app', 'files': 'lumen-files', 'search': 'lumen-search'}[app]
        from lumen_launch import executable as resolve_executable
        executable = resolve_executable(name)
        args = ['--page', 'apps'] if app == 'apps' else []
    started, _ = QProcess.startDetached(executable, args)
    if not started: raise OSError(tr('Die App konnte nicht gestartet werden. Bitte die Lumen-Installation prüfen.'))


class AppCenter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self); outer.setContentsMargins(24, 20, 24, 16); outer.setSpacing(16)
        heading = QLabel('Lumen Apps'); heading.setObjectName('heading'); outer.addWidget(heading)
        subtitle = QLabel(tr('Ein Zuhause für deine Lumen-Apps.')); subtitle.setObjectName('muted'); outer.addWidget(subtitle)
        self.search = QLineEdit(); self.search.setPlaceholderText(tr('App finden …')); self.search.setAccessibleName(tr('Lumen-Apps durchsuchen')); outer.addWidget(self.search)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget(); self.grid = QGridLayout(content); self.grid.setContentsMargins(0, 0, 0, 0); self.grid.setSpacing(14)
        scroll.setWidget(content); outer.addWidget(scroll, 1)
        self.cards = []
        for app, title, description, icon in catalogue():
            card = QFrame(); card.setObjectName('appCard')
            card.setStyleSheet('QFrame#appCard { background: palette(base); border: 1px solid palette(mid); border-radius: 16px; }')
            box = QVBoxLayout(card); box.setContentsMargins(20, 18, 20, 18); box.setSpacing(10)
            top = QHBoxLayout(); mark = QLabel(); mark.setPixmap(QIcon.fromTheme('lumen' if app == 'lumen' else 'lumen-' + app, QIcon.fromTheme(icon)).pixmap(28, 28)); top.addWidget(mark)
            name = QLabel(title); name.setWordWrap(True); font = name.font(); font.setBold(True); name.setFont(font); top.addWidget(name, 1); box.addLayout(top)
            detail = QLabel(description); detail.setWordWrap(True); detail.setObjectName('muted'); box.addWidget(detail); box.addStretch()
            row = QHBoxLayout()
            for text, callback in ((tr('Öffnen'), lambda _=False, key=app: self.open(key)),
                                   (tr('Einstellungen'), lambda _=False, key=app: self.settings(key))):
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
