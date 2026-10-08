"""One local overview of explicitly configured notebook, project and Drive sync."""

import json
import os
from pathlib import Path
from lumen_i18n import tr


def snapshot():
    from lumen_store import Store
    from drive_sync import read

    store = Store()
    notes = [
        json.loads(row["value"])
        for row in store.rows("SELECT value FROM settings WHERE key LIKE 'knowledge/server-sync/%'")
    ]
    tools = Path(
        os.environ.get(
            "LUMEN_TOOLS_DATA",
            Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "lumen-tools",
        )
    )
    try:
        projects = json.loads((tools / "workbench/server-sync.json").read_text())
    except FileNotFoundError:
        projects = {}
    roots = read()["roots"]
    return dict(
        notes=dict(enabled=sum(bool(n.get("enabled")) for n in notes)),
        projects=dict(
            enabled=bool(projects.get("enabled")),
            count=len(projects.get("projects", {})),
            conflicts=len(projects.get("conflicts", {})),
            last_sync=projects.get("last_sync"),
        ),
        drive=[
            dict(
                id=r["id"],
                name=Path(r["path"]).name,
                enabled=r["enabled"],
                status=r.get("status", ""),
                conflicts=len(r.get("conflicts", {})),
                skipped=len(r.get("errors", [])),
                last_sync=r.get("last_sync"),
            )
            for r in roots
        ],
    )


def widget(parent):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QWidget, QVBoxLayout
    from tools_ui import label, button
    from lumen_apps import launch

    page = QWidget(parent)
    layout = QVBoxLayout(page)
    layout.addWidget(label(tr("Einmal verbinden, danach automatisch"), "heading"))
    layout.addWidget(
        label(
            tr("Nur ausdrücklich ausgewählte Daten werden abgeglichen. Pausieren behält vorhandene Kopien.")
        )
    )
    status = label("")
    layout.addWidget(status)

    def refresh():
        try:
            data = snapshot()
            status.setText(
                tr("Notizbücher: {0}", data["notes"]["enabled"])
                + "\n"
                + tr(
                    "Projekte: {0} · Konflikte: {1}", data["projects"]["count"], data["projects"]["conflicts"]
                )
                + "\n"
                + "\n".join(
                    r["name"] + " · " + (r["status"] if r["enabled"] else tr("Pausiert"))
                    for r in data["drive"]
                )
            )
        except Exception as error:
            status.setText(str(error))

    layout.addWidget(button(tr("Notizen einrichten"), lambda: launch("wissen"), "accessories-text-editor"))
    layout.addWidget(button(tr("Projekte einrichten"), lambda: launch("workbench"), "folder-development"))

    def drive():
        from drive_ui import show

        show(page)

    layout.addWidget(button(tr("Drive-Ordner einrichten"), drive, "folder-cloud"))
    layout.addStretch()
    page.timer = QTimer(page)
    page.timer.setInterval(5000)
    page.timer.timeout.connect(refresh)
    page.timer.start()
    refresh()
    return page
