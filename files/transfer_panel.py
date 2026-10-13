"""Toggleable native transfer view over the shared durable ticket store."""

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QLabel,
    QProgressBar,
    QPushButton,
    QMessageBox,
)

from core import size_text
from lumen_i18n import tr
from lumen_store import Store
import lumen_transfers as transfers

NAMES = {
    "copy": tr("Kopieren"),
    "move": tr("Verschieben"),
    "rename": tr("Umbenennen"),
    "mkdir": tr("Neuer Ordner"),
    "trash": tr("Papierkorb"),
    "download": tr("Download"),
    "drive-upload": tr("Drive · Hochladen"),
    "drive-download": tr("Drive · Herunterladen"),
    "drive-copy": tr("Drive · Kopieren"),
}
CONTROLLABLE = {"copy", "download", "drive-upload", "drive-download", "drive-copy"}


class Transfers(QDockWidget):
    def __init__(self, window):
        super().__init__(tr("Lumen Übertragungen"), window)
        self.setObjectName("lumenTransfers")
        self.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.RightDockWidgetArea)
        self.window, self.store = window, Store()
        self.values, self.previous, self.samples = {}, {}, {}
        body = QWidget()
        layout = QVBoxLayout(body)
        self.list = QTreeWidget()
        self.list.setHeaderLabels(
            [tr("Vorgang / Datei"), tr("Fortschritt"), tr("Status"), tr("Ziel")]
        )
        self.list.setRootIsDecorated(False)
        self.list.setAlternatingRowColors(True)
        self.list.setMinimumHeight(100)
        self.list.setColumnWidth(0, 270)
        self.list.setColumnWidth(1, 190)
        layout.addWidget(self.list)
        self.detail = QLabel()
        self.detail.setTextFormat(Qt.PlainText)
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.detail)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        self.pause = QPushButton(tr("Pausieren"))
        self.resume = QPushButton(tr("Fortsetzen"))
        self.cancel = QPushButton(tr("Abbrechen"))
        self.open = QPushButton(tr("Ziel öffnen"))
        self.clear = QPushButton(tr("Fertige ausblenden"))
        for button in (self.pause, self.resume, self.cancel, self.open, self.clear):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.setWidget(body)
        self.pause.clicked.connect(lambda: self.control(transfers.pause))
        self.resume.clicked.connect(lambda: self.control(transfers.retry))
        self.cancel.clicked.connect(self.abort)
        self.open.clicked.connect(self.open_target)
        self.clear.clicked.connect(self.dismiss)
        self.list.itemSelectionChanged.connect(self.details)
        window.addDockWidget(Qt.BottomDockWidgetArea, self)
        self.hide()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(750)
        self.refresh()

    def selected(self):
        item = self.list.currentItem()
        return self.values.get(item.data(0, Qt.UserRole)) if item else None

    def refresh(self):
        chosen = self.selected()
        identity = chosen["id"] if chosen else None
        try:
            values = transfers.tickets(self.store)
        except Exception as error:
            self.detail.setText(str(error))
            return
        self.values = {v["id"]: v for v in values}
        scroll = self.list.verticalScrollBar().value()
        self.list.blockSignals(True)
        self.list.clear()
        completed = False
        for value in values[:200]:
            key, state = value["id"], value["status"]
            if state == "completed" and self.previous.get(key) in transfers.ACTIVE:
                completed = True
            self.previous[key] = state
            name = value["current"] or value["sources"][0]
            total = value["total"]
            amount = size_text(value["bytes"]) + (
                " / " + size_text(total) if total else ""
            )
            status = (
                tr("Wird abgebrochen")
                if value.get("discard") and state in transfers.ACTIVE
                else tr("Wird angehalten")
                if value.get("cancel") and state in transfers.ACTIVE
                else transfers.LABELS.get(state, state)
            )
            item = QTreeWidgetItem(
                [
                    NAMES.get(value["action"], value["action"])
                    + " · "
                    + Path(name).name,
                    amount,
                    status,
                    value["target"] or "",
                ]
            )
            item.setData(0, Qt.UserRole, key)
            item.setToolTip(0, name)
            item.setToolTip(3, value["target"] or "")
            self.list.addTopLevelItem(item)
            if key == identity:
                self.list.setCurrentItem(item)
        if not self.list.currentItem() and self.list.topLevelItemCount():
            self.list.setCurrentItem(self.list.topLevelItem(0))
        self.list.verticalScrollBar().setValue(scroll)
        self.list.blockSignals(False)
        self.details()
        if completed:
            self.window.refresh()

    def details(self):
        value = self.selected()
        active = bool(value and value["status"] in transfers.ACTIVE)
        allowed = bool(value and value["action"] in CONTROLLABLE)
        self.pause.setEnabled(allowed and active and not value.get("cancel"))
        self.resume.setEnabled(allowed and value["status"] in ("paused", "failed"))
        self.cancel.setEnabled(
            allowed
            and value["status"] not in ("completed", "cancelled")
            and not value.get("discard")
        )
        self.open.setEnabled(bool(value and value["target"]))
        if not value:
            self.detail.setText(
                tr(
                    "Keine Übertragungen. Kopiere Dateien wie gewohnt mit Strg+C und Strg+V."
                )
            )
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            return
        key, now = value["id"], time.monotonic()
        previous = self.samples.get(key)
        speed = ""
        if (
            previous
            and active
            and now - previous[0] >= 0.5
            and value["bytes"] > previous[1]
        ):
            rate = (value["bytes"] - previous[1]) / (now - previous[0])
            remaining = (
                max(0, value["total"] - value["bytes"]) / rate
                if value["total"]
                else None
            )
            speed = " · " + size_text(int(rate)) + "/s"
            if remaining is not None:
                speed += tr(" · noch etwa {0} s", round(remaining))
        if not previous or now - previous[0] >= 0.5:
            self.samples[key] = (now, value["bytes"])
        self.detail.setText(
            "\n".join(value["sources"])
            + "\n→ "
            + str(value["target"] or "")
            + speed
            + ("\n" + "\n".join(value["errors"]) if value["errors"] else "")
        )
        self.progress.setRange(0, 0 if active and not value["total"] else 100)
        self.progress.setValue(
            100
            if value["status"] == "completed"
            else min(100, round(100 * value["bytes"] / value["total"]))
            if value["total"]
            else 0
        )

    def control(self, action):
        value = self.selected()
        if not value:
            return
        try:
            action(self.store, value["id"])
        except Exception as error:
            self.window.error(str(error))
        self.refresh()

    def abort(self):
        if (
            QMessageBox.question(
                self,
                tr("Lumen Übertragung abbrechen"),
                tr(
                    "Unvollständige Kopien entfernen? Bereits fertig kopierte Dateien bleiben erhalten."
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        ):
            self.control(transfers.cancel)

    def open_target(self):
        value = self.selected()
        if not value:
            return
        if str(value["target"]).startswith("lumen-drive://"):
            self.window.navigate(value["target"])
        else:
            path = Path(value["target"])
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(
                    str(path.parent if value["action"] == "download" else path)
                )
            )

    def dismiss(self):
        with self.store.connect() as db:
            for value in self.values.values():
                if value["status"] in ("completed", "cancelled"):
                    db.execute(
                        "DELETE FROM settings WHERE key=?",
                        (transfers.PREFIX + value["id"],),
                    )
        self.refresh()

    def enqueue(self, action, paths, target=None, drive=None, portable=False):
        value = transfers.create(
            self.store,
            action,
            list(map(str, paths)),
            str(target) if target else None,
            portable,
            drive=drive,
        )
        transfers.start(self.store, value)
        self.show()
        self.raise_()
        self.refresh()
        return value


def panel(window):
    if not hasattr(window, "transfer_panel"):
        window.transfer_panel = Transfers(window)
    return window.transfer_panel


def toggle(window):
    view = panel(window)
    view.setVisible(not view.isVisible())
    if view.isVisible():
        view.raise_()
