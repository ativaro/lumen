"""Project environment fields embedded in the dedicated project sidebar."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QAbstractItemView,
    QHeaderView, QListWidget, QListWidgetItem, QPlainTextEdit, QTableWidgetItem, QFileDialog, QDialog)
from lumen_i18n import tr
from lumen_workplace import text, table, row
from network import ConnectDialog, server_label
import lumen_projects as projects


class ProjectEnvironment(QWidget):
    def __init__(self, store, project, parent):
        super().__init__(parent)
        self.store, self.project, self.saved = store, project, None
        value = project or {}; layout = QVBoxLayout(self); layout.setSpacing(14)
        tabs = QTabWidget(); layout.addWidget(tabs)
        sources = QWidget(); sources_box = QVBoxLayout(sources)
        sources_box.addWidget(text(tr('Lokale Ordner und NAS gehören zusammen. Jede Datei behält ihre Herkunft.'), 'muted'))
        self.sources = table([tr('Bezeichnung'), tr('Ordner oder Netzwerkadresse')])
        self.sources.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.sources.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.sources.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        sources_box.addWidget(self.sources)
        for source in value.get('sources', []): self.add_source(source['label'], source['location'])
        row(sources_box, [(tr('Ordner …'), self.local), (tr('Netzwerk …'), self.remote), (tr('Entfernen'), self.remove_source)])
        tabs.addTab(sources, tr('Dateiquellen'))
        launch = QWidget(); launch_box = QVBoxLayout(launch)
        launch_box.addWidget(text(tr('Diese Programme und Webseiten werden nur beim Klick auf „Arbeitsstand laden“ geöffnet.'), 'muted'))
        self.apps = QListWidget(); self.apps.setAccessibleName(tr('Programme beim Laden des Arbeitsstands'))
        from gi.repository import Gio
        apps = sorted([a for a in Gio.AppInfo.get_all() if a.should_show() and a.get_id()], key=lambda a: a.get_display_name().casefold())
        selected = value.get('applications', [])
        for app in apps:
            item = QListWidgetItem(QIcon.fromTheme(app.get_icon().to_string()) if app.get_icon() else QIcon(), app.get_display_name())
            item.setData(Qt.UserRole, app.get_id()); item.setCheckState(Qt.Checked if app.get_id() in selected else Qt.Unchecked)
            self.apps.addItem(item)
        launch_box.addWidget(self.apps)
        self.urls = QPlainTextEdit('\n'.join(value.get('urls', []))); self.urls.setMaximumHeight(100)
        self.urls.setPlaceholderText(tr('Webseiten · eine HTTP(S)-Adresse pro Zeile')); self.urls.setAccessibleName(tr('Webseiten'))
        launch_box.addWidget(self.urls); tabs.addTab(launch, tr('Beim Fortsetzen öffnen'))
        self.original = self.fields()

    def add_source(self, label, location):
        r = self.sources.rowCount(); self.sources.insertRow(r)
        self.sources.setItem(r, 0, QTableWidgetItem(label)); self.sources.setItem(r, 1, QTableWidgetItem(location))

    def local(self):
        path = QFileDialog.getExistingDirectory(self, tr('Projektordner wählen'))
        if path: self.add_source(Path(path).name, path)

    def remote(self):
        dialog = ConnectDialog(self)
        if dialog.exec() == QDialog.Accepted: self.add_source(server_label(dialog.url), dialog.url)
        dialog.deleteLater()

    def remove_source(self):
        if self.sources.currentRow() >= 0: self.sources.removeRow(self.sources.currentRow())

    def fields(self):
        sources = [dict(label=self.sources.item(r, 0).text() if self.sources.item(r, 0) else '',
                        location=self.sources.item(r, 1).text() if self.sources.item(r, 1) else '')
                   for r in range(self.sources.rowCount())]
        known = {self.apps.item(i).data(Qt.UserRole) for i in range(self.apps.count())}
        apps = [self.apps.item(i).data(Qt.UserRole) for i in range(self.apps.count())
                if self.apps.item(i).checkState() == Qt.Checked]
        apps += [app for app in self.project.get('applications', []) if app not in known]
        return dict(sources=sources, applications=apps,
                    urls=[url.strip() for url in self.urls.toPlainText().splitlines() if url.strip()])

    def dirty(self):
        return self.fields() != self.original

    def save(self):
        if not self.dirty():return
        fields=self.fields()
        self.saved = projects.save_project(self.store, self.project, self.project['name'],
            fields['sources'], fields['applications'], fields['urls'], self.project.get('note',''))
        self.project=self.saved;self.original=self.fields()
