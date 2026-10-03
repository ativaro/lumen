"""Explicit Lumen playback routing and private, crash-safe radio interruption.

Each foreground playback holds a local socket open while it needs the radio
paused. Disconnecting (including process exit) releases that hold. No audio
daemon, microphone access, or system-wide device changes are involved.
"""
import hashlib
import json
import os
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from lumen_i18n import tr, worker_process
from tools_data import Library


NAMES = {'reader': 'Lumen Reader', 'radio': 'Lumen Persönliches Radio', 'meetings': 'Lumen Meeting-Werkstatt'}
DEFAULTS = dict(sink='', pause_radio=False, pause_disconnect=False, strict_routing=False)


def preferences(app, root=None):
    if app not in NAMES:
        return dict(DEFAULTS)
    import sound_data
    values = sound_data.settings(Library('sound', root)).get('lumen_playback', {}).get(app, {})
    return {key: values.get(key, default) for key, default in DEFAULTS.items()}


def _validated(app, values):
    if app not in NAMES or set(values) - set(DEFAULTS):
        raise ValueError(tr('Ungültige Audioauswahl.'))
    sink = values.get('sink', '')
    if not isinstance(sink, str) or len(sink) > 512 or '\0' in sink:
        raise ValueError(tr('Ungültige Audioauswahl.'))
    values = dict(sink=sink, pause_radio=bool(values.get('pause_radio')), pause_disconnect=bool(values.get('pause_disconnect')), strict_routing=bool(values.get('strict_routing')))
    if (values['pause_disconnect'] or values['strict_routing']) and not sink:
        raise ValueError(tr('Für die Trennungs-Pause zuerst einen festen Audioausgang auswählen.'))
    return values


def save_preferences(app, values, root=None):
    values = _validated(app, values)
    import sound_data
    library = Library('sound', root)
    with sound_data.locked(library):
        record = sound_data.settings(library)
        saved = dict(record.get('lumen_playback', {}))
        saved[app] = values
        library.update(record['id'], lumen_playback=saved)
    return values


def save_project_profile(library, key, title, players=None):
    """Associate current or explicit playback preferences with one project."""
    title = str(title).strip()
    if not title or len(title) > 200:
        raise ValueError(tr('Bitte einen Namen für das Audioprofil angeben.'))
    root = library.root.parent
    players = players if players is not None else {app: preferences(app, root) for app in NAMES}
    if not isinstance(players, dict) or set(players) - set(NAMES) or not players:
        raise ValueError(tr('Ungültige Audioauswahl.'))
    profile = dict(title=title, players={app: _validated(app, value) for app, value in players.items()})
    library.update(key, audio_profile=profile)
    return profile


def apply_project_profile(library, key):
    """Explicit application changes future playback preferences, never hardware."""
    profile = library.get(key).get('audio_profile')
    if not profile or not isinstance(profile.get('players'), dict):
        raise ValueError(tr('Dieses Projekt hat noch kein Audioprofil.'))
    players = {app: _validated(app, value) for app, value in profile['players'].items()}
    import sound_data
    sound_library = Library('sound', library.root.parent)
    with sound_data.locked(sound_library):
        record = sound_data.settings(sound_library)
        values = dict(record.get('lumen_playback', {}))
        values.update(players)
        sound_library.update(record['id'], lumen_playback=values)
    return profile


def install_audio_menu(window):
    """Called by shared menu installation after the Workbench UI exists."""
    if getattr(window, 'name', '') != 'workbench' or hasattr(window, '_audio_profile_menu'):
        return
    from PySide6.QtWidgets import QInputDialog,QMenu
    menu = QMenu(tr('Audioprofil'),window)
    window._audio_profile_menu = menu

    def save():
        if not window.current:
            raise ValueError(tr('Zuerst ein Projekt auswählen.'))
        window.save()
        title, accepted = QInputDialog.getText(window, tr('Lumen-Audioprofil'), tr('Name des Audioprofils'), text=window.library.get(window.current)['title'])
        if accepted:
            save_project_profile(window.library, window.current, title)
            window.status.setText(tr('Aktuelle Lumen-Audioauswahl beim Projekt gespeichert.'))

    def apply():
        if not window.current:
            raise ValueError(tr('Zuerst ein Projekt auswählen.'))
        profile = apply_project_profile(window.library, window.current)
        window.status.setText(tr('Audioprofil für die nächste Wiedergabe aktiviert: ') + profile['title'])

    menu.addAction(tr('Aktuelle Audioauswahl beim Projekt speichern'), lambda: window.safe(save))
    menu.addAction(tr('Gespeichertes Projektprofil aktivieren'), lambda: window.safe(apply))


