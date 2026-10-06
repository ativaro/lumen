"""Google Drive login and a shared, session-owned rclone mount."""
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from PySide6.QtCore import QObject, QProcess, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLineEdit, QVBoxLayout, QWidget
from lumen_i18n import tr, worker_process

APP_CLIENT_FILE = Path(__file__).with_name('google-drive-client.json')


class DrivePaths:
    def __init__(self):
        self.provider = 'drive'; self.label = 'Google Drive'
        self.root = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')/'lumen/google-drive'
        self.config = self.root/'rclone.conf'
        self.mount = Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')/'lumen/Google Drive'
        self.cache = Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')/'lumen/google-drive'
        self.unit = 'lumen-google-drive-' + hashlib.sha256(os.fsencode(self.config)).hexdigest()[:12]

    def contains(self, path):
        return Path(os.path.abspath(os.path.expanduser(str(path)))).is_relative_to(self.mount)

    def mounted(self):
        # Read the local mount table; stat() can hang on an unavailable FUSE server.
        target = str(self.mount).replace('\\', r'\134').replace(' ', r'\040')
        try:
            return any(line.split()[4] == target and
                       line.split(' - ', 1)[1].split()[:2] == ['fuse.rclone', self.unit]
                       for line in Path('/proc/self/mountinfo').read_text().splitlines())
        except OSError:
            return False

    def configured(self, path=None):
        try:
            config = configparser.ConfigParser(interpolation=None)
            config.read(path or self.config)
            token = json.loads(config.get('drive', 'token', fallback='{}'))
            return isinstance(token, dict) and bool(token.get('refresh_token')) and config.get('drive', 'type') == 'drive'
        except (OSError, ValueError, configparser.Error):
            return False

    def command(self):
        for path in (self.root, self.mount.parent, self.cache):
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700); self.cache.chmod(0o700); self.config.chmod(0o600)
        self.mount.mkdir(mode=0o700, exist_ok=True)
        return ['--user', '--collect', '--quiet', '--unit='+self.unit, '--service-type=notify',
                '--property=TimeoutStartSec=60', '--property=TimeoutStopSec=120', '--property=UMask=0077',
                '--expand-environment=no', shutil.which('rclone') or 'rclone', 'mount', 'drive:', str(self.mount),
                '--config', str(self.config), '--cache-dir', str(self.cache), '--devname', self.unit,
                '--vfs-cache-mode=writes', '--vfs-write-back=0s', '--dir-cache-time=30s', '--poll-interval=15s',
                '--log-level=ERROR', '--contimeout=15s', '--timeout=30s']


def oauth_client(path):
    with open(path, 'rb') as source:
        raw = source.read(65537)
    if len(raw) > 65536: raise ValueError(tr('Die OAuth-Datei ist zu groß.'))
    try:
        client = json.loads(raw)['installed']
        identity, secret = client['client_id'], client['client_secret']
        if (not isinstance(identity, str) or not isinstance(secret, str) or not secret
                or not re.fullmatch(r'[\w.-]+\.apps\.googleusercontent\.com', identity)
                or any(ord(c) < 32 for c in secret)):
            raise ValueError()
        return identity, secret
    except (ValueError, KeyError, TypeError):
        raise ValueError(tr('Bitte die Google-OAuth-JSON-Datei für eine Desktop-App auswählen.')) from None


