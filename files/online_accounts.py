"""Cloud accounts reuse rclone login and session-owned mounts; no cloud sync service."""
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from PySide6.QtCore import QProcess, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout, QWidget)
from google_drive import DriveDialog, DrivePaths, GoogleDrive
from lumen_i18n import tr

PROVIDERS = {'drive': 'Google Drive', 'onedrive': 'OneDrive', 'dropbox': 'Dropbox', 'webdav': 'WebDAV'}


def account_root():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')/'lumen/online-accounts'


def mount_root():
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')/'lumen/Online Accounts'


def read_config(path):
    parser = configparser.ConfigParser(interpolation=None)
    with path.open() as source:
        data = source.read(131073)
    if len(data) > 131072: raise ValueError('Account configuration too large')
    parser.read_string(data)
    return dict(parser['drive'])


def webdav_url(value):
    url = QUrl(value.strip())
    if (any(ord(c) < 32 for c in value) or not url.isValid() or url.scheme() != 'https' or not url.host() or
            url.userInfo() or url.hasQuery() or url.hasFragment() or url.port() == 0):
        raise ValueError(tr('Bitte eine HTTPS-Ordneradresse ohne Zugangsdaten, ? oder # eingeben.'))
    return url.toString(QUrl.FullyEncoded)


class AccountPaths(DrivePaths):
    def __init__(self, identity, provider, label=None):
        if not re.fullmatch('[a-f0-9]{32}', identity) or provider not in PROVIDERS:
            raise ValueError('Invalid account')
        self.identity = identity; self.provider = provider; self.label = label or PROVIDERS[provider]
        self.root = account_root()/identity; self.config = self.root/'rclone.conf'
        self.mount = mount_root()/identity
        self.cache = Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')/'lumen/online-accounts'/identity
        self.unit = 'lumen-online-account-' + hashlib.sha256(os.fsencode(self.config)).hexdigest()[:12]

    def configured(self, path=None):
        try:
            data = read_config(path or self.config)
            if data.get('type') != self.provider: return False
            if self.provider == 'webdav':
                return bool(webdav_url(data.get('url', '')))
            token = json.loads(data.get('token', '{}'))
            if not isinstance(token, dict) or not token.get('refresh_token'): return False
            return self.provider != 'onedrive' or bool(data.get('drive_id') and data.get('drive_type'))
        except (OSError, ValueError, KeyError, configparser.Error): return False


def accounts():
    result = []
    legacy = DrivePaths()
    if legacy.config.exists(): result.append(legacy)
    root = account_root()
    try: folders = sorted(root.iterdir())
    except OSError: return result
    for folder in folders:
        if not re.fullmatch('[a-f0-9]{32}', folder.name) or folder.is_symlink(): continue
        try:
            data = read_config(folder/'rclone.conf')
            result.append(AccountPaths(folder.name, data['type'], data.get('description', '')[:80]))
        except (OSError, ValueError, KeyError, configparser.Error): continue
    return result