def playback_environment(environment, app, prefs=None):
    """SDL2 and libpulse expose these documented hints/properties to the mixer."""
    if app not in NAMES:
        return environment
    prefs = prefs or DEFAULTS
    title = tr(NAMES[app])
    environment.insert('SDL_AUDIO_DEVICE_APP_NAME', title)
    environment.insert('SDL_AUDIO_DEVICE_STREAM_NAME', title)
    environment.insert('SDL_AUDIO_DEVICE_STREAM_ROLE', 'music' if app == 'radio' else 'production')
    environment.insert('PULSE_PROP_application.id', 'org.lumen.' + app)
    environment.insert('PULSE_PROP_application.name', title)
    environment.insert('PULSE_PROP_media.name', title)
    # Use the Pulse-compatible path consistently with Lumen Sound's controls.
    environment.insert('SDL_AUDIODRIVER', 'pulseaudio')
    if prefs.get('sink'):
        environment.insert('PULSE_SINK', prefs['sink'])
        if prefs.get('sink_description'):
            # SDL2-compat/SDL3 supplies an explicit default sink to libpulse and
            # therefore bypasses PULSE_SINK unless this SDL override is supplied.
            environment.insert('SDL_AUDIO_DEVICE_NAME', prefs['sink_description'])
    if prefs.get('strict_routing'):
        for key in ('node.dont-fallback', 'node.dont-reconnect', 'node.dont-move'):
            environment.insert('PULSE_PROP_' + key, 'true')
    return environment


def socket_name(root, app='radio'):
    digest = hashlib.sha256(str(Path(root).absolute()).encode()).hexdigest()[:24]
    return 'lumen-audio-' + app + '-' + str(os.getuid()) + '-' + digest


