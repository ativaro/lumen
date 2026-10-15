"""Lumen Drive browsing and selective offline folders inside Lumen Files."""

from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QFileDialog,
    QMessageBox,
    QInputDialog,
)
from tools_ui import button, Job
from lumen_i18n import tr
import lumen_connect
import drive_sync as sync
import drive_local as local
import drive_transport as transport


class Drive(QDialog):
    def __init__(
        self, parent=None, local_path=None, folder=None, offline=False
    ):
        super().__init__(parent)
        self.setWindowTitle("Lumen Drive")
        self.resize(1060, 730)
        self.job = None
        self.cache = dict(files={}, folders={})
        self.folder = folder
        self.initial_offline = offline
        self.local_path = local_path
        self.profile = {}
        self.closing = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)
        heading = QLabel("Lumen Drive")
        heading.setObjectName("heading")
        outer.addWidget(heading)
        top = QHBoxLayout()
        top.addStretch()
        top.addWidget(button(tr("Serververbindung"), self.connection, "network-server"))
        top.addWidget(button(tr("Aktualisieren"), self.reload, "view-refresh"))
        outer.addLayout(top)
        self.path = QLabel("/")
        self.path.setTextFormat(Qt.PlainText)
        outer.addWidget(self.path)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Dateien und Ordner suchen …"))
        self.search.textChanged.connect(self.render)
        outer.addWidget(self.search)
        actions = QHBoxLayout()
        for title, fn, icon in [
            (tr("Zurück"), self.up, "go-up"),
            (tr("Hochladen"), self.upload, "document-send"),
            (tr("Herunterladen"), self.download, "document-save"),
            (tr("Neuer Ordner"), self.new_folder, "folder-new"),
            (tr("Offline verfügbar …"), self.configure, "folder-sync"),
        ]:
            actions.addWidget(button(title, fn, icon))
        outer.addLayout(actions)
        self.list = QTreeWidget()
        self.list.setHeaderLabels([tr("Name"), tr("Art"), tr("Größe")])
        self.list.setRootIsDecorated(False)
        self.list.setAlternatingRowColors(False)
        self.list.setColumnWidth(0, 510)
        self.list.itemDoubleClicked.connect(self.open)
        outer.addWidget(self.list, 1)
        outer.addWidget(QLabel(tr("Synchronisierte Ordner")))
        self.roots = QComboBox()
        self.roots.setAccessibleName(tr("Synchronisierte Ordner"))
        outer.addWidget(self.roots)
        self.migration_status=QLabel()
        self.migration_status.setTextFormat(Qt.PlainText)
        self.migration_status.setWordWrap(True)
        outer.addWidget(self.migration_status)
        self.migration_button=button(tr('Ordner zuordnen …'),self.migrate_binding,'folder-sync')
        outer.addWidget(self.migration_button)
        self.roots.currentIndexChanged.connect(self.refresh_migration)
        commands = QHBoxLayout()
        for title, fn, icon in [
            (tr("Jetzt abgleichen"), self.sync_now, "view-refresh"),
            (tr("Pausieren / Fortsetzen"), self.pause, "media-playback-pause"),
            (tr("Lokalen Ordner öffnen"), self.open_local, "folder"),
            (tr("Konflikte lösen"), self.conflicts, "dialog-warning"),
            (tr("Verbindung entfernen"), self.remove, "edit-delete"),
        ]:
            commands.addWidget(button(title, fn, icon))
        outer.addLayout(commands)
        self.status = QLabel(tr("Serververbindung wird geprüft …"))
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh_roots)
        self.timer.start()
        QTimer.singleShot(0, self.reload)

    def work(self, fn, done=None):
        if self.job:
            return
        job = Job(fn, self)
        self.job = job
        self.list.setEnabled(False)
        job.progress.connect(self.status.setText)

        def result(value):
            try:
                if done:
                    done(value)
            except Exception as error:
                self.status.setText(str(error))

        job.result.connect(result)
        job.failed.connect(lambda message: self.status.setText(tr("Drive: ") + message))

        def finished():
            self.job = None
            self.list.setEnabled(True)
            self.refresh_roots()
            job.deleteLater()
            if self.closing:
                self.close()

        job.finished.connect(finished)
        job.start()

    def connection(self):
        from lumen_connect_gui import ConnectionDialog

        self.connection_dialog = ConnectionDialog(self)
        self.connection_dialog.show()

    def reload(self):
        if self.job: return
        self.cache = dict(files={}, folders={}); self.profile = {}
        self.render()

        def run(job):
            config = lumen_connect.read_config()
            profile = lumen_connect.request(config, '/bridge/me')
            job.check()
            return config, profile, sync.inventory(config)

        def done(value):
            self.config, self.profile, self.cache = value
            if self.folder and self.folder not in self.cache["folders"]:
                self.folder = None
                self.initial_offline = False
                self.status.setText(tr("Der verknüpfte Ordner ist nicht mehr verfügbar."))
            else:
                self.status.setText(tr("Aktueller Drive-Bestand · Dateien bis 64 MB"))
            self.render()
            if self.initial_offline:
                self.initial_offline = False
                QTimer.singleShot(100, self.configure)

        self.work(run, done)

    def render(self):
        self.list.clear()
        query = self.search.text().casefold()
        paths = sync.paths(self.cache, None)
        self.path.setText("/" + (paths.get(self.folder) or ""))
        for key, row in self.cache["folders"].items():
            if (
                row["trashed"]
                or row["parent_id"] != self.folder
                or query
                and query not in row["name"].casefold()
            ):
                continue
            item = QTreeWidgetItem([row["name"], tr("Ordner"), ""])
            item.setIcon(0, QIcon.fromTheme("folder"))
            item.setData(0, Qt.UserRole, ("folder", key))
            self.list.addTopLevelItem(item)
        for key, row in self.cache["files"].items():
            if (
                row["trashed"]
                or row["folder_id"] != self.folder
                or query
                and query not in row["name"].casefold()
            ):
                continue
            from core import size_text

            item = QTreeWidgetItem([row["name"], row["mime"], size_text(row["size"])])
            item.setData(0, Qt.UserRole, ("file", key))
            item.setIcon(0, QIcon.fromTheme("text-x-generic"))
            self.list.addTopLevelItem(item)

    def up(self):
        if self.job:
            return
        if self.folder:
            self.folder = self.cache["folders"][self.folder]["parent_id"]
            self.render()

    def open(self, item, _column=0):
        kind, key = item.data(0, Qt.UserRole)
        if kind == "folder":
            self.folder = key
            self.render()
        else:
            self.download()

    def progress(self, job):
        return lambda count, total: (
            job.check(),
            job.progress.emit(f"{count:,} / {total:,} " + tr("Bytes übertragen")),
        )

    def download(self):
        if self.job:
            return
        item = self.list.currentItem()
        if not item or item.data(0, Qt.UserRole)[0] != "file":
            return
        row = self.cache["files"][item.data(0, Qt.UserRole)[1]]
        folder = QFileDialog.getExistingDirectory(self, tr("Downloadordner"))
        if not folder:
            return
        root = self.local_root(folder)

        def run(job):
            if local.checksum(root, row["name"]) is not None:
                raise ValueError(
                    tr("Datei existiert bereits. Einen anderen Downloadordner wählen.")
                )
            staged = transport.download(self.config, root, row, self.progress(job))
            local.install(root, row["name"], staged, None)
            return str(Path(folder) / row["name"])

        self.work(run, lambda path: self.status.setText(tr("Gespeichert: ") + path))

    @staticmethod
    def local_root(path):
        p = Path(path).absolute()
        if p.is_symlink():
            raise ValueError(tr("Symbolische Ordner nicht verwenden."))
        st = p.stat()
        return dict(path=str(p), identity=[st.st_dev, st.st_ino])

    def upload(self):
        if not self.can_write(): return
        filename, _ = QFileDialog.getOpenFileName(
            self, tr("Datei in Lumen Drive ablegen")
        )
        if not filename:
            return
        path = Path(filename)
        root = self.local_root(path.parent)
        folder = self.folder
        self.work(
            lambda job: transport.upload(
                self.config,
                root,
                path.name,
                folder,
                str(uuid4()),
                local.checksum(root, path.name),
                None,
                self.progress(job),
            ),
            lambda _: QTimer.singleShot(50, self.reload),
        )

    def new_folder(self):
        if not self.can_write(): return
        name, ok = QInputDialog.getText(self, tr("Lumen Drive"), tr("Neuer Ordner"))
        if ok and name:
            self.work(
                lambda _: sync.request(
                    self.config,
                    "/folders",
                    dict(id=str(uuid4()), name=name, parent_id=self.folder),
                ),
                lambda _: QTimer.singleShot(50, self.reload),
            )

    def can_write(self):
        if self.job: return False
        current = self.cache["folders"].get(self.folder)
        if not (current.get("can_write", False) if current else self.profile.get("can_create", False)):
            self.status.setText(tr("Dieser Ordner ist nur zum Lesen freigegeben.")); return False
        return True

    def configure(self):
        if not self.can_write(): return
        if not self.folder:
            self.status.setText(tr("Zum Synchronisieren zuerst einen Drive-Ordner öffnen.")); return
        folder = self.local_path
        if not folder:
            choice = QMessageBox(self)
            choice.setWindowTitle("Lumen Drive")
            choice.setText(tr("Lokalen Drive-Ordner auswählen"))
            default = choice.addButton(
                str(Path.home() / "Lumen Drive"), QMessageBox.AcceptRole
            )
            other = choice.addButton(
                tr("Anderen Ordner auswählen …"), QMessageBox.ActionRole
            )
            choice.addButton(QMessageBox.Cancel)
            choice.exec()
            if choice.clickedButton() == default:
                folder = str(Path.home() / "Lumen Drive")
            elif choice.clickedButton() == other:
                folder = QFileDialog.getExistingDirectory(
                    self, tr("Lokalen Drive-Ordner auswählen"), str(Path.home())
                )
        if not folder:
            return
        remote = self.folder
        message = (
            tr("Automatisch in beide Richtungen synchronisieren?")
            + "\n\n"
            + self.config["server"]
            + "\n"
            + self.path.text()
            + "\n↔ "
            + folder
            + "\n\n"
            + tr(
                "Bestehende Dateien werden verglichen. Konflikte bleiben erhalten. Änderungen und Löschungen werden künftig übertragen. Sync ersetzt keine Sicherung."
            )
        )
        if (
            QMessageBox.question(
                self,
                tr("Lumen Drive · Ordner verbinden"),
                message,
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            != QMessageBox.Yes
        ):
            return
        self.work(
            lambda _: self.create_binding(folder, remote),
            lambda _: self.status.setText(
                tr("Ordner verbunden. Der Hintergrundabgleich startet automatisch.")
            ),
        )

    @staticmethod
    def create_binding(folder, remote):
        Path(folder).mkdir(mode=0o700, exist_ok=True)
        return sync.configure(folder, remote)

    def refresh_roots(self):
        previous = self.roots.currentData()
        self.roots.blockSignals(True)
        self.roots.clear()
        for root in sync.read()["roots"]:
            title = (
                Path(root["path"]).name
                + " · "
                + (tr("Umstellung erforderlich") if not root.get("folder") else root.get("status", "") if root["enabled"] else tr("Pausiert"))
            )
            self.roots.addItem(title, root["id"])
        if previous:
            self.roots.setCurrentIndex(max(0, self.roots.findData(previous)))
        self.roots.blockSignals(False)
        self.refresh_migration()

    def refresh_migration(self,*_):
        root=self.current_root()
        needed=bool(root and not root.get('folder'))
        self.migration_button.setVisible(needed)
        self.migration_status.setVisible(needed)
        if needed:
            count=sum(bool(e.get('pending') or e.get('request_id')) for e in root['entries'].values())
            self.migration_status.setText(tr('Umstellung erforderlich')+' · '+root['path']+'\n'+
                tr('Ausstehende Übertragungen:')+' '+str(count)+' · '+tr('Lokale Dateien und Warteschlange bleiben erhalten.'))
            self.migration_button.setText(tr('Umstellung fortsetzen …') if root.get('migration') else tr('Ordner zuordnen …'))

    def migrate_binding(self):
        root=self.current_root()
        if self.job or not root or root.get('folder'):return
        from drive_migration_ui import Migration
        if Migration(self,root).exec()==QDialog.Accepted:
            self.folder=(self.current_root() or {}).get('folder') or self.folder
            self.reload()
        self.refresh_roots()

    def current_root(self):
        return next(
            (r for r in sync.read()["roots"] if r["id"] == self.roots.currentData()),
            None,
        )

    def sync_now(self):
        root = self.current_root()
        if root:
            self.work(
                lambda job: sync.synchronize(root["id"], self.progress(job)),
                lambda _: QTimer.singleShot(50, self.reload),
            )

    def pause(self):
        root = self.current_root()
        if root:
            self.work(lambda _: sync.toggle(root["id"], not root["enabled"]))

    def remove(self):
        root = self.current_root()
        if (
            root
            and QMessageBox.question(
                self,
                tr("Lumen Drive"),
                tr(
                    "Abgleich beenden? Lokale Dateien und Serverdateien bleiben erhalten."
                ),
            )
            == QMessageBox.Yes
        ):
            self.work(lambda _: sync.toggle(root["id"], remove=True))

    def open_local(self):
        root = self.current_root()
        if root:
            QDesktopServices.openUrl(QUrl.fromLocalFile(root["path"]))

    def conflicts(self):
        root = self.current_root()
        if not root:
            return
        entries = root.get("conflicts", {})
        if not entries:
            QMessageBox.information(
                self,
                "Lumen Drive",
                "\n".join(root.get("errors", [])) or tr("Keine Konflikte."),
            )
            return
        keys = list(entries)
        labels = [entries[k]["title"] for k in keys]
        title, ok = QInputDialog.getItem(
            self,
            tr("Lumen Drive · Konflikt lösen"),
            tr("Datei oder Ordner"),
            labels,
            0,
            False,
        )
        if not ok:
            return
        key = keys[labels.index(title)]
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Lumen Drive")
        dialog.setText(title)
        dialog.setInformativeText(
            tr(
                "Welche Fassung weiterverwenden? Die bisherige lokale Datei bleibt bei Ersetzen in .lumen-drive/history erhalten."
            )
        )
        a = dialog.addButton(tr("Lokale Fassung"), QMessageBox.AcceptRole)
        b = dialog.addButton(tr("Serverfassung"), QMessageBox.AcceptRole)
        dialog.addButton(QMessageBox.Cancel)
        dialog.exec()
        if dialog.clickedButton() in (a, b):
            self.work(
                lambda _: sync.choose(
                    root["id"],
                    key,
                    "local" if dialog.clickedButton() == a else "server",
                ),
                lambda _: self.status.setText(
                    tr("Auswahl gespeichert. Jetzt abgleichen.")
                ),
            )

    def closeEvent(self, event):
        if self.job:
            self.closing = True
            self.job.cancelled.set()
            event.ignore()
        else:
            self.timer.stop()
            event.accept()


def show(window, path=None, folder=None, offline=False):
    current = getattr(window, "drive_dialog", None)
    if current and current.isVisible():
        if not current.job:
            current.folder = folder
            current.initial_offline = offline
            current.reload()
        current.raise_()
        current.activateWindow()
        return
    window.drive_dialog = Drive(window, path, folder, offline)
    window.drive_dialog.show()
