"""Native approval for a server-initiated connection. No terminal and no inbound listener."""

import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
from uuid import UUID

from PySide6.QtCore import QSettings, Qt, QThread, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

import lumen_connect as client

desktop_files = Path(os.environ.get("LUMEN_DESKTOP_FILES", Path.home() / ".local/share/lumen/files"))
if Path(__file__).with_name("appearance.py").is_file():
    desktop_files = Path(__file__).parent
sys.path.insert(0, str(desktop_files))


def t(de, en):
    from lumen_i18n import language

    return de if language() == "de" else en


def label(text, size=None):
    item = QLabel(text)
    item.setTextFormat(Qt.PlainText)
    item.setWordWrap(True)
    if size:
        font = item.font()
        font.setPointSize(size)
        font.setBold(size >= 20)
        item.setFont(font)
    return item


class Worker(QThread):
    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation
        self.result = None
        self.error = ""

    def run(self):
        try:
            self.result = self.operation()
        except urllib.error.HTTPError as error:
            self.error = (
                t(
                    "Die Anfrage ist abgelaufen. Bitte im Server erneut starten.",
                    "This request expired. Please start again on the server.",
                )
                if error.code == 410
                else t("Der Server hat die Anfrage abgelehnt.", "The server rejected this request.")
            )
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            self.error = t(
                "Die Verbindung konnte nicht eingerichtet werden. Prüfe Serveradresse, Zertifikat und Netzwerk.",
                "Could not set up the connection. Check the server address, certificate and network.",
            )


