"""Network folders through the existing KDE KIO-FUSE service."""
import os
import re
import sys
from pathlib import Path

from PyQt5.QtCore import QObject, QProcess, Qt, QUrl, pyqtSignal
from PyQt5.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingCallWatcher, QDBusPendingReply
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QFormLayout, QLabel, QLineEdit, QVBoxLayout)

SCHEMES = {'smb', 'sftp', 'webdav', 'webdavs', 'ftp', 'nfs'}
ALIASES = {'http': 'webdav', 'https': 'webdavs', 'dav': 'webdav', 'davs': 'webdavs'}


def is_network_address(value):
    value = str(value).strip()
    return value.startswith('\\\\') or bool(re.match(r'^[a-zA-Z][\w+.-]*://', value)) and not value.startswith('file:')


def normalize_url(value):
    """Validate before connecting or persisting. Passwords belong to KDE's auth UI."""
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Die Adresse enthält ungültige Steuerzeichen.')
    value = value.strip()
    if value.startswith('\\\\'):
        value = 'smb://' + value[2:].replace('\\', '/')
    url = QUrl(value, QUrl.StrictMode)
    url.setScheme(ALIASES.get(url.scheme(), url.scheme()))
    if not url.isValid() or url.scheme() not in SCHEMES or not url.host() or url.port() == 0:
        raise ValueError('Bitte eine gültige SMB-, SFTP-, WebDAV-, FTP- oder NFS-Adresse mit Server eingeben.')
    if url.password() or ':' in url.userInfo():
        raise ValueError('Bitte das Passwort aus der Adresse entfernen. KDE fragt es bei der Anmeldung ab.')
    if url.hasQuery() or url.hasFragment():
        raise ValueError('Bitte eine Ordneradresse ohne ? oder # verwenden; im Dateinamen diese Zeichen URL-kodieren.')
    if not url.path():
        url.setPath('/')
    return url.toString(QUrl.FullyEncoded)


def remote_path(path, mounts):
    """Translate descendants without stat/resolve calls against an offline server."""
    path = Path(os.path.abspath(path))
    for local, remote in sorted(mounts.items(), key=lambda item: len(item[0]), reverse=True):
        try:
            relative = path.relative_to(local)
        except ValueError:
            continue
        url = QUrl(remote)
        if relative.parts:
            url.setPath(url.path().rstrip('/') + '/' + relative.as_posix(), QUrl.DecodedMode)
        return url.toString(QUrl.FullyEncoded)
    return None


def display_url(value):
    return QUrl(value).toDisplayString(QUrl.RemovePassword)


def server_label(value):
    url = QUrl(value)
    name = url.path().rstrip('/').rsplit('/', 1)[-1]
    return f'{name} · {url.host()}' if name else url.host()


class Network(QObject):
    connected = pyqtSignal(str, str)
    failed = pyqtSignal(str)
    busy = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mounts = {}
        self.pending = None
        self.watchers = set()
        self.closed = False

    def mount(self, address):
        if self.closed: return
        address = normalize_url(address)
        self.cancel()
        message = QDBusMessage.createMethodCall('org.kde.KIOFuse', '/org/kde/KIOFuse',
                                               'org.kde.KIOFuse.VFS', 'mountUrl')
        message.setArguments([address])
        watcher = QDBusPendingCallWatcher(QDBusConnection.sessionBus().asyncCall(message, 120000), self)
        self.watchers.add(watcher)
        self.pending = watcher
        self.busy.emit(True)

        def finished():
            self.watchers.discard(watcher)
            if self.pending is not watcher:
                watcher.deleteLater()
                return
            self.pending = None
            self.busy.emit(False)
            reply = QDBusPendingReply(watcher)
            if reply.isError():
                self.failed.emit('Verbindung fehlgeschlagen. Serveradresse, Netzwerk und Anmeldung prüfen.\n'
                                 + reply.error().message())
            else:
                values = reply.reply().arguments()
                path = values[0] if values else ''
                if not isinstance(path, str) or not os.path.isabs(path) or '\x00' in path:
                    self.failed.emit('KDE hat keinen gültigen Ordnerpfad zurückgegeben.')
                else:
                    path = os.path.normpath(path)
                    self.mounts[path] = address
                    self.connected.emit(address, path)
            watcher.deleteLater()
        watcher.finished.connect(finished)

    def cancel(self):
        # KIO-FUSE has no per-request cancel method; ignore late replies, never unmount shared KIO sessions.
        self.pending = None
        self.busy.emit(False)

    def release(self):
        """Detach this client. KIO-FUSE has no per-URL unmount API."""
        self.cancel()
        paths = list(self.mounts)
        self.mounts.clear()
        if paths:
            QProcess.startDetached(sys.executable, [str(Path(__file__).with_name('network_cleanup.py')), *paths])

    def close(self):
        self.closed = True
        self.release()
        for watcher in list(self.watchers):
            watcher.finished.disconnect()
            watcher.deleteLater()
        self.watchers.clear()

    def remote(self, path):
        return remote_path(path, self.mounts)


class ConnectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Mit Server verbinden')
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        title = QLabel('Deine Dateien im Netzwerk')
        title.setObjectName('previewTitle')
        layout.addWidget(title)
        form = QFormLayout()
        self.protocol = QComboBox()
        for name, scheme in [('SMB · NAS / Windows', 'smb'), ('SFTP · SSH', 'sftp'),
                             ('WebDAV · HTTPS', 'webdavs'), ('WebDAV · HTTP', 'webdav'),
                             ('NFS', 'nfs'), ('FTP', 'ftp')]:
            self.protocol.addItem(name, scheme)
        form.addRow('Verbindung', self.protocol)
        self.address = QLineEdit()
        self.address.setAccessibleName('Serveradresse')
        self.address.setPlaceholderText('nas.local/Freigabe oder smb://nas.local/Freigabe')
        form.addRow('Adresse', self.address)
        layout.addLayout(form)
        hint = QLabel('Auch vollständige Adressen wie sftp://name@server/ordner sind möglich.\n'
                      'Benutzername und Passwort fragt KDE bei Bedarf ab.')
        hint.setWordWrap(True)
        hint.setObjectName('muted')
        layout.addWidget(hint)
        self.remember = QCheckBox('Server in der Seitenleiste merken')
        self.remember.setChecked(True)
        layout.addWidget(self.remember)
        self.error = QLabel()
        self.error.setTextFormat(Qt.PlainText)
        self.error.setWordWrap(True)
        self.error.setStyleSheet('color: #f1b3ad;')
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('Verbinden')
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.protocol.currentIndexChanged.connect(self.update_placeholder)
        self.address.setFocus()
        self.url = None

    def update_placeholder(self):
        examples = {'smb': 'nas.local/Freigabe', 'sftp': 'name@server/ordner',
                    'webdavs': 'cloud.example/remote.php/dav/files/name/',
                    'webdav': 'server/ordner', 'nfs': 'server/export', 'ftp': 'server/ordner'}
        self.address.setPlaceholderText(examples[self.protocol.currentData()])

    def validate(self):
        value = self.address.text()
        if not is_network_address(value):
            value = self.protocol.currentData() + '://' + value
        try:
            self.url = normalize_url(value)
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.accept()