def bundle_oauth_client(source, destination):
    """Ship only the Desktop app identity, never account tokens or custom endpoints."""
    identity, secret = oauth_client(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        output = Path(staging)/'client.json'
        output.write_text(json.dumps({'installed': {'client_id': identity, 'client_secret': secret}})+'\n')
        output.chmod(0o644)  # A distributed Desktop client is public, unlike users' refresh tokens.
        os.replace(output, destination)


class DriveDialog(QDialog):
    def __init__(self, parent=None, paths=None):
        super().__init__(parent)
        from settings_dialog import button, text
        self.paths = paths or DrivePaths()
        self.job = None; self.staging = None; self.output = b''; self.login_url = ''
        self.setWindowTitle(tr('Lumen · Google Drive'))
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 24, 24, 24); layout.setSpacing(14)
        layout.addWidget(text(tr('Google Drive in Lumen Files')))
        layout.addWidget(text(tr('Dateien öffnen, kopieren und umbenennen. Änderungen werden zu Google übertragen; laufende Übertragungen gehen nach dem Schließen von Lumen weiter.')))
        self.status = text(''); layout.addWidget(self.status)
        self.inputs = []
        if self.paths.configured():
            self.status.setText(tr('Dein Google-Konto ist verbunden. Google Drive ist in der Seitenleiste von Lumen Files verfügbar.'))
            buttons = QDialogButtonBox(QDialogButtonBox.Close)
            buttons.rejected.connect(self.reject); layout.addWidget(buttons)
            return
        layout.addWidget(text(tr('Melde dich im Browser bei Google an und erlaube Lumen den Zugriff auf deine Drive-Dateien. Dein Passwort bleibt bei Google.')))
        self.app_client = None
        try: self.app_client = oauth_client(APP_CLIENT_FILE)
        except FileNotFoundError:
            app_status = tr('Die Google-Anmeldung ist in dieser Lumen-Ausgabe noch nicht eingerichtet.')
        except (OSError, ValueError):
            app_status = tr('Die Google-Anmeldung dieser Lumen-Ausgabe ist fehlerhaft eingerichtet. Bitte Lumen aktualisieren.')
        else:
            app_status = tr('Mit Google verbinden öffnet die Anmeldung im Browser.')
        layout.addWidget(text(app_status))
        self.install_button = button(tr('Google-Drive-Unterstützung installieren'), self.install_support)
        layout.addWidget(self.install_button)
        self.custom_client = QCheckBox(tr('Eigene Google-App verwenden (erweitert)'))
        layout.addWidget(self.custom_client)
        self.credentials = QWidget(); advanced = QVBoxLayout(self.credentials); advanced.setContentsMargins(0, 0, 0, 0)
        advanced.addWidget(button(tr('Anleitung für Google-Zugangsdaten öffnen'), lambda: QDesktopServices.openUrl(
            QUrl('https://rclone.org/drive/#making-your-own-client-id'))))
        self.import_button = button(tr('Google-OAuth-JSON importieren …'), self.import_client)
        advanced.addWidget(self.import_button)
        form = QFormLayout(); advanced.addLayout(form)
        self.client = QLineEdit(); self.secret = QLineEdit(); self.secret.setEchoMode(QLineEdit.Password)
        form.addRow(tr('Client-ID'), self.client); form.addRow(tr('Client-Secret'), self.secret)
        layout.addWidget(self.credentials); self.credentials.hide()
        self.inputs = [self.credentials, self.custom_client, self.install_button]
        self.browser = button(tr('Anmeldung im Browser öffnen'), lambda: QDesktopServices.openUrl(QUrl(self.login_url)))
        self.browser.hide(); layout.addWidget(self.browser)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(tr('Mit Google verbinden'))
        self.buttons.accepted.connect(self.connect_account); self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.timeout = QTimer(self); self.timeout.setSingleShot(True); self.timeout.setInterval(300000)
        self.timeout.timeout.connect(self.timed_out)
        self.custom_client.toggled.connect(self.credentials.setVisible)
        self.custom_client.toggled.connect(self.refresh_support)
        self.refresh_support()

    def refresh_support(self):
        missing = not all(shutil.which(name) for name in ('rclone', 'fusermount3', 'systemd-run'))
        self.install_button.setVisible(missing)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
            not missing and not self.job and (bool(self.app_client) or self.custom_client.isChecked()))
        if missing: self.status.setText(tr('Bitte zuerst die Google-Drive-Unterstützung installieren.'))

    def install_support(self):
        from setup_dialog import SetupDialog
        dialog = SetupDialog(self)
        QTimer.singleShot(0, dialog, lambda: dialog.start_job('packages', ['google_drive']))
        dialog.exec(); dialog.deleteLater(); self.refresh_support()
        if self.buttons.button(QDialogButtonBox.Ok).isEnabled():
            self.status.setText(tr('Bereit für die Anmeldung.'))

    def import_client(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Google-OAuth-JSON importieren …'), '', 'JSON (*.json)')
        if not path: return
        try:
            identity, secret = oauth_client(path)
            self.client.setText(identity); self.secret.setText(secret)
            self.status.setText(tr('Zugangsdaten importiert. Jetzt das Google-Konto verbinden.'))
        except (OSError, ValueError) as error: self.status.setText(str(error))

    def connect_account(self):
        if self.job: return
        # Never silently fall back to rclone's retiring shared client or another app's identity.
        if self.custom_client.isChecked():
            identity, secret = self.client.text().strip(), self.secret.text().strip()
        elif self.app_client:
            identity, secret = self.app_client
        else:
            self.status.setText(tr('Die Google-Anmeldung ist in dieser Lumen-Ausgabe noch nicht eingerichtet.')); return
        if not re.fullmatch(r'[\w.-]+\.apps\.googleusercontent\.com', identity) or not secret or any(ord(c)<32 for c in secret):
            self.status.setText(tr('Bitte gültige Client-ID und Client-Secret eingeben oder importieren.')); return
        # Never overwrite a connection made concurrently by another Lumen window.
        if self.paths.configured(): self.accept(); return
        try:
            self.paths.root.mkdir(mode=0o700, parents=True, exist_ok=True); self.paths.root.chmod(0o700)
            self.staging = tempfile.TemporaryDirectory(prefix='login-', dir=self.paths.root)
            config = configparser.ConfigParser(interpolation=None)
            config['drive'] = dict(type='drive', client_id=identity, client_secret=secret, scope='drive', description=self.paths.label)
            path = Path(self.staging.name)/'rclone.conf'
            with path.open('w') as output: config.write(output)
            path.chmod(0o600)
        except OSError:
            self.status.setText(tr('Die Zugangsdaten konnten nicht sicher gespeichert werden.')); self.clean_staging(); return
        self.start_login(['config', 'update', 'drive', 'config_is_local', 'true',
            'config_change_team_drive', 'false', '--non-interactive', '--config', str(path)])

    def start_login(self, arguments, stdin=None):
        self.output = b''; self.login_url = ''; self.browser.hide()
        self.job = worker_process(self); proc = self.job
        env = proc.processEnvironment()
        for key in env.keys():
            if key.startswith('RCLONE_'): env.remove(key)
        proc.setProcessEnvironment(env)
        if stdin is not None:
            def write_input():
                proc.write(stdin); proc.closeWriteChannel()
            proc.started.connect(write_input)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self.read_login)
        proc.finished.connect(self.login_finished)
        proc.errorOccurred.connect(lambda error: self.login_finished(1) if error == QProcess.FailedToStart else None)
        for widget in self.inputs: widget.setEnabled(False)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.status.setText(tr('Bitte die Anmeldung im Browser abschließen …'))
        self.timeout.start()
        proc.start(shutil.which('rclone') or 'rclone', arguments)

    def read_login(self):
        if not self.job: return
        self.output = (self.output + bytes(self.job.readAllStandardOutput()))[-65536:]
        # Only this fixed loopback OAuth endpoint may become a clickable link.
        match = re.search(rb'http://127\.0\.0\.1:53682/auth\?state=[A-Za-z0-9_-]+', self.output)
        if match:
            self.login_url = match[0].decode(); self.browser.show()

    def login_finished(self, code, *_):
        if not self.job: return
        self.read_login(); proc, self.job = self.job, None; proc.deleteLater(); self.timeout.stop()
        success = False
        try:
            staged = Path(self.staging.name)/'rclone.conf'
            if code == 0 and self.paths.configured(staged):
                # link() is an atomic no-clobber publish; concurrent logins keep the first account.
                staged.chmod(0o600)
                try: os.link(staged, self.paths.config)
                except FileExistsError:
                    if not self.paths.configured(): raise OSError()
                success = True
        except (OSError, ValueError, configparser.Error): pass
        self.clean_staging(); self.output = b''; self.login_url = ''; self.browser.hide()
        for widget in self.inputs: widget.setEnabled(True)
        self.refresh_support()
        if success: self.secret.clear(); self.accept()
        else: self.status.setText(getattr(self, 'failure_message', tr('Google-Anmeldung nicht abgeschlossen. Bitte erneut versuchen und den Zugriff bei Google bestätigen. Falls Google die App blockiert, muss ihre Freigabe vom Anbieter geklärt werden.')))

    def clean_staging(self):
        if self.staging: self.staging.cleanup(); self.staging = None

    def stop_login(self):
        if self.job:
            proc, self.job = self.job, None
            proc.kill(); proc.waitForFinished(1000); proc.deleteLater()
        if hasattr(self, 'timeout'): self.timeout.stop()
        self.clean_staging(); self.output = b''; self.login_url = ''

    def timed_out(self):
        self.stop_login(); self.browser.hide()
        for widget in self.inputs: widget.setEnabled(True)
        self.refresh_support(); self.status.setText(tr('Die Anmeldung ist abgelaufen. Bitte erneut verbinden.'))

    def done(self, result):
        self.stop_login()
        super().done(result)