def accept_pairing(uri):
    client.ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (client.ROOT / "pairing.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if client.CONFIG.exists():
            raise ValueError("Eine vorhandene Verbindung wird nicht ersetzt.")
        config = client.pairing_request(uri, "approve")
        UUID(config["device_id"])
        if not all(
            isinstance(config.get(k), str) and 32 <= len(config[k]) <= 200 for k in ("token", "backup_token")
        ):
            raise ValueError("Ungültige Geräteantwort.")
        identity = client.request(config, "/bridge/me")
        if not isinstance(identity, dict) or identity.get("device_id") != config["device_id"]:
            raise ValueError("Gerätekennung stimmt nicht.")
        config["system_access"] = dict(
            server=config["server"],
            device_id=config["device_id"],
            version=2,
            enabled="system_read" in config.get("capabilities", []),
        )
        client.save_private(client.CONFIG, json.dumps(config))
    try:
        service = subprocess.run(
            ["systemctl", "--user", "enable", "--now", "lumen-server-connector.service"],
            capture_output=True,
            timeout=20,
        )
        return {"watching": service.returncode == 0}
    except (OSError, subprocess.SubprocessError):
        return {"watching": False}


class PairingDialog(QDialog):
    def __init__(self, uri):
        super().__init__()
        self.uri = uri
        self.worker = None
        self.callback = None
        self.setWindowTitle(t("Lumen · Server verbinden", "Lumen · Connect server"))
        self.setWindowIcon(QIcon.fromTheme("lumen"))
        self.setMinimumSize(560, 550)
        self.resize(580, 550)
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(18)
        header = QHBoxLayout()
        icon = QLabel()
        fallback = (
            Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
            / "icons/hicolor/scalable/apps/lumen.svg"
        )
        icon.setPixmap(QIcon.fromTheme("lumen", QIcon(str(fallback))).pixmap(52, 52))
        header.addWidget(icon)
        header.addWidget(label("Lumen Desktop", 14), 1)
        root.addLayout(header)
        self.title = label(t("Dein Server möchte sich verbinden.", "Your server wants to connect."), 23)
        root.addWidget(self.title)
        self.description = label(
            t(
                "Prüfe die Adresse und das Konto, bevor du zustimmst.",
                "Check the address and account before you approve.",
            )
        )
        root.addWidget(self.description)
        card = QFrame()
        card.setObjectName("serverIdentity")
        card.setStyleSheet(
            "QFrame#serverIdentity { border: 1px solid palette(mid); border-radius: 14px; background: palette(base); }"
        )
        fields = QVBoxLayout(card)
        fields.setContentsMargins(18, 16, 18, 16)
        fields.setSpacing(8)
        self.server = label("", 11)
        self.account = label(t("Anfrage wird geprüft …", "Checking request …"), 10)
        self.account.setMinimumHeight(self.account.fontMetrics().lineSpacing() * 3 + 8)
        fields.addWidget(self.server)
        fields.addWidget(self.account)
        root.addWidget(card)
        self.permissions = label(
            t(
                "Die Verbindung gleicht bestätigte Server-Erinnerungen ab und zeigt neue Berichte. Sie ermöglicht Serveraufträge und ein verschlüsseltes Sicherungsziel. Lokale Dateien werden dadurch nicht hochgeladen; Desktop-Aufträge werden nicht automatisch ausgeführt.",
                "This connection syncs approved server memories and shows new reports. It enables server tasks and an encrypted backup destination. Local files are not uploaded by pairing; desktop tasks are not executed automatically.",
            )
        )
        root.addWidget(self.permissions)
        self.status = label("")
        self.status.setAccessibleName(t("Verbindungsstatus", "Connection status"))
        root.addWidget(self.status)
        root.addStretch()
        row = QHBoxLayout()
        self.decline = QPushButton(t("Ablehnen", "Decline"))
        self.decline.setObjectName("quiet")
        self.decline.setAutoDefault(False)
        self.approve = QPushButton(t("Verbinden", "Connect"))
        self.approve.setStyleSheet(
            "QPushButton { background: palette(highlight); color: palette(highlighted-text); border: none; padding: 10px 20px; } QPushButton:disabled { background: palette(button); color: palette(text); }"
        )
        self.approve.setAutoDefault(False)
        self.approve.setEnabled(False)
        row.addWidget(self.decline)
        row.addStretch()
        row.addWidget(self.approve)
        root.addLayout(row)
        self.decline.clicked.connect(self.reject_request)
        self.approve.clicked.connect(self.confirm)
        try:
            config, _ = client.parse_pairing_uri(uri)
            self.server.setText(config["server"])
            if client.CONFIG.exists():
                self.status.setText(
                    t(
                        "Dieser Desktop ist bereits verbunden. Die vorhandene Verbindung bleibt erhalten.",
                        "This desktop is already paired. Its existing connection will be preserved.",
                    )
                )
                self.account.setText("")
            else:
                QTimer.singleShot(
                    0, lambda: self.run_job(lambda: client.pairing_request(uri, "preview"), self.preview)
                )
        except ValueError:
            self.account.setText("")
            self.status.setText(
                t(
                    "Ungültige Anfrage. Bitte die Verbindung im Server starten.",
                    "Invalid request. Please start the connection on the server.",
                )
            )

    def run_job(self, operation, callback):
        self.callback = callback
        self.approve.setEnabled(False)
        self.decline.setEnabled(False)
        self.worker = Worker(operation, self)
        self.worker.finished.connect(self.finished_job)
        self.worker.start()

    def finished_job(self):
        self.decline.setEnabled(True)
        if self.worker.error:
            self.status.setText(self.worker.error)
        else:
            self.callback(self.worker.result)

    def preview(self, data):
        self.account.setText(data["account"] + "\n" + data["email"] + "\n" + data["name"])
        rights = {
            "backup": t("Verschlüsselte Sicherungen", "Encrypted backups"),
            "tasks": t("Serveraufträge", "Server tasks"),
            "artifacts": t("Ergebnisdateien", "Result files"),
            "memory": t("Bestätigtes Gedächtnis", "Approved memory"),
            "notifications": t("Benachrichtigungen", "Notifications"),
            "desktop": t("Desktop-Übergaben", "Desktop handoffs"),
            "system_read": t(
                "Systemstatus und Geräteinformationen ohne weitere Rückfragen",
                "System status and device information without further prompts",
            ),
            "projects": t("Projekte synchronisieren", "Synchronize projects"),
            "drive": t("Lumen Drive synchronisieren", "Synchronize Lumen Drive"),
            "notes": t("Notizen synchronisieren", "Synchronize notes"),
            "approvals": t("Serveränderungen am Desktop freigeben", "Approve server changes on desktop"),
            "device_control": t("Andere Servergeräte von diesem Desktop verwalten", "Manage other server devices from this desktop"),
            "manage": t("Lumen-Dienste und Updates verwalten", "Manage Lumen services and updates"),
            "wake": t("Geräte im lokalen Netzwerk aufwecken", "Wake devices on the local network"),
            "vault_sync": t("Verschlüsselten Tresor abgleichen", "Encrypted vault synchronization"),
            "services": t("Freigegebene Dienstzugänge", "Delegated service access"),
            "inbox": t("Mailkonten lesen und Entwürfe vorschlagen", "Read mail and propose drafts"),
            "household": t("Haushaltseinträge lesen und bearbeiten", "Read and edit household entries"),
        }
        selected = data.get(
            "capabilities",
            [
                key
                for key in rights
                if key
                not in (
                    "services",
                    "inbox",
                    "household",
                    "notes",
                    "projects",
                    "drive",
                    "vault_sync",
                    "wake",
                    "manage",
                    "device_control",
                    "approvals",
                )
            ],
        )
        self.permissions.setText(
            t("Freigegebene Fähigkeiten:\n", "Allowed capabilities:\n")
            + "\n".join("• " + rights[k] for k in selected if k in rights)
        )
        self.approve.setEnabled(data.get("protocol", 1) == 1)
        self.decline.setFocus()

    def confirm(self):
        self.status.setText(t("Verbindung wird eingerichtet …", "Setting up the connection …"))
        self.run_job(lambda: accept_pairing(self.uri), self.connected)

    def connected(self, data):
        self.title.setText(t("Dein Desktop ist verbunden.", "Your desktop is connected."))
        self.status.setText(
            t("Der Abgleich läuft jetzt im Hintergrund.", "Sync is now running in the background.")
            if data["watching"]
            else t(
                "Verbunden. Der Hintergrunddienst konnte nicht gestartet werden.",
                "Connected. The background service could not be started.",
            )
        )
        self.approve.hide()
        self.decline.setText(t("Fertig", "Done"))
        self.decline.clicked.disconnect()
        self.decline.clicked.connect(self.accept)

    def reject_request(self):
        if self.approve.isEnabled():
            self.run_job(lambda: client.pairing_request(self.uri, "decline"), lambda _: self.reject())
        else:
            self.reject()

    def reject(self):
        if not self.worker or not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)