class Controller(QObject):
    def __init__(self, player, app, root):
        super().__init__(player)
        self.player, self.app, self.root = player, app, root
        self.prefs = dict(DEFAULTS)
        self.server = None
        self.holds = set()
        self.clients = set()
        self.auto_paused = False
        self.leases = {}
        self.awaiting = set()
        self.pending = None
        self.monitor = None
        self.preflight = None
        self.wait = QTimer(self)
        self.wait.setSingleShot(True)
        self.wait.timeout.connect(self._timeout)
        self.poll = QTimer(self)
        self.poll.setInterval(1000)
        self.poll.timeout.connect(self.check_output)
        if app in NAMES:
            self.server = QLocalServer(self)
            self.server.setSocketOptions(QLocalServer.UserAccessOption)
            name = socket_name(root, app)
            if not self.server.listen(name):
                probe = QLocalSocket(self)
                probe.connectToServer(name)
                if not probe.waitForConnected(50):
                    QLocalServer.removeServer(name)
                    self.server.listen(name)
                probe.abort()
                probe.deleteLater()
            self.server.newConnection.connect(self._accept)

    def start(self, callback):
        self.stop()
        self.prefs = preferences(self.app, self.root)
        self.pending = callback
        if self.prefs['sink']:
            from tools_ui import Job
            from interop_audio_route import snapshot
            job = Job(snapshot, self)
            self.preflight = job
            job.result.connect(lambda state: self._route_ready(job, state))
            job.failed.connect(lambda error: self._route_failed(job, error))
            job.finished.connect(job.deleteLater)
            job.start()
        else:
            self._coordinate()

    def _route_ready(self, job, state):
        if self.preflight is not job: return
        self.preflight = None
        from interop_audio_route import route
        try:
            self.prefs = route(state, self.prefs)
        except ValueError as error:
            self.pending = None
            self.player.time.setText(str(error))
            return
        self._coordinate()

    def _route_failed(self, job, error):
        if self.preflight is not job: return
        self.preflight = None
        self.pending = None
        self.player.time.setText(tr('Audioausgang konnte nicht geprüft werden. Wiedergabe bleibt gestoppt.') + ' ' + error)

    def _coordinate(self):
        if self.app in ('reader', 'meetings') and self.prefs['pause_radio']:
            targets = ['radio', 'reader'] if self.app == 'meetings' else ['radio']
            self.awaiting = set(targets)
            for app in targets:
                lease = QLocalSocket(self)
                self.leases[app] = lease
                lease.connected.connect(lambda l=lease: l.write(json.dumps(dict(app=self.app, version=1)).encode() + b'\n'))
                lease.readyRead.connect(lambda l=lease, a=app: self._held(a, l))
                lease.errorOccurred.connect(lambda _, l=lease, a=app: self._unavailable(a, l))
                lease.connectToServer(socket_name(self.root, app))
            self.wait.start(700)
        else:
            self._ready()

    def _ready(self):
        self.wait.stop()
        callback, self.pending = self.pending, None
        if callback:
            callback()
            if (self.prefs['pause_disconnect'] or self.prefs.get('strict_routing')) and self.prefs['sink']:
                self.poll.start()
                self.check_output()

    def _held(self, app, lease):
        if lease is self.leases.get(app) and lease.canReadLine() and bytes(lease.readLine()).strip() == b'held':
            self.awaiting.discard(app)
            if not self.awaiting:
                self._ready()

    def _unavailable(self, app, lease):
        if lease is self.leases.get(app) and self.pending:
            # A missing endpoint means that application has no controlled player.
            self.leases.pop(app)
            lease.abort()
            lease.deleteLater()
            self.awaiting.discard(app)
            if not self.awaiting:
                self._ready()

    def _timeout(self):
        if self.pending:
            self.pending = None
            self._drop_lease()
            self.player.time.setText(tr('Lumen-Wiedergabe konnte nicht pausiert werden. Wiedergabe erneut starten.'))

    def _drop_lease(self):
        leases, self.leases = self.leases, {}
        self.awaiting.clear()
        for lease in leases.values():
            lease.abort()
            lease.deleteLater()

    def stop(self):
        self.pending = None
        self.wait.stop()
        self.poll.stop()
        self._drop_lease()
        self.auto_paused = False
        if self.preflight:
            job, self.preflight = self.preflight, None
            job.cancelled.set()
            job.wait(3000)
        if self.monitor:
            monitor, self.monitor = self.monitor, None
            monitor.kill()
            monitor.waitForFinished(300)
            monitor.deleteLater()

    def manual(self):
        """A user's stop/pause/resume takes precedence over automatic resumption."""
        self.auto_paused = False

    def _accept(self):
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            self.clients.add(client)
            client.readyRead.connect(lambda c=client: self._request(c))
            client.disconnected.connect(lambda c=client: self._release(c))
            timeout = QTimer(client)
            timeout.setSingleShot(True)
            timeout.timeout.connect(lambda c=client: c.abort() if c not in self.holds else None)
            timeout.start(1000)

    def _request(self, client):
        if client in self.holds:
            client.abort()
            return
        if client.bytesAvailable() > 1024:
            client.abort()
            return
        if not client.canReadLine():
            return
        try:
            request = json.loads(bytes(client.readLine()))
            if request != dict(app=request.get('app'), version=1) or request['app'] not in ('reader', 'meetings'):
                raise ValueError()
        except (ValueError, AttributeError, TypeError):
            client.abort()
            return
        first = not self.holds
        self.holds.add(client)
        if first and self.player.proc and not self.player.paused:
            self.player.set_paused(True)
            self.auto_paused = True
        client.write(b'held\n')

    def _release(self, client):
        self.holds.discard(client)
        self.clients.discard(client)
        client.deleteLater()
        if not self.holds and self.auto_paused:
            self.auto_paused = False
            if self.player.proc and self.player.paused:
                self.player.set_paused(False)

    def check_output(self):
        if self.monitor or not self.player.proc or self.player.paused:
            return
        monitor = worker_process(self)
        self.monitor = monitor
        monitor.setProcessChannelMode(QProcess.SeparateChannels)
        monitor.finished.connect(lambda code, _: self._output_ready(monitor, code))
        monitor.errorOccurred.connect(lambda _: self._output_ready(monitor, 1))
        monitor.start('pactl', ['-f', 'json', 'list', 'sinks'])

    def _output_ready(self, monitor, code):
        if monitor is not self.monitor:
            return
        self.monitor = None
        try:
            if code == 0:
                sinks = json.loads(bytes(monitor.readAllStandardOutput()))
                self.observe_outputs({sink['name'] for sink in sinks})
        except (ValueError, KeyError, TypeError):
            pass
        finally:
            monitor.deleteLater()

    def observe_outputs(self, names):
        """Update controls; strict no-fallback is enforced by server properties."""
        if (self.prefs['pause_disconnect'] or self.prefs.get('strict_routing')) and self.prefs['sink'] not in names and self.player.proc and not self.player.paused:
            self.manual()
            self.player.set_paused(True)
            self._drop_lease()
            self.player.time.setText(tr('Audioausgang getrennt · Wiedergabe pausiert.'))


