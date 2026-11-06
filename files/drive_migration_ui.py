"""Review a concrete folder assignment before changing an old Drive binding."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QCheckBox,
    QGridLayout,
)
from desktop_design import AppHeader, PAGE_MARGIN, PAGE_SPACING
from tools_ui import button, Job
from lumen_i18n import tr
import drive_binding_migration as migration
import drive_sync as sync


class Migration(QDialog):
    def __init__(self, parent, root):
        super().__init__(parent)
        self.setWindowTitle(tr("Lumen Drive · Ordner zuordnen"))
        self.resize(760, 650)
        self.root = root
        self.job = None
        self.proposal = None
        self.completed = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN)
        layout.setSpacing(PAGE_SPACING)
        layout.addWidget(AppHeader("Lumen Drive", tr("Ordner zuordnen …")))
        info = QLabel(tr("Lokaler Ordner bleibt erhalten:") + "\n" + root["path"])
        info.setTextFormat(Qt.PlainText)
        info.setWordWrap(True)
        layout.addWidget(info)
        self.mode = QComboBox()
        self.mode.addItems(
            [
                tr("Neuen Zielordner anlegen"),
                tr("Leeren Zielordner verwenden"),
                tr("Zuordnung eines anderen Geräts übernehmen"),
            ]
        )
        self.mode.setAccessibleName(tr("Art der Zuordnung"))
        layout.addWidget(self.mode)
        self.name = QLineEdit("Lumen Drive")
        self.name.setAccessibleName(tr("Name des neuen Zielordners"))
        layout.addWidget(self.name)
        self.folder = QComboBox()
        self.folder.setAccessibleName(tr("Vorhandener Zielordner"))
        self.folder_paths = sync.paths(parent.cache, None)
        for key, row in parent.cache["folders"].items():
            if not row["trashed"] and row.get("can_write"):
                self.folder.addItem(self.folder_paths.get(key) or row["name"], key)
                self.folder.setItemData(self.folder.count() - 1, key, Qt.ToolTipRole)
        layout.addWidget(self.folder)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName(tr("Vorschau der Umstellung"))
        layout.addWidget(self.details, 1)
        self.technical = QCheckBox(tr("Technische Kennungen anzeigen"))
        self.technical.toggled.connect(lambda _: self.present(self.proposal) if self.proposal else None)
        layout.addWidget(self.technical)
        self.status = QLabel(
            tr(
                "Zuerst Ziel wählen und Vorschau prüfen. Die aufgeführten Serverdateien werden in diesen Ordner verschoben. Inhalte und Freigaben bleiben erhalten."
            )
        )
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        actions = QGridLayout()
        actions.setSpacing(8)
        layout.addLayout(actions)
        self.inspect = button(tr("Vorschau prüfen"), self.preview)
        actions.addWidget(self.inspect, 0, 0)
        self.finish = button(tr("Original-Uploads abschließen"), self.finish_uploads)
        actions.addWidget(self.finish, 0, 1)
        self.finish.setVisible(False)
        self.commit = button(tr("Gezeigte Zuordnung bestätigen"), self.apply, primary=True)
        actions.addWidget(self.commit, 1, 0, 1, 2)
        self.commit.setEnabled(False)
        self.abort = button(tr("Begonnene Umstellung sicher abbrechen"), self.cancel)
        layout.addWidget(self.abort)
        self.close_button = button(tr("Schließen"), self.reject)
        layout.addWidget(self.close_button)
        self.mode.currentIndexChanged.connect(self.invalidate)
        self.name.textChanged.connect(self.invalidate)
        self.folder.currentIndexChanged.connect(self.invalidate)
        self.invalidate()
        journal = root.get("migration")
        self.abort.setVisible(bool(journal))
        if journal:
            self.details.setPlainText(
                tr("Bestätigte Umstellung fortsetzen:")
                + "\n"
                + (
                    journal["plan"].get("new_name")
                    or self.folder_paths.get(journal["plan"]["folder"])
                    or tr("Bestätigter Zielordner")
                )
                + "\n"
                + tr("Dateien:")
                + " "
                + str(len(journal["plan"]["files"]))
                + "\n"
                + tr("Übertragungen:")
                + " "
                + str(len(journal["plan"]["uploads"]))
            )
            self.commit.setText(tr("Bestätigte Umstellung fortsetzen"))
            self.commit.setEnabled(True)
            self.inspect.setEnabled(False)
            for widget in (self.mode, self.name, self.folder):
                widget.setEnabled(False)

    def invalidate(self, *_):
        self.proposal = None
        self.commit.setEnabled(False)
        self.finish.setVisible(False)
        self.name.setVisible(self.mode.currentIndex() == 0)
        self.folder.setVisible(self.mode.currentIndex() != 0)
        self.details.clear()

    def run(self, fn, done):
        if self.job:
            return
        self.job = Job(fn, self)
        self.setEnabled(False)
        self.job.progress.connect(self.status.setText)
        self.job.result.connect(done)
        self.job.failed.connect(self.failed)
        self.job.finished.connect(self.job_finished)
        self.job.start()

    def job_finished(self):
        job = self.job
        self.job = None
        job.deleteLater()
        self.setEnabled(True)
        # An uncertain apply has a durable journal; expose recovery immediately.
        self.root = next(r for r in sync.read()["roots"] if r["id"] == self.root["id"])
        if self.completed:
            self.accept()
            return
        if self.root.get("migration"):
            self.abort.setVisible(True)
            self.commit.setEnabled(True)
            self.commit.setText(tr("Bestätigte Umstellung fortsetzen"))
            self.inspect.setEnabled(False)
            for widget in (self.mode, self.name, self.folder):
                widget.setEnabled(False)

    def failed(self, message):
        self.status.setText(message)

    def preview(self):
        mode = self.mode.currentIndex()
        folder = self.folder.currentData() if mode else None
        name = self.name.text().strip() if not mode else None
        if (not mode and not name) or (mode and not folder):
            self.status.setText(tr("Bitte einen Zielordner wählen."))
            return
        self.run(lambda _: migration.preview(self.root["id"], folder, name, mode == 2), self.present)

    def present(self, proposal):
        self.proposal = proposal
        view = proposal["preview"]
        show_ids = self.technical.isChecked()
        folder = view["folder"]
        target_path = self.folder_paths.get(folder["id"]) or folder["name"]
        paths = sync.paths(
            {"folders": {r["id"]: r for r in view["folders"]}}, folder["id"] if view.get("adopt") else None
        )
        root_paths = sync.paths({"folders": {r["id"]: r for r in view["folders"]}}, None)
        paths = {k: v if v is not None else root_paths.get(k) for k, v in paths.items()}
        moving = view.get("moving", {})
        moves = {
            kind: set(moving.get(kind, [] if view.get("adopt") else [r["id"] for r in view[kind]]))
            for kind in ("files", "folders")
        }
        lines = [tr("Ziel:") + " " + target_path + (" · " + str(folder["id"]) if show_ids else "")]
        if view.get("adopt"):
            lines.append(
                tr(
                    "Vorhandene Zuordnungen bleiben erhalten. Nur die unten als Verschiebung aufgeführten Originale ändern ihren Serverordner."
                )
                if any(moves.values())
                else tr("Bestehende Zuordnung übernehmen, ohne Serverdateien zu verschieben.")
            )
        for moved, heading in [
            (False, tr("Bleibt unverändert im Zielordner:")),
            (True, tr("Wird in den gewählten Zielordner verschoben:")),
        ]:
            rows = [
                (kind, row)
                for kind in ("folders", "files")
                for row in view[kind]
                if (row["id"] in moves[kind]) == moved
            ]
            if not rows:
                continue
            lines.extend(["", heading])
            for kind, row in rows:
                if kind == "folders":
                    name = (paths.get(row["id"]) or row["name"]) + "/"
                else:
                    parent = paths.get(row.get("folder_id"))
                    name = (parent + "/" if parent else "") + row["name"]
                lines.append(name + (" · " + str(row["id"]) if show_ids else ""))
        labels = {
            "not_started": tr("Wartet – wird in den gewählten Ordner übertragen"),
            "uploading": tr("Original-Upload noch offen"),
            "completed": tr("Original-Upload bestätigt"),
        }
        if view["uploads"]:
            lines.extend(["", tr("Warteschlange:")])
            for item in view["uploads"]:
                name = next(
                    u["body"]["name"]
                    for u in proposal["plan"]["uploads"]
                    if u["request_id"] == item["request_id"]
                )
                lines.append(
                    name + " · " + labels[item["state"]] + (" · " + item["request_id"] if show_ids else "")
                )
                if item.get("replacement_revision"):
                    lines.append(
                        tr("Nur die nachgewiesene Ordnerrevision wird aktualisiert:")
                        + " "
                        + str(item["replacement_revision"])
                    )
        self.details.setPlainText("\n".join(lines))
        self.commit.setEnabled(view["ready"])
        self.finish.setVisible(not view["ready"])
        self.status.setText(
            tr("Die Bestätigung gilt nur für diese Vorschau. Änderungen erfordern eine neue Prüfung.")
            if view["ready"]
            else tr("Offene Original-Uploads zuerst abschließen, danach Vorschau erneut prüfen.")
        )

    def finish_uploads(self):
        if not self.proposal:
            return
        self.run(
            lambda job: migration.finish_uploads(
                self.root["id"],
                self.proposal,
                lambda n, total: (job.check(), job.progress.emit(f"{n} / {total}")),
            ),
            lambda _: self.invalidate(),
        )

    def apply(self):
        if not self.root.get("migration") and not self.proposal:
            return
        self.run(
            lambda _: migration.apply(self.root["id"], self.proposal),
            lambda _: setattr(self, "completed", True),
        )

    def cancel(self):
        self.run(lambda _: migration.cancel(self.root["id"]), lambda _: setattr(self, "completed", True))

    def reject(self):
        if not self.job:
            super().reject()

    def closeEvent(self, event):
        if self.job:
            event.ignore()
        else:
            event.accept()