class ArtifactDialog(QDialog):
    def __init__(self, identity):
        super().__init__()
        self.identity = str(UUID(identity))
        self.config = client.read_config()
        self.worker = None
        self.action = None
        self.setWindowTitle(t("Lumen · Datei vom Server", "Lumen · File from server"))
        self.resize(520, 320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        self.heading = label(t("Auf diesem Desktop öffnen?", "Open on this desktop?"), 22)
        layout.addWidget(self.heading)
        self.details = label(self.config["server"])
        layout.addWidget(self.details)
        self.notice = label(
            t(
                "Eine geprüfte Kopie wird lokal geöffnet. Deine Dateien bleiben erhalten.",
                "A verified copy will be opened locally. Your existing files are preserved.",
            )
        )
        layout.addWidget(self.notice)
        self.status = label(t("Anfrage wird geprüft …", "Checking request …"))
        layout.addWidget(self.status)
        controls = QHBoxLayout()
        self.decline = QPushButton(t("Ablehnen", "Decline"))
        self.open = QPushButton(t("Öffnen", "Open"))
        self.open.setEnabled(False)
        controls.addWidget(self.decline)
        controls.addStretch()
        controls.addWidget(self.open)
        layout.addLayout(controls)
        self.decline.clicked.connect(self.declined)
        self.open.clicked.connect(self.accepted_request)
        self.work(lambda: client.request(self.config, "/bridge/actions/" + self.identity), self.preview)

    def work(self, operation, callback):
        self.open.setEnabled(False)
        self.decline.setEnabled(False)
        self.worker = Worker(operation, self)

        def done():
            self.decline.setEnabled(True)
            if self.worker.error:
                self.status.setText(self.worker.error)
            else:
                callback(self.worker.result)

        self.worker.finished.connect(done)
        self.worker.start()

    def preview(self, action):
        self.action = action
        self.details.setText(
            action["name"] + " · " + str(action["size"]) + " Bytes\n" + self.config["server"]
        )
        self.status.setText(t("Nur diese Datei wird freigegeben.", "Only this file is shared."))
        self.open.setEnabled(action["state"] == "pending")

    def accepted_request(self):
        self.status.setText(t("Datei wird geprüft …", "Verifying file …"))
        self.work(lambda: client.receive_artifact(self.config, self.action), self.opened)

    def opened(self, result):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(result["path"]))
        self.work(
            lambda: client.request(
                self.config,
                "/bridge/actions/" + self.identity,
                dict(state="completed" if opened else "failed", revision=result["revision"]),
            ),
            lambda _: self.accept(),
        )

    def declined(self):
        if self.action and self.action["state"] == "pending":
            self.work(
                lambda: client.request(
                    self.config,
                    "/bridge/actions/" + self.identity,
                    dict(state="declined", revision=self.action["revision"]),
                ),
                lambda _: self.reject(),
            )
        else:
            self.reject()

    def reject(self):
        if not self.worker or not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)


