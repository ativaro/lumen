"""Small native controls for the existing server connection and project sync."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QDialogButtonBox,
    QCheckBox,
    QLabel,
    QMessageBox,
    QComboBox,
    QInputDialog,
)
from tools_ui import button, Job
from lumen_i18n import tr
import projects_sync as sync


def configure(window):
    window.save()

    def loaded(info):
        dialog = QDialog(window)
        dialog.setWindowTitle(tr("Lumen Projekte · Serverabgleich"))
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(info["server"]))
        enabled = QCheckBox(tr("Meine Serverprojekte synchronisieren"))
        enabled.setChecked(info["enabled"])
        layout.addWidget(enabled)
        message = QLabel(
            tr(
                "Neue eigene Serverprojekte erscheinen hier automatisch. Lokale Projekte bleiben lokal, bis du sie verbindest."
            )
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        bind = QCheckBox(tr("Ausgewähltes lokales Projekt verbinden"))
        bind.setEnabled(bool(window.current))
        layout.addWidget(bind)
        shared = QComboBox()
        shared.setAccessibleName(tr("Geteiltes Serverprojekt"))
        shared.addItem(tr("Kein zusätzliches Projekt"), None)
        for space in info.get("spaces", []):
            if not space["owned"] or space["private"]:
                shared.addItem(space["title"], space["id"])
        layout.addWidget(shared)
        if not info["allowed"]:
            layout.addWidget(QLabel(tr("Auf dem Server zuerst „Projekte synchronisieren“ freigeben.")))
        controls = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        layout.addWidget(controls)
        controls.rejected.connect(dialog.reject)

        def save():
            if enabled.isChecked() and not info["allowed"]:
                return
            sync.configure(
                window.library,
                enabled.isChecked(),
                window.current if bind.isChecked() else None,
                shared.currentData(),
            )
            dialog.accept()
            QTimer.singleShot(0, lambda: run(window))

        controls.accepted.connect(lambda: window.safe(save))
        window.sync_dialog = dialog
        dialog.show()

    window.work(tr("Serververbindung prüfen …"), lambda job: sync.info(window.library), loaded)


def run(window):
    if window.editor.dirty() or window.editor.draft_kind:return
    if window.job or window.save_timer.isActive() or (window.runner and window.runner.busy):
        return
    if not sync.read_state(window.library)["enabled"]:
        return
    if getattr(window, "project_sync_job", None):
        return
    window.save()
    job = Job(lambda _: sync.synchronize(window.library), window)
    window.project_sync_job = job

    def done(result):
        window.refresh()
        # Never reload over a draft typed while the worker was in flight.
        if (
            window.current
            and not window.editor.draft_kind
            and not window.editor.dirty()
            and not window.save_timer.isActive()
            and window.editor_fields() == window.loaded_fields
        ):
            window.loading = True
            try:
                window.load_fields(
                    window.projects.get(window.scope) if window.scope else window.library.get(window.current)
                )
                window.refresh_tasks()
            finally:
                window.loading = False
        window.status.setText(
            tr("Projektabgleich abgeschlossen")
            if not result["conflicts"]
            else tr("Projektkonflikte vorhanden · Über Serverabgleich prüfen")
        )

    job.result.connect(lambda result: window.safe(done, result))
    job.failed.connect(lambda message: window.status.setText(tr("Projektabgleich: ") + message))

    def finished():
        window.project_sync_job = None
        job.deleteLater()
        if getattr(window, "sync_close_requested", False):
            window.close()

    job.finished.connect(finished)
    job.start()


def conflicts(window):
    state = sync.read_state(window.library)
    entries = state.get("conflicts", {})
    if not entries:
        QMessageBox.information(window, tr("Lumen Projekte"), tr("Keine Projektkonflikte."))
        return
    keys = list(entries)
    labels = [entries[key]["title"] + " · " + key[:8] for key in keys]
    selected, ok = QInputDialog.getItem(
        window, tr("Lumen Projekte · Konflikt"), tr("Eintrag"), labels, 0, False
    )
    if not ok:
        return
    key = keys[labels.index(selected)]
    entry = entries[key]
    dialog = QMessageBox(window)
    dialog.setWindowTitle(tr("Lumen Projekte · Beide Fassungen erhalten"))
    dialog.setText(entry["title"])
    dialog.setInformativeText(tr("Welche Fassung soll weiterverwendet werden?"))
    import json

    dialog.setDetailedText(
        tr("Lokal")
        + "\n"
        + json.dumps(entry["local"], ensure_ascii=False, indent=2)
        + "\n\nServer\n"
        + json.dumps(entry["server"], ensure_ascii=False, indent=2)
    )
    local = dialog.addButton(tr("Lokale Fassung"), QMessageBox.AcceptRole)
    remote = dialog.addButton(tr("Serverfassung"), QMessageBox.DestructiveRole)
    dialog.addButton(QMessageBox.Cancel)
    dialog.exec()
    if dialog.clickedButton() in (local, remote):
        window.save()
        sync.resolve(window.library, key, dialog.clickedButton() == local)
        run(window)


def install(window):
    for index,(title,action,icon) in enumerate([
        ('Serverabgleich …',configure,'network-server'),('Jetzt abgleichen',run,'view-refresh'),
        ('Konflikte',conflicts,'dialog-warning'),('Serveraufträge …',server_workspace,'network-server'),
        ('Auf Server öffnen',open_server,'globe')]):
        window.content.insertWidget(index,button(tr(title),lambda _=False,fn=action:window.safe(fn,window),icon))
    window.project_sync_timer = QTimer(window)
    window.project_sync_timer.setInterval(60000)
    window.project_sync_timer.timeout.connect(lambda: window.safe(run, window))
    window.project_sync_timer.start()


def open_server(window):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    from urllib.parse import urlencode

    state = sync.read_state(window.library)
    binding = state["projects"].get(window.current)
    if not binding:
        return
    config = sync.lumen_connect.read_config()
    QDesktopServices.openUrl(
        QUrl(config["server"] + "/?" + urlencode(dict(app="projects", workspace=binding["remote"])))
    )


def server_workspace(window):
    from server_workspace import ServerWorkspace
    state = sync.read_state(window.library)
    config = sync.lumen_connect.read_config()
    if state.get('scope') != sync.scope(config):
        raise ValueError(tr('Serverkonto geändert. Zuerst Serverabgleich prüfen.'))
    binding = state['projects'].get(window.current)
    if not binding:
        raise ValueError(tr('Dieses Projekt zuerst über Serverabgleich verbinden.'))
    dialog = QDialog(window); dialog.setWindowTitle(tr('Lumen Serveraufträge')); dialog.resize(1050,750)
    box = QVBoxLayout(dialog); box.addWidget(ServerWorkspace(dialog, binding['remote']))
    window.server_workspace_dialog = dialog; dialog.show()