def controller(player):
    if not hasattr(player, '_lumen_audio'):
        window = player.window()
        app = getattr(window, 'name', '')
        if app not in NAMES:
            return None
        player._lumen_audio = Controller(player, app, window.library.root.parent)
    return player._lumen_audio


def options(player):
    window = player.window()
    control = controller(player)
    if not control:
        return
    from interop_audio_route import snapshot, strict_reason
    from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel

    def ready(snapshot):
        dialog = QDialog(window)
        dialog.setWindowTitle(tr('Lumen Audioausgabe'))
        dialog.resize(700, 320)
        form = QFormLayout(dialog)
        prefs = preferences(control.app, control.root)
        sink = QComboBox()
        sink.addItem(tr('Aktueller Standardausgang'), '')
        for item in snapshot['sinks']:
            sink.addItem(item.get('description', item['name']), item['name'])
        if prefs['sink'] and sink.findData(prefs['sink']) < 0:
            sink.addItem(tr('Nicht verbunden · ') + prefs['sink'], prefs['sink'])
        sink.setCurrentIndex(max(0, sink.findData(prefs['sink'])))
        form.addRow(tr('Ausgabe für diese Lumen-Anwendung'), sink)
        interrupt = QCheckBox(tr('Lumen Persönliches Radio und Lumen Reader während dieser Wiedergabe pausieren') if control.app == 'meetings' else tr('Lumen Persönliches Radio während dieser Wiedergabe pausieren'))
        interrupt.setChecked(prefs['pause_radio'])
        if control.app != 'radio':
            form.addRow(interrupt)
        disconnect = QCheckBox(tr('Beim Trennen dieses Ausgangs pausieren'))
        disconnect.setChecked(prefs['pause_disconnect'])
        form.addRow(disconnect)
        strict = QCheckBox(tr('Bei Geräteausfall niemals auf einen anderen Audioausgang wechseln'))
        strict.setChecked(prefs.get('strict_routing', False))
        form.addRow(strict)
        support = QLabel(); support.setWordWrap(True); form.addRow(support)
        def update_support():
            chosen = next((item for item in snapshot['sinks'] if item['name'] == sink.currentData()), None)
            reason = strict_reason(snapshot, chosen)
            strict.setEnabled(not reason or strict.isChecked())
            support.setText(reason or tr('Der separate USB-/Bluetooth-Ausgang wird fest gebunden. Bei seinem Ausfall beendet PipeWire den Audiostream ohne Ausweichgerät.'))
        sink.currentIndexChanged.connect(update_support)
        strict.toggled.connect(update_support)
        update_support()
        note = QLabel(tr('Ohne feste Gerätesperre wird die Trennung regelmäßig geprüft; ein kurzer Wechsel auf Lautsprecher kann dabei technisch nicht ausgeschlossen werden.'))
        note.setWordWrap(True)
        form.addRow(note)
        note = QLabel(tr('Gilt ab der nächsten Wiedergabe. Automatisches Fortsetzen nur nach einer automatischen Radio-Pause.'))
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.Accepted:
            window.safe(save_preferences, control.app, dict(sink=sink.currentData(), pause_radio=interrupt.isChecked(), pause_disconnect=disconnect.isChecked(), strict_routing=strict.isChecked()), control.root)
    def show_options(state):
        timer = QTimer(window)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: ready(state))
        timer.timeout.connect(timer.deleteLater)
        timer.start(0)
    window.work(tr('Audioausgänge werden gelesen …'), snapshot, show_options)