class AccountDialog(DriveDialog):
    """Use the existing bounded/cancellable process lifecycle for the other providers."""
    def __init__(self, parent, paths):
        QDialog.__init__(self, parent)
        from settings_dialog import button, text
        self.paths = paths; self.job = None; self.staging = None; self.output = b''; self.login_url = ''
        self.stage = ''; self.options = {}; self.drive_state = ''
        self.failure_message = tr('Verbindung nicht abgeschlossen. Bitte Anmeldung, Adresse und Berechtigungen prüfen.')
        self.setWindowTitle(tr('Lumen · {0} verbinden', PROVIDERS[paths.provider])); self.setMinimumWidth(560)
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 24, 24, 24); layout.setSpacing(14)
        layout.addWidget(text(paths.label))
        layout.addWidget(text(tr('Änderungen an Dateien werden direkt zum Anbieter übertragen.')))
        self.status = text(''); layout.addWidget(self.status)
        self.install_button = button(tr('Cloud-Datei-Unterstützung installieren'), self.install_support)
        layout.addWidget(self.install_button); self.inputs = [self.install_button]
        self.secret = QLineEdit(); self.secret.setEchoMode(QLineEdit.Password)
        if paths.provider == 'webdav':
            layout.addWidget(text(tr('Verwende die WebDAV-Ordneradresse und nach Möglichkeit ein App-Passwort deines Anbieters. Zugangsdaten werden lokal geschützt gespeichert.')))
            form = QFormLayout(); layout.addLayout(form)
            self.url = QLineEdit(); self.url.setPlaceholderText('https://cloud.example/remote.php/dav/files/name/')
            self.user = QLineEdit(); self.vendor = QComboBox()
            for title, value in [('WebDAV', 'other'), ('Nextcloud', 'nextcloud'), ('ownCloud', 'owncloud')]: self.vendor.addItem(title, value)
            form.addRow(tr('Serveradresse'), self.url); form.addRow(tr('Benutzername'), self.user)
            form.addRow(tr('Passwort / App-Passwort'), self.secret); form.addRow(tr('Servertyp'), self.vendor)
            self.inputs += [self.url, self.user, self.secret, self.vendor]
        else:
            layout.addWidget(text(tr('Die Anmeldung öffnet deinen Browser. Dort erlaubst du der Anwendung „rclone“ den Zugriff auf dein eigenes Konto.')))
        self.drive_choice = QComboBox(); self.drive_choice.setAccessibleName(tr('OneDrive-Laufwerk'))
        layout.addWidget(self.drive_choice); self.drive_choice.hide()
        self.browser = button(tr('Anmeldung im Browser öffnen'), lambda: QDesktopServices.openUrl(QUrl(self.login_url)))
        layout.addWidget(self.browser); self.browser.hide()
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(tr('Verbinden'))
        self.buttons.accepted.connect(self.connect_account); self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.timeout = QTimer(self); self.timeout.setSingleShot(True); self.timeout.setInterval(300000)
        self.timeout.timeout.connect(self.timed_out); self.refresh_support()

    def refresh_support(self):
        missing = not all(shutil.which(name) for name in ('rclone', 'fusermount3', 'systemd-run'))
        self.install_button.setVisible(missing)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not missing and not self.job)
        if missing: self.status.setText(tr('Bitte zuerst die Cloud-Datei-Unterstützung installieren.'))

    def write_options(self):
        config = configparser.ConfigParser(interpolation=None); config['drive'] = self.options
        path = Path(self.staging.name)/'rclone.conf'
        with path.open('w') as output: config.write(output)
        path.chmod(0o600)
        return path

    def connect_account(self):
        if self.job: return
        if self.paths.configured(): self.accept(); return
        if self.drive_state:
            choice = self.drive_choice.currentData()
            if not choice: return
            self.drive_choice.setEnabled(False)
            self.start_login(self.oauth_arguments() + ['--continue', '--state', self.drive_state, '--result', choice])
            self.drive_state = ''; return
        self.options = {'type': self.paths.provider, 'description': self.paths.label}
        if self.paths.provider == 'webdav':
            try: self.options['url'] = webdav_url(self.url.text())
            except ValueError as error: self.status.setText(str(error)); return
            self.options.update(user=self.user.text(), vendor=self.vendor.currentData())
            if any(ord(c) < 32 for c in self.user.text()+self.secret.text()):
                self.status.setText(tr('Benutzername und Passwort dürfen keine Steuerzeichen enthalten.')); return
        if self.paths.provider == 'onedrive': self.options['disable_site_permission'] = 'true'
        try:
            account_root().mkdir(mode=0o700, parents=True, exist_ok=True); account_root().chmod(0o700)
            self.paths.root.mkdir(mode=0o700, parents=True, exist_ok=True); self.paths.root.chmod(0o700)
            self.clean_staging(); self.staging = tempfile.TemporaryDirectory(prefix='login-', dir=self.paths.root)
            self.write_options()
        except OSError:
            self.status.setText(tr('Die Zugangsdaten konnten nicht sicher gespeichert werden.')); self.clean_staging(); return
        if self.paths.provider == 'webdav':
            self.stage = 'obscure'; self.start_login(['obscure', '-'], stdin=self.secret.text().encode())
            self.status.setText(tr('WebDAV-Verbindung wird geprüft …'))
        else:
            self.stage = 'oauth'; self.start_login(self.oauth_arguments())

    def oauth_arguments(self):
        return ['config', 'update', 'drive', 'config_is_local', 'true', 'config_type', 'onedrive',
                'config_drive_ok', 'true', '--non-interactive', '--config', str(Path(self.staging.name)/'rclone.conf')]

    def login_finished(self, code, *_):
        if not self.job: return
        self.read_login()
        if code == 0 and self.stage == 'obscure':
            value = self.output.decode(errors='replace').strip()
            if not re.fullmatch('[A-Za-z0-9_-]+', value): code = 1
            else:
                proc, self.job = self.job, None; proc.deleteLater(); self.timeout.stop()
                self.options['pass'] = value
                try: path = self.write_options()
                except OSError:
                    self.stop_login(); self.refresh_support(); self.status.setText(self.failure_message); return
                self.stage = 'probe'
                self.start_login(['lsf', 'drive:', '--dirs-only', '--max-depth', '1', '--retries', '1',
                    '--contimeout', '10s', '--timeout', '20s', '--config', str(path)])
                self.timeout.setInterval(30000); self.status.setText(tr('WebDAV-Verbindung wird geprüft …')); return
        if code == 0 and self.stage == 'oauth' and self.paths.provider == 'onedrive':
            # Only the documented drive-selection step is supported; never expose arbitrary prompts/tokens.
            try:
                raw = self.output.decode(); result = json.loads(raw[raw.index('{'):])
                if not isinstance(result, dict) or result.get('Error'): raise ValueError()
                if result.get('State'):
                    option = result.get('Option', {})
                    if not isinstance(option, dict) or result['State'] != 'driveid_final' or option.get('Name') != 'config_driveid': raise ValueError()
                    choices = option.get('Examples')
                    if not isinstance(choices, list) or not 1 <= len(choices) <= 100: raise ValueError()
                    self.drive_choice.clear()
                    for choice in choices:
                        value = choice['Value']; caption = choice['Help']
                        if not isinstance(value, str) or not value or len(value)>1024 or not isinstance(caption, str): raise ValueError()
                        self.drive_choice.addItem(caption[:250], value)
                    proc, self.job = self.job, None; proc.deleteLater(); self.timeout.stop()
                    self.output = b''; self.login_url = ''; self.browser.hide()
                    self.drive_state = 'driveid_final'; self.drive_choice.show(); self.drive_choice.setEnabled(True)
                    self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)
                    self.status.setText(tr('Wähle das OneDrive-Laufwerk für dieses Konto.')); return
            except (ValueError, KeyError, TypeError): code = 1
        super().login_finished(code)
        self.drive_state = ''; self.drive_choice.hide(); self.timeout.setInterval(300000)