class GoogleDrive(QObject):
    def __init__(self, window, paths=None):
        super().__init__(window)
        self.window = window; self.paths = paths or DrivePaths(); self.pending = None; self.job = None
        self.timeout = QTimer(self); self.timeout.setSingleShot(True); self.timeout.setInterval(65000)
        self.timeout.timeout.connect(lambda: self.finished(1))

    def open(self, path, record, history_position):
        if not self.paths.configured():
            if self.paths.provider != 'drive':
                self.window.error(tr('Bitte das Konto unter Online-Konten erneut verbinden.')); return
            dialog = DriveDialog(self.window, self.paths)
            result = dialog.exec(); dialog.deleteLater()
            if result != QDialog.Accepted: return
        self.pending = (self.window.tabs_data[self.window.tabs.currentIndex()], str(path), record, history_position)
        if self.paths.mounted(): self.finished(0); return
        if self.job: return
        try: command = self.paths.command()
        except OSError:
            self.finished(1); return
        self.window.activity.setText(tr('{0} wird verbunden …', self.paths.label))
        self.job = worker_process(self); proc = self.job
        env = proc.processEnvironment()
        for key in env.keys():
            if key.startswith('RCLONE_'): env.remove(key)
        proc.setProcessEnvironment(env)
        proc.setStandardOutputFile(QProcess.nullDevice()); proc.setStandardErrorFile(QProcess.nullDevice())
        proc.finished.connect(self.finished)
        proc.errorOccurred.connect(lambda error: self.finished(1) if error == QProcess.FailedToStart else None)
        self.timeout.start(); proc.start('systemd-run', command)

    def finished(self, _code, *_):
        self.timeout.stop()
        if self.job:
            proc, self.job = self.job, None
            # This is only the launcher. The user service owns the mount and uploads.
            proc.finished.disconnect()
            proc.errorOccurred.disconnect()
            proc.kill(); proc.waitForFinished(1000); proc.deleteLater()
        request, self.pending = self.pending, None
        window = self.window
        if not request or not window.tabs_data or request[0] is not window.tabs_data[window.tabs.currentIndex()]: return
        if self.paths.mounted():
            window.show_folder(request[1], request[2], history_position=request[3])
            window.activity.setText(tr('{0} · Änderungen werden im Hintergrund übertragen', self.paths.label))
        else:
            window.activity.setText(tr('{0} konnte nicht verbunden werden.', self.paths.label))
            window.error(tr('{0} konnte nicht verbunden werden.', self.paths.label),
                         tr('Bitte Internetverbindung, rclone und die Konto-Anmeldung prüfen. Dienstprotokoll: {0}',
                            'journalctl --user -u '+self.paths.unit))

    def close(self):
        self.pending = None; self.finished(0)


def open_drive_settings(parent=None):
    dialog = DriveDialog(parent)
    try: return dialog.exec()
    finally: dialog.deleteLater()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Bundle the Lumen Google Desktop client without account data.')
    parser.add_argument('--bundle-client', nargs=2, metavar=('SOURCE', 'DESTINATION'), required=True)
    args = parser.parse_args()
    try: bundle_oauth_client(*args.bundle_client)
    except (OSError, ValueError): parser.exit(1, 'Invalid or unreadable Google Desktop client; bundle unchanged.\n')