class LaunchDialog(ArtifactDialog):
    def __init__(self, identity):
        super().__init__(identity)
        self.setWindowTitle(t("Lumen · App auf diesem Desktop", "Lumen · App on this desktop"))
        self.heading.setText(t("App hier öffnen?", "Open app here?"))
        self.notice.setText(t("Bestätige den Start auf diesem Gerät.", "Confirm launching on this device."))

    def preview(self, action):
        self.action = action
        names = {"companion": "Lumen Companion", "system": "Lumen System"}
        if action.get("app") not in names:
            self.status.setText(t("Diese App ist nicht freigegeben.", "This app is not allowed."))
            return
        self.details.setText(names[action["app"]] + "\n" + self.config["server"])
        self.status.setText(
            t(
                "Nur die App wird geöffnet. Ein Fenster wählst du anschließend selbst; erst nach deiner Vorschau-Freigabe darf Companion ein Bild verarbeiten.",
                "Only the app opens. You select a window yourself; Companion processes an image only after your preview consent.",
            )
        )
        self.open.setEnabled(action["state"] == "pending")

    def accepted_request(self):
        def claim():
            result = client.request(
                self.config,
                "/bridge/actions/" + self.identity,
                dict(state="claimed", revision=self.action["revision"]),
            )
            if result.get("replayed"):
                return result
            current = client.request(self.config, "/bridge/actions/" + self.identity)
            if current["state"] != "claimed" or current["revision"] != result["revision"]:
                raise ValueError("Request no longer valid")
            return result

        self.work(claim, self.launch)

    def launch(self, result):
        if result.get("replayed"):
            self.status.setText(
                t("Diese Anfrage wurde bereits ausgeführt.", "This request was already handled.")
            )
            return
        paths = {"companion": "screen_companion.py", "system": "system_app.py"}
        path = desktop_files / paths[self.action["app"]]
        try:
            if not path.is_file():
                raise OSError("Unavailable")
            subprocess.Popen(
                [sys.executable, str(path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self.status.setText(
                t(
                    "Diese App ist auf dem Desktop noch nicht installiert.",
                    "This app is not installed on the desktop yet.",
                )
            )
            state = "failed"
        else:
            state = "completed"
        self.work(
            lambda: client.request(
                self.config,
                "/bridge/actions/" + self.identity,
                dict(state=state, revision=result["revision"]),
            ),
            lambda _: self.accept() if state == "completed" else None,
        )


class SnapshotDialog(LaunchDialog):
    """Only the bounded measurements shown here leave the desktop after confirmation."""

    def __init__(self, identity):
        super().__init__(identity)
        self.setWindowTitle(t("Lumen · Systemstatus teilen", "Lumen · Share system status"))
        self.heading.setText(t("Diesen Systemstatus teilen?", "Share this system snapshot?"))
        self.notice.setText(
            t(
                "Nur CPU, Speicher, Laufwerk und Netzwerkraten werden einmalig mit deinem Server geteilt. Keine Prozessnamen, Fenster, Dateien oder laufende Überwachung.",
                "Share CPU, memory, disk and network rates once with your server. No process names, windows, files or ongoing monitoring.",
            )
        )
        self.open.setText(t("Status teilen", "Share snapshot"))
        self.snapshot = None

    def preview(self, action):
        self.action = action
        if action.get("app") != "system_snapshot" or action.get("state") != "pending":
            self.status.setText(t("Diese Anfrage ist nicht mehr gültig.", "This request is no longer valid."))
            return
        self.details.setText(self.config["server"])
        self.status.setText(t("Lokale Vorschau wird gemessen …", "Measuring local preview …"))
        self.work(system_snapshot, self.measured)

    def measured(self, value):
        self.snapshot = value

        def gib(number):
            return "—" if number is None else f"{number / 1024**3:.1f} GiB"

        def rate(number):
            return "—" if number is None else f"{number / 1024:.1f} KiB/s"

        self.details.setText(
            self.config["server"]
            + "\n\n"
            + f"CPU: {value['cpu'] if value['cpu'] is not None else '—'} % · {value['cores']} "
            + t("Kerne", "cores")
            + "\n"
            + f"RAM: {gib(value['memory_used'])} / {gib(value['memory_total'])}\n"
            + t("Laufwerk", "Disk")
            + f": {gib(value['disk_used'])} / {gib(value['disk_total'])}\n"
            + t("Netzwerk", "Network")
            + f": ↓ {rate(value['receive'])} ↑ {rate(value['send'])}"
        )
        self.status.setText(
            t(
                "Einmalige Momentaufnahme. Erst mit deiner Bestätigung senden.",
                "One-time snapshot. Send only after your confirmation.",
            )
        )
        self.open.setEnabled(True)

    def launch(self, claimed):
        if claimed.get("replayed") or not self.snapshot:
            self.status.setText(
                t("Diese Anfrage wurde bereits übernommen.", "This request was already claimed.")
            )
            return
        self.work(
            lambda: client.request(
                self.config,
                "/bridge/actions/" + self.identity,
                dict(state="completed", revision=claimed["revision"], result=self.snapshot),
            ),
            lambda _: self.accept(),
        )


def system_snapshot():
    return client.system_snapshot()


class HandoffDialog(QDialog):
    """A bounded text task; local tools and implicit desktop memory stay disabled."""

    def __init__(self, identity):
        super().__init__()
        from PySide6.QtWidgets import QPlainTextEdit

        self.identity = str(UUID(identity))
        self.config = client.read_config()
        self.worker = self.backend = None
        self.task = None
        self.running = False
        self.pending_result = None
        self.setWindowTitle(t("Lumen · Auftrag übernehmen", "Lumen · Continue task"))
        self.resize(600, 540)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        layout.addWidget(label(t("Hier weiterarbeiten", "Continue here"), 22))
        layout.addWidget(label(self.config["server"]))
        self.content = QPlainTextEdit()
        self.content.setReadOnly(True)
        self.content.setAccessibleName(
            t("Auftrag und bestätigter Zwischenstand", "Task and approved checkpoint")
        )
        layout.addWidget(self.content, 1)
        layout.addWidget(
            label(
                t(
                    "Nur dieser Auftrag und sein ausdrücklich freigegebener Kontext werden verarbeitet. Keine lokalen Dateien oder Werkzeuge. Das Ergebnis geht zurück an deinen Server.",
                    "Only this task and its explicitly shared context will be processed. No local files or tools. The result returns to your server.",
                )
            )
        )
        self.status = label(t("Anfrage wird geprüft …", "Checking request …"))
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.close_button = QPushButton(t("Schließen", "Close"))
        self.start_button = QPushButton(t("Auf diesem Desktop fortsetzen", "Continue on this desktop"))
        self.start_button.setEnabled(False)
        row.addWidget(self.close_button)
        row.addStretch()
        row.addWidget(self.start_button)
        layout.addLayout(row)
        self.close_button.clicked.connect(self.stop_or_close)
        self.start_button.clicked.connect(self.claim)
        self.lease = QTimer(self)
        self.lease.setInterval(15000)
        self.lease.timeout.connect(self.renew)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(self.lost)
        self.work("/handoff", None, self.preview)

    def work(self, suffix, body, callback):
        if self.worker and self.worker.isRunning():
            return False
        self.worker = Worker(
            lambda: client.request(self.config, "/bridge/tasks/" + self.identity + suffix, body), self
        )
        worker = self.worker

        def done():
            if worker.error:
                self.lost()
                self.status.setText(worker.error)
            else:
                callback(worker.result)
            if self.pending_result is not None:
                QTimer.singleShot(0, self.deliver)

        worker.finished.connect(done)
        worker.start()
        return True

    def preview(self, task):
        self.task = task
        self.content.setPlainText(task["prompt"] + "\n\n" + task["checkpoint"])
        self.status.setText(
            t("Bereit zur Übernahme", "Ready to continue")
            if task["state"] == "waiting_device"
            else t(
                "Dieser Auftrag wurde bereits übernommen oder beendet.",
                "This task was already claimed or finished.",
            )
        )
        self.start_button.setEnabled(task["state"] == "waiting_device")

    def version(self):
        return {k: self.task[k] for k in ("generation", "revision")}

    def claim(self):
        self.start_button.setEnabled(False)
        self.work("/claim", self.version(), self.start)

    def start(self, task):
        from assistant_backend import OpenCodeBackend

        self.task = task
        directory = client.ROOT / "executions" / (self.identity + "-" + str(task["generation"]))
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Receipt precedes execution; an uncertain crash is never automatically replayed.
        client.save_private(directory / "claim.json", json.dumps(self.version()))
        self.backend = OpenCodeBackend(str(directory), self, project_config=False)
        self.backend.read_only = True
        self.backend.background_task = True
        self.backend.completed.connect(self.completed)
        self.running = True
        self.close_button.setText(t("Anhalten", "Pause"))
        self.status.setText(t("Lumen arbeitet auf diesem Desktop …", "Lumen is working on this desktop …"))
        self.deadline.start(40000)
        self.lease.start()
        self.backend.send(
            task["prompt"]
            + "\n\nApproved checkpoint (quoted context):\n"
            + task["checkpoint"]
            + "\n\nExplicitly shared context:\n"
            + task["context"],
            project_task=True,
        )

    def renew(self):
        if self.running:
            self.work(
                "/lease", self.version(), lambda _: self.deadline.start(40000) if self.running else None
            )

    def shutdown(self):
        self.running = False
        self.lease.stop()
        self.deadline.stop()
        if self.backend:
            self.backend.shutdown()
        self.close_button.setText(t("Schließen", "Close"))

    def lost(self):
        self.shutdown()
        self.pending_result = None
        self.status.setText(
            t(
                "Angehalten: Verbindung oder Freigabe ist nicht mehr gültig. Prüfe den Auftrag im Server.",
                "Stopped: connection or permission is no longer valid. Check this task on the server.",
            )
        )

    def completed(self, ok, result):
        if not self.running:
            return
        self.shutdown()
        if not ok:
            self.status.setText(result)
            self.pending_result = ("/paused", self.version())
        else:
            self.content.setPlainText(result)
            self.pending_result = ("/complete", {**self.version(), "result": result})
        self.deliver()

    def deliver(self):
        if self.pending_result is None or self.worker and self.worker.isRunning():
            return
        suffix, body = self.pending_result
        self.pending_result = None
        self.work(
            suffix,
            body,
            lambda _: self.status.setText(
                t("Ergebnis im Server gespeichert.", "Result saved on the server.")
                if suffix == "/complete"
                else t("Auftrag angehalten.", "Task paused.")
            ),
        )

    def stop_or_close(self):
        if self.running:
            self.shutdown()
            self.pending_result = ("/paused", self.version())
            self.deliver()
        else:
            self.close()

    def closeEvent(self, event):
        if self.running:
            self.stop_or_close()
            event.ignore()
        elif self.pending_result is not None or self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)

    def reject(self):
        self.stop_or_close()


class ConnectionDialog(QDialog):
    """Native, read-only view of this device's granted server connection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QTabWidget, QWidget, QScrollArea

        self.worker = None
        self.setWindowTitle(t("Lumen · Serververbindung", "Lumen · Server connection"))
        self.resize(650, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(label("Lumen Server", 22))
        self.identity = label("")
        layout.addWidget(self.identity)
        self.status = label("")
        layout.addWidget(self.status)
        tabs = QTabWidget()
        self.sections = {}
        for key, title in (
            ("tasks", t("Aufträge", "Tasks")),
            ("backup", t("Sicherungen", "Backups")),
            ("memory", t("Geteiltes Gedächtnis", "Shared memory")),
        ):
            area = QScrollArea()
            area.setWidgetResizable(True)
            page = QWidget()
            rows = QVBoxLayout(page)
            content = label("")
            content.setTextInteractionFlags(Qt.TextSelectableByMouse)
            rows.addWidget(content)
            rows.addStretch()
            area.setWidget(page)
            tabs.addTab(area, title)
            self.sections[key] = content
        try:
            from sync_overview import widget

            tabs.addTab(widget(self), t("Synchronisation", "Synchronization"))
        except ImportError:
            pass  # Standalone connector without the native apps.
        layout.addWidget(tabs, 1)
        self.system_access_button = QCheckBox(t("Automatische Systemabfragen", "Automatic system queries"))
        self.system_access_button.clicked.connect(self.change_system_access)
        layout.addWidget(self.system_access_button)
        layout.addWidget(
            label(
                t(
                    "Standardmäßig aktiv. Teilt Systemstatus und Geräteinformationen mit deinem Server. Jederzeit abschaltbar.",
                    "Enabled by default. Shares system status and device information with your server. Turn off at any time.",
                )
            )
        )
        controls = QHBoxLayout()
        self.refresh_button = QPushButton(t("Aktualisieren", "Refresh"))
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_button)
        self.browser = QPushButton(t("Im Browser verwalten", "Manage in browser"))
        self.browser.clicked.connect(self.open_browser)
        controls.addWidget(self.browser)
        controls.addStretch()
        close = QPushButton(t("Schließen", "Close"))
        close.clicked.connect(self.reject)
        controls.addWidget(close)
        layout.addLayout(controls)
        self.refresh()

    def change_system_access(self):
        enabled = self.system_access_button.isChecked()
        self.refresh_button.setEnabled(False)
        self.system_access_button.setEnabled(False)
        self.worker = Worker(lambda: client.set_system_access(enabled), self)
        self.worker.finished.connect(self.system_access_changed)
        self.worker.start()

    def system_access_changed(self):
        if self.worker.error:
            self.status.setText(self.worker.error)
            self.system_access_button.setChecked(client.system_access_allowed(self.config))
            self.system_access_button.setEnabled(True)
            self.refresh_button.setEnabled(True)
        else:
            self.refresh()

    def open_browser(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        if hasattr(self, "config"):
            QDesktopServices.openUrl(QUrl(self.config["server"]))

    def refresh(self):
        if self.worker and self.worker.isRunning():
            return
        try:
            self.config = client.read_config()
        except (OSError, ValueError):
            self.identity.setText(t("Noch nicht verbunden", "Not connected yet"))
            self.status.setText(
                t(
                    "Öffne deinen Lumen Server im Browser und wähle Geräte → Desktop verbinden.",
                    "Open your Lumen Server in a browser and choose Devices → Connect desktop.",
                )
            )
            self.browser.setEnabled(False)
            self.system_access_button.setText(
                t("Systemabfragen: zuerst verbinden", "System queries: connect first")
            )
            self.system_access_button.setEnabled(False)
            return
        self.system_access_button.setEnabled(True)
        self.system_access_button.setChecked(client.system_access_allowed(self.config))
        self.identity.setText(self.config["server"])
        self.status.setText(t("Verbindung wird geprüft …", "Checking connection …"))
        self.refresh_button.setEnabled(False)

        def connection_status():
            client.initialize_system_access(self.config)
            return client.request(self.config, "/bridge/connection")

        self.worker = Worker(connection_status, self)
        self.worker.finished.connect(self.loaded)
        self.worker.start()

    def loaded(self):
        self.refresh_button.setEnabled(True)
        if self.worker.error:
            self.status.setText(
                t(
                    "Der Server ist gerade nicht erreichbar oder die Verbindung wurde beendet. Bereits geladene Angaben werden ausgeblendet.",
                    "The server is unavailable or the connection has ended. Previously loaded details are hidden.",
                )
            )
            for content in self.sections.values():
                content.clear()
            return
        data = self.worker.result
        self.system_access_button.setChecked(
            client.system_access_allowed(self.config) and "system_read" in data["capabilities"]
        )
        self.status.setText(t("Verbunden · ", "Connected · ") + data["name"])
        states = {
            "completed": t("Erledigt", "Completed"),
            "running": t("Läuft", "Running"),
            "device_running": t("Läuft auf Desktop", "Running on desktop"),
            "queued": t("Wartet", "Queued"),
            "waiting_device": t("Wartet auf Desktop", "Waiting for desktop"),
            "interrupted": t("Unterbrochen", "Interrupted"),
            "failed": t("Fehlgeschlagen", "Failed"),
            "cancelled": t("Abgebrochen", "Cancelled"),
            "paused": t("Angehalten", "Paused"),
            "pause_requested": t("Wird angehalten", "Pausing"),
        }
        denied = t("Für dieses Gerät nicht freigegeben.", "Not shared with this device.")
        self.sections["tasks"].setText(
            "\n\n".join(
                row["title"]
                + "\n"
                + states.get(row["state"], row["state"])
                + " · "
                + ("Server" if row["target"] == "server" else "Desktop")
                for row in data["tasks"]
            )
            or (t("Noch keine Aufträge.", "No tasks yet.") if "tasks" in data["capabilities"] else denied)
        )
        backup = data["backup"]
        backup_states = {
            "running": t("Läuft", "Running"),
            "completed": t("Abgeschlossen", "Completed"),
            "failed": t("Fehlgeschlagen", "Failed"),
            "cancelled": t("Abgebrochen", "Cancelled"),
        }
        backup_errors = {
            "quota": t("Speichergrenze erreicht", "Storage quota reached"),
            "unavailable": t("Sicherungsziel nicht erreichbar", "Backup destination unavailable"),
            "storage": t("Speicherfehler", "Storage error"),
            "client": t("Fehler auf dem Desktop", "Desktop error"),
        }
        self.sections["backup"].setText(
            (
                t("Gemeldeter Zustand", "Reported state")
                + "\n"
                + backup_states.get(backup.get("backup_state"), t("Noch nicht gemeldet", "Not reported yet"))
                + (
                    " · " + backup_errors.get(backup["backup_error"], t("Fehler gemeldet", "Error reported"))
                    if backup.get("backup_error")
                    else ""
                )
                + "\n\n"
            )
            + "\n\n".join(
                title + "\n" + (backup.get(key) or "—")
                for key, title in (
                    ("last_backup", t("Letzte Sicherung", "Last backup")),
                    ("last_check", t("Vollständig geprüft", "Fully checked")),
                    ("last_restore", t("Wiederhergestellt", "Restored")),
                )
            )
            if backup
            else denied
        )
        memory = data["memory"]
        self.sections["memory"].setText(
            (
                t("Vom Desktop bestätigter Abgleich", "Sync acknowledged by desktop")
                + "\n"
                + str(memory["memory_synced_count"])
                + t(" Erinnerungen\n", " memories\n")
                + str(memory["memory_synced_at"] or t("Noch nicht bestätigt", "Not acknowledged yet"))
                + "\n\n"
                + t(
                    "Persönliche Notizen bleiben getrennt. Freigaben verwaltest du im Server; lokal kannst du Erinnerungen in Lumen Wissen ausschließen.",
                    "Personal notes remain separate. Manage sharing on the server; exclude memories locally in Lumen Knowledge.",
                )
            )
            if memory
            else denied
        )

    def reject(self):
        if not self.worker or not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)


def main():
    from appearance import apply_design, DEFAULT_DESIGN

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Lumen Server Connection")
    apply_design(app, QSettings("Lumen", "Assistant").value("appearance", DEFAULT_DESIGN))
    dialogs = {
        "--artifact": ArtifactDialog,
        "--handoff": HandoffDialog,
        "--launch": LaunchDialog,
        "--snapshot": SnapshotDialog,
    }
    dialog = (
        dialogs[sys.argv[1]](sys.argv[2])
        if len(sys.argv) == 3 and sys.argv[1] in dialogs
        else ConnectionDialog()
        if sys.argv[1:] == ["--status"]
        else PairingDialog(sys.argv[1] if len(sys.argv) == 2 else "")
    )
    dialog.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