class AccountsWidget(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from settings_dialog import button, text
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(14)
        layout.addWidget(text(tr('Verbinde deine Cloud-Dateien mit Lumen Files. Jedes Konto bleibt getrennt; du kannst mehrere Konten desselben Anbieters hinzufügen.')))
        self.list = QListWidget(); self.list.setAccessibleName(tr('Verbundene Online-Konten'))
        self.list.setMinimumHeight(180); layout.addWidget(self.list)
        actions = QHBoxLayout(); layout.addLayout(actions)
        self.open_button = button(tr('In Lumen Files öffnen'), self.open_selected); actions.addWidget(self.open_button)
        self.remove_button = button(tr('Konto entfernen …'), self.remove_selected); actions.addWidget(self.remove_button)
        actions.addStretch(); actions.addWidget(button(tr('Aktualisieren'), self.refresh))
        form = QFormLayout(); layout.addLayout(form)
        self.provider = QComboBox()
        for key, name in PROVIDERS.items(): self.provider.addItem(name, key)
        self.name = QLineEdit(); self.name.setMaxLength(80); self.name.setPlaceholderText(tr('Zum Beispiel: Arbeit oder Privat'))
        form.addRow(tr('Anbieter'), self.provider); form.addRow(tr('Kontoname (optional)'), self.name)
        layout.addWidget(button(tr('Konto hinzufügen …'), self.add_account))
        self.status = text(''); layout.addWidget(self.status)
        layout.addWidget(text(tr('Jedes Konto wird erst nach deiner eigenen Anmeldung verbunden. Das Hinzufügen aktiviert keine automatische KI-Analyse deiner Cloud-Dateien.')))
        self.list.currentItemChanged.connect(self.selection_changed)
        self.list.itemActivated.connect(lambda _: self.open_selected())
        self.refresh()

    def selected(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def refresh(self):
        selected = self.selected(); key = selected.config if selected else None
        self.list.clear()
        for paths in accounts():
            state = tr('Verbunden') if paths.mounted() else tr('Eingerichtet') if paths.configured() else tr('Anmeldung prüfen')
            item = QListWidgetItem(paths.label + '\n' + PROVIDERS[paths.provider] + ' · ' + state)
            item.setData(Qt.UserRole, paths); self.list.addItem(item)
            if paths.config == key: self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.list.count(): self.list.setCurrentRow(0)
        self.selection_changed()

    def selection_changed(self, *_):
        paths = self.selected()
        self.open_button.setEnabled(paths is not None and paths.configured())
        self.remove_button.setEnabled(paths is not None)
        self.status.setText('' if self.list.count() else tr('Noch keine Online-Konten verbunden.'))

    def add_account(self):
        label = self.name.text().strip()
        if any(ord(c) < 32 for c in label):
            self.status.setText(tr('Der Kontoname darf keine Steuerzeichen enthalten.')); return
        try:
            account_root().mkdir(mode=0o700, parents=True, exist_ok=True); account_root().chmod(0o700)
        except OSError:
            self.status.setText(tr('Die Zugangsdaten konnten nicht sicher gespeichert werden.')); return
        paths = AccountPaths(uuid.uuid4().hex, self.provider.currentData(), label)
        dialog = DriveDialog(self, paths) if paths.provider == 'drive' else AccountDialog(self, paths)
        try:
            if dialog.exec() == QDialog.Accepted:
                self.name.clear(); self.refresh(); self.changed.emit()
        finally: dialog.deleteLater()

    def open_selected(self):
        paths = self.selected()
        if not paths: return
        try:
            from lumen_launch import executable
            started, _ = QProcess.startDetached(executable('lumen-files'), [str(paths.mount)])
            if not started: raise OSError()
        except (OSError, ValueError): self.status.setText(tr('Lumen Files konnte nicht geöffnet werden.'))

    def remove_selected(self):
        paths = self.selected()
        if not paths: return
        if paths.mounted():
            self.status.setText(tr('Dieses Konto ist in der Sitzung eingebunden. Bitte Übertragungen abschließen und vom Desktop abmelden. Nach der nächsten Anmeldung kannst du es hier entfernen.')); return
        if QMessageBox.question(self, tr('Konto entfernen'), tr('„{0}“ aus Lumen entfernen? Cloud-Dateien bleiben erhalten. Die Zugriffsfreigabe kannst du zusätzlich beim Anbieter widerrufen.', paths.label),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes: return
        try:
            # A second Files window may have mounted the account while confirmation was open.
            if paths.mounted():
                self.status.setText(tr('Das Konto wurde inzwischen verbunden. Bitte zuerst vom Desktop abmelden.')); return
            paths.config.unlink(missing_ok=True)
        except OSError:
            self.status.setText(tr('Das Konto konnte nicht entfernt werden.')); return
        self.refresh(); self.changed.emit()


def open_accounts(parent=None):
    dialog = QDialog(parent); dialog.setWindowTitle(tr('Lumen · Online-Konten')); dialog.resize(640, 580)
    layout = QVBoxLayout(dialog); layout.setContentsMargins(24, 24, 24, 24)
    widget = AccountsWidget(dialog); layout.addWidget(widget)
    buttons = QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
    try: return dialog.exec()
    finally: dialog.deleteLater()


class CloudAccounts:
    def __init__(self, window, legacy):
        self.window = window; self.legacy = legacy; self.drives = {str(legacy.paths.config): legacy}

    def refresh(self):
        for paths in accounts():
            key = str(paths.config)
            if key not in self.drives: self.drives[key] = GoogleDrive(self.window, paths)
        for key, drive in list(self.drives.items()):
            if drive is not self.legacy and not drive.paths.config.exists() and not drive.paths.mounted():
                drive.close(); drive.deleteLater(); del self.drives[key]

    def for_path(self, path):
        return next((drive for drive in self.drives.values() if drive.paths.contains(path)), None)

    def contains(self, path):
        return self.legacy.paths.contains(path) or Path(os.path.abspath(os.path.expanduser(str(path)))).is_relative_to(mount_root())

    def mounted(self, path):
        drive = self.for_path(path)
        return bool(drive and drive.paths.mounted())

    def label(self, path):
        drive = self.for_path(path)
        return drive.paths.label if drive else tr('Online-Konto')

    def open(self, path, record, history_position):
        self.refresh(); drive = self.for_path(path)
        if drive: drive.open(path, record, history_position)
        else: self.window.error(tr('Bitte das Konto unter Online-Konten erneut verbinden.'))

    def cancel_pending(self):
        for drive in self.drives.values(): drive.pending = None

    def close(self):
        for drive in self.drives.values(): drive.close()
