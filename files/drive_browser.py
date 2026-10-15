"""Paired Drive folders in the existing Files model, navigation and actions."""

import os
import tempfile
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

import drive_local as local
import drive_sync as sync
import drive_transport as transport
import lumen_connect
from core import size_text, valid_name
from lumen_i18n import tr
from lumen_jobs import Job
from PySide6.QtCore import QMimeData, QModelIndex, QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
)

ROOT = "lumen-drive://"


def is_drive(path):
    return str(path).startswith(ROOT)


location = sync.location
resolve = sync.resolve


def parse(path):
    kind, key = sync.parse_address(path)
    if kind == 'file':
        raise ValueError(tr('Bitte einen Drive-Ordner öffnen.'))
    return key


class Browser(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.model = QStandardItemModel(self)
        self.model.setHorizontalHeaderLabels(
            [tr("Name"), tr("Größe"), tr("Typ"), tr("Geändert"), tr("Ort")]
        )
        self.cache = dict(files={}, folders={})
        self.profile = {}
        self.entries = {}
        self.jobs = []
        self.generation = 0
        self.folder = None
        self.config = None
        # Opened files are explicitly local copies; no hidden upload from an editor.

    def work(self, fn, done, *, current=True):
        generation = self.generation
        job = Job(fn, self)
        self.jobs.append(job)

        def active():
            return (
                not current
                or generation == self.generation
                and is_drive(self.window.current_location)
            )

        def result(value):
            if active():
                try:
                    done(value)
                except Exception as error:
                    self.window.error(str(error))

        job.result.connect(result)
        job.progress.connect(
            lambda text: self.window.activity.setText(text) if active() else None
        )
        job.failed.connect(
            lambda message: (
                self.window.activity.setText("Lumen Drive: " + message)
                if active()
                else None
            )
        )

        def finished():
            self.jobs.remove(job)
            job.deleteLater()

        job.finished.connect(finished)
        job.start()

    def navigate(self, path, record=True, history_position=None, selected=None, identity=None):
        try:
            folder = parse(path)
        except ValueError as error:
            self.window.error(str(error))
            return
        w = self.window
        self.generation += 1
        self.folder = folder
        w.cancel_connection()
        w.cancel_search()
        w.spaces.cancel()
        w.debounce.stop()
        w.current_location = location(folder)
        # A virtual location must never fall through to a local filesystem operation.
        w.current_path = w.current_location
        tab = w.tabs_data[w.tabs.currentIndex()]
        if history_position is not None:
            tab["position"] = history_position
        if record and tab["history"][tab["position"]] != w.current_location:
            tab["history"] = tab["history"][: tab["position"] + 1] + [
                w.current_location
            ]
            tab["position"] += 1
        w.back_button.setEnabled(tab["position"] > 0)
        w.forward_button.setEnabled(tab["position"] < len(tab["history"]) - 1)
        w.search.blockSignals(True)
        w.search.clear()
        w.search.blockSignals(False)
        w.search.setPlaceholderText(tr("In diesem Drive-Ordner suchen"))
        w.source_bar.hide()
        w.preview.clear()
        w.subtitle.clear()
        self.entries.clear()
        self.model.removeRows(0, self.model.rowCount())
        w.proxy.setSourceModel(self.model)
        w.set_file_root(QModelIndex())
        w.configure_columns()
        w.heading.setTextFormat(Qt.PlainText)
        w.heading.setText("Lumen Drive")
        w.location_badge.setText("Lumen Drive")
        w.tabs.setTabText(w.tabs.currentIndex(), "Lumen Drive")
        w.path_edit.setText(w.current_location)
        w.path_stack.setCurrentWidget(w.crumbs)
        self.crumbs()
        w.activity.setText(tr("Drive wird geladen …"))
        w.update_count()
        w.session_save.start()
        for i in range(w.places.count()):
            w.places.item(i).setSelected(w.places.item(i).data(Qt.UserRole) == ROOT)

        def load(job):
            config = lumen_connect.read_config()
            profile = lumen_connect.request(config, '/bridge/me')
            if identity and (config['server'] != identity['server'] or profile['id'] != identity['account']):
                raise ValueError(tr('Dieser Drive-Verweis gehört zu einer anderen Serververbindung oder einem anderen Konto.'))
            job.check()
            return config, profile, sync.inventory(config)

        def done(value):
            if sync.scope(lumen_connect.read_config()) != sync.scope(value[0]):
                raise ValueError(tr('Serververbindung geändert. Drive neu öffnen.'))
            self.config, self.profile, self.cache = value
            if folder and (
                folder not in self.cache["folders"]
                or self.cache["folders"][folder]["trashed"]
            ):
                w.activity.setText(tr("Drive-Ordner nicht mehr verfügbar."))
                return
            self.render()
            if selected:
                from PySide6.QtCore import QItemSelectionModel
                address=next((p for p,(kind,row) in self.entries.items() if kind=='file' and row['family']==selected),None)
                if not address:raise ValueError(tr('Drive-Datei wurde verschoben. Verweis erneut öffnen.'))
                for i in range(self.model.rowCount()):
                    if self.model.item(i).data(Qt.UserRole)==address:
                        index=w.proxy.mapFromSource(self.model.index(i,0))
                        w.view.selectionModel().select(index,QItemSelectionModel.ClearAndSelect|QItemSelectionModel.Rows)
                        w.file_stack.currentWidget().scrollTo(index)
                        break
            w.activity.setText(tr("Auf dem Server"))
            w.disk_label.setText(QUrl(self.config["server"]).host() + "\nLumen Drive")

        self.work(load, done)

    def follow_reference(self, ref):
        from drive_references import resolve
        self.generation += 1
        generation = self.generation
        def done(value):
            if generation != self.generation:return
            config, rows=value;row=rows[0]
            if sync.scope(lumen_connect.read_config())!=sync.scope(config):
                raise ValueError(tr('Serververbindung geändert. Drive neu öffnen.'))
            self.navigate(location(row['folder_id'] if ref['kind']=='drive_file' else row['id']),
                          selected=ref['id'] if ref['kind']=='drive_file' else None,identity=ref['locator'])
        self.work(lambda job:resolve([ref],job),done,current=False)

    def crumbs(self):
        w = self.window
        from app import button

        parts = [("Lumen Drive", ROOT)]
        ancestors, seen, key = [], set(), self.folder
        while key:
            if key in seen or key not in self.cache["folders"]:
                break
            seen.add(key)
            row = self.cache["folders"][key]
            ancestors.append((row["name"], location(key)))
            key = row["parent_id"]
        parts += list(reversed(ancestors))
        while w.crumb_layout.count():
            item = w.crumb_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for number, (title, address) in enumerate(parts):
            if number:
                from tools_ui import label

                w.crumb_layout.addWidget(label(" › ", "muted"))
            widget = button(title, lambda _=False, p=address: w.navigate(p))
            widget.setObjectName("crumb")
            w.crumb_layout.addWidget(widget)
        w.crumb_layout.addStretch()
        w.heading.setText(parts[-1][0])
        w.tabs.setTabText(w.tabs.currentIndex(), parts[-1][0])
        w.tabs.setTabToolTip(w.tabs.currentIndex(), " / ".join(p[0] for p in parts))

    def render(self):
        w = self.window
        self.model.removeRows(0, self.model.rowCount())
        self.entries.clear()
        self.crumbs()
        query = w.search.text().casefold()
        rows = [(location(r['id']), r, 'folder')
                for r in self.cache['folders'].values()
                if not r['trashed'] and r['parent_id'] == self.folder]
        rows += [('lumen-drive:///file/' + str(UUID(r['family'])) + '/' + quote(r['name'], safe=''), r, 'file')
                 for r in self.cache['files'].values()
                 if not r['trashed'] and r['folder_id'] == self.folder]
        for address, row, kind in rows:
            self.entries[address] = (kind, row)
            if query and query not in row["name"].casefold():
                continue
            directory = kind != "file"
            items = [
                QStandardItem(v)
                for v in [
                    row["name"],
                    "" if directory else size_text(row["size"]),
                    tr("Ordner") if directory else row["mime"],
                    str(row.get("updated", ""))[:16].replace("T", " "),
                    "Lumen Drive",
                ]
            ]
            items[0].setData(address, Qt.UserRole)
            items[0].setData(directory, Qt.UserRole + 3)
            items[0].setData("Lumen Drive", Qt.UserRole + 2)
            items[1].setData(row.get("size", 0), Qt.UserRole + 1)
            items[0].setIcon(
                QIcon.fromTheme("folder-cloud" if directory else "text-x-generic")
            )
            for item in items:
                item.setEditable(False)
            self.model.appendRow(items)
        w.update_count()

    def up(self):
        parent = self.cache["folders"].get(self.folder, {}).get("parent_id")
        self.window.navigate(location(parent) if self.folder else ROOT)

    def progress(self, job):
        def report(count, total):
            job.check()
            job.progress.emit(
                tr("Drive: {0} von {1}", size_text(count), size_text(total))
            )

        return report

    @staticmethod
    def root(path):
        path = Path(path).absolute()
        if path.is_symlink():
            raise ValueError(tr("Symbolische Ordner nicht verwenden."))
        st = path.stat()
        return dict(path=str(path), identity=[st.st_dev, st.st_ino])

    def fetch(self, paths, done):
        config = dict(self.config)
        rows = [
            dict(self.entries[p][1])
            for p in paths
            if p in self.entries and self.entries[p][0] == "file"
        ]
        if len(rows) != len(paths):
            self.window.error(tr("Für ganze Ordner „Offline verfügbar“ verwenden."))
            return

        def run(job):
            result = []
            cache_dir = (
                Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
                / "lumen-drive-open"
                / sync.scope(config)
            )
            cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            for row in rows:
                job.check()
                destination = cache_dir / str(UUID(row["id"]))
                if destination.exists() and local.checksum(
                    self.root(destination), valid_name(row["name"])
                ) not in (None, row["sha256"]):
                    destination = cache_dir / uuid4().hex
                destination.mkdir(mode=0o700, exist_ok=True)
                root = self.root(destination)
                if local.checksum(root, valid_name(row["name"])) is not None:
                    result.append(str(destination / row["name"]))
                    continue
                staged = transport.download(config, root, row, self.progress(job))
                local.install(root, valid_name(row["name"]), staged, None)
                result.append(str(destination / row["name"]))
            return result

        self.work(run, done)

    def open(self, path):
        entry = self.entries.get(path)
        if not entry:
            return
        if entry[0] != "file":
            self.window.navigate(path)
            return

        def done(paths):
            QDesktopServices.openUrl(QUrl.fromLocalFile(paths[0]))
            self.window.activity.setText(
                tr(
                    "Lokale Kopie geöffnet · Änderungen bei Bedarf wieder in Drive ablegen."
                )
            )

        self.fetch([path], done)

    def preview(self, paths):
        if self.jobs:
            return
        w = self.window
        w.preview.clear()
        if len(paths) != 1 or paths[0] not in self.entries:
            return
        kind, row = self.entries[paths[0]]
        if kind != "file":
            w.preview.title.setText(row["name"])
            return

        def done(local_paths):
            if w.selected_paths() == paths:
                w.preview.show_path(local_paths[0], "Lumen Drive")

        self.fetch(paths, done)

    def copy(self, cut=False):
        paths = self.window.selected_paths()
        if not paths:
            return
        # Virtual URLs stay virtual. Local targets explicitly download them.
        mime = QMimeData()
        mime.setUrls([QUrl(p) for p in paths])
        mime.setData("application/x-kde-cutselection", b"1" if cut else b"0")
        QApplication.clipboard().setMimeData(mime)
        self.window.activity.setText(tr("Drive-Auswahl kopiert"))

    def download_into(self, config, paths, target, job):
        root = self.root(target)
        entries = resolve(config, paths)
        outputs = []
        for kind, row in entries:
            name = str(local.relative(row["name"]))
            # Never merge into an unrelated existing destination, including symlinks.
            with local.directory(root) as fd:
                try:
                    os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError(tr("Datei existiert bereits: {0}", name))
            files = [(name, row)] if kind == "file" else []
            folders = []
            if kind == "folder":
                cache = sync.inventory(config)
                paths_by_id = sync.paths(cache, row["id"])
                paths_by_id[row["id"]] = ""
                folders = [name] + [
                    name + "/" + p
                    for key, p in paths_by_id.items()
                    if p and not cache["folders"][key]["trashed"]
                ]
                for child in cache["files"].values():
                    parent = paths_by_id.get(child["folder_id"])
                    if parent is not None and not child["trashed"]:
                        files.append((str(Path(name) / parent / child["name"]), child))
            if len(files) + len(folders) > 10000:
                raise ValueError(tr("Maximal 10.000 Einträge pro Drive-Ordner."))
            # Validate before creating any destination and stream one file at a time.
            for path, item in files:
                local.relative(path)
                if item["size"] > local.LIMIT:
                    raise ValueError(tr("Ungültige Dateigröße."))
            for path in sorted(folders, key=lambda p: len(Path(p).parts)):
                job.check()
                local.mkdir(root, path)
            for path, item in files:
                job.check()
                staged = transport.download(config, root, item, self.progress(job))
                local.install(root, path, staged, None)
            outputs.append(str(Path(target) / name))
        return outputs

    def queue(self, action, paths, target, config, folder=None, previous=None):
        from transfer_panel import panel
        if not paths: return
        panel(self.window).enqueue(action, paths, target, drive=dict(scope=sync.scope(config),
                                                                  folder=folder, previous=previous or {}))

    def download(self, paths, target):
        self.queue('drive-download', paths, target, lumen_connect.read_config())

    def paste(self, mime=None, target=None):
        mime = mime if mime is not None else QApplication.clipboard().mimeData()
        if not mime:
            return is_drive(self.window.current_location)
        remote = [u.toString() for u in mime.urls() if is_drive(u.toString())]
        native = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
        if is_drive(self.window.current_location):
            if native:
                self.upload(native)
            elif remote:
                if not self.writable():
                    return True
                cut = bytes(mime.data("application/x-kde-cutselection")) == b"1"
                config, folder = dict(self.config), self.folder
                if target and is_drive(target):
                    folder = parse(target)

                if not cut:
                    self.queue('drive-copy', remote, location(folder), config, folder)
                    return True

                def run(job):
                    for kind, row in resolve(config, remote):
                        job.check()
                        if not row.get('can_write', False):
                            raise ValueError(tr('Dieser Eintrag ist nur zum Lesen freigegeben.'))
                        key = "parent_id" if kind == "folder" else "folder_id"
                        data = dict(
                            name=row["name"], revision=row["revision"], trashed=False
                        )
                        data[key] = folder
                        sync.request(
                            config,
                            ("/folders/" if kind == "folder" else "/files/")
                            + row["id"],
                            data,
                        )

                self.mutation(run)
            return True
        if remote:
            if bytes(mime.data("application/x-kde-cutselection")) == b"1":
                self.window.error(
                    tr(
                        "Beim Herunterladen bleiben die Dateien auf dem Server. Bitte Kopieren verwenden."
                    )
                )
                return True
            from file_spaces import virtual

            destination = target or (
                self.window.spaces.choose_target()
                if virtual(self.window.current_location)
                else self.window.current_path
            )
            if destination:
                self.download(remote, destination)
            return True
        return False

    def writable(self):
        if not self.config or sync.scope(lumen_connect.read_config()) != sync.scope(
            self.config
        ):
            self.window.error(tr("Serververbindung geändert. Drive neu öffnen."))
            return False
        current = self.cache['folders'].get(self.folder)
        if not (current.get('can_write', False) if current else self.profile.get('can_create', False)):
            self.window.error(tr('Dieser Ordner ist nur zum Lesen freigegeben.'))
            return False
        if self.jobs or self.window.file_job:
            self.window.activity.setText(
                tr("Bitte die laufende Drive-Übertragung abwarten.")
            )
            return False
        return True

    def mutation(self, fn):
        address = self.window.current_location
        self.work(
            fn,
            lambda _: QTimer.singleShot(
                0, lambda: self.window.navigate(address, record=False)
            ),
        )

    def upload(self, paths, folder=None):
        if not paths or not self.writable():
            return
        config = dict(self.config)
        target = self.folder if folder is None else folder
        uploads, previous = [], {}
        for path in paths:
            name = Path(path).name
            old = next(
                (
                    r
                    for r in self.cache["files"].values()
                    if not r["trashed"]
                    and r["folder_id"] == target
                    and r["name"] == name
                ),
                None,
            )
            if (
                old
                and QMessageBox.question(
                    self.window,
                    "Lumen Drive",
                    tr("„{0}“ als neue Version speichern?", name),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                != QMessageBox.Yes
            ):
                continue
            uploads.append(path)
            previous[path] = old
        self.queue('drive-upload', uploads, location(target), config, target, previous)

    def mkdir(self):
        if not self.writable():
            return
        name, ok = QInputDialog.getText(
            self.window, tr("Neuer Ordner"), tr("Name des Ordners:")
        )
        if not ok or not name:
            return
        config, folder = dict(self.config), self.folder
        self.mutation(
            lambda _: sync.request(
                config,
                "/folders",
                dict(id=str(uuid4()), name=valid_name(name), parent_id=folder),
            )
        )

    def edit(self, paths, *, name=None, trash=False, folder=None, move=False):
        if not self.writable():
            return
        config = dict(self.config)
        entries = [self.entries[p] for p in paths if p in self.entries]

        def run(job):
            for kind, row in entries:
                job.check()
                if not row.get("can_write", False):
                    raise ValueError(tr("Dieser Eintrag ist nur zum Lesen freigegeben."))
                data = dict(
                    name=name or row["name"], revision=row["revision"], trashed=trash
                )
                key = "parent_id" if kind == "folder" else "folder_id"
                data[key] = folder if move else row[key]
                sync.request(
                    config,
                    ("/folders/" if kind == "folder" else "/files/") + row["id"],
                    data,
                )

        self.mutation(run)

    def rename(self):
        paths = self.window.selected_paths()
        if len(paths) != 1 or paths[0] not in self.entries:
            return
        name, ok = QInputDialog.getText(
            self.window,
            tr("Umbenennen"),
            tr("Neuer Name:"),
            text=self.entries[paths[0]][1]["name"],
        )
        if ok and name:
            self.edit(paths, name=name)

    def trash(self):
        paths = self.window.selected_paths()
        if (
            paths
            and QMessageBox.question(
                self.window,
                tr("In den Papierkorb"),
                tr(
                    "{0} ausgewählte Einträge in den Papierkorb verschieben?",
                    len(paths),
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        ):
            self.edit(paths, trash=True)

    def settings(self, offline=False):
        from drive_ui import show

        folder = self.folder
        paths = self.window.selected_paths()
        if len(paths) == 1 and self.entries.get(paths[0], ("file",))[0] != "file":
            folder = parse(paths[0])
        show(self.window, folder=folder, offline=offline)

    def context_menu(self, position):
        from PySide6.QtCore import QItemSelectionModel

        w = self.window
        view = w.file_stack.currentWidget()
        index = view.indexAt(position)
        if index.isValid() and not w.view.selectionModel().isSelected(index):
            w.view.selectionModel().select(
                index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
            )
        paths = w.selected_paths() if index.isValid() else []
        menu = self.build_context_menu(paths)
        try:
            menu.exec(view.viewport().mapToGlobal(position))
        finally:
            menu.deleteLater()

    def build_context_menu(self, paths):
        return self.window.build_context_menu(paths)
