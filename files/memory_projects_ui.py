"""Native explicit project/folder mapping and private memory copies."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QComboBox, QLineEdit,
                              QFileDialog, QDialogButtonBox, QCheckBox)
from lumen_i18n import tr
from lumen_memory import worker
from tools_ui import label, button, row


def configure(window, copy=False):
    if window.job or window.poller:
        return
    if window.dirty:
        window.save_note(lambda: configure(window, copy))
        return
    note = window.doc if copy and window.area == 'lumen' else None
    if copy and not note:
        return
    window.work(tr('Projektzuordnung laden …'),
                lambda job: worker(job, window.store, 'project_info'),
                lambda info: setattr(window, 'after_job', lambda: show(window, info, note)))


def show(window, info, note=None):
    dialog = QDialog(window)
    dialog.setWindowTitle(tr('Lumen Gedächtnis · Projektwissen'))
    dialog.setWindowModality(Qt.WindowModal)
    dialog.resize(600, 400)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(14)
    layout.addWidget(label(tr('Ein Projekt, ein Gedächtnis'), 'heading'))
    layout.addWidget(label(tr('Wähle den lokalen Arbeitsordner eines bestehenden Projekts. Neue projektbezogene Erinnerungen gehören dann dauerhaft zu diesem Projekt – auch wenn du den Ordner hier später wechselst.'), 'muted'))
    layout.addWidget(label(tr('Projektwissen bleibt vorerst privat auf diesem Desktop. Diese Zuordnung gibt nichts auf Lumen Server oder für andere Personen frei.'), 'muted'))
    project = QComboBox()
    project.setAccessibleName(tr('Projekt'))
    for item in info['projects']:
        project.addItem(item['title'], item['id'])
    layout.addWidget(label(tr('Projekt')))
    layout.addWidget(project)
    folder = QLineEdit()
    folder.setReadOnly(True)
    folder.setAccessibleName(tr('Lokaler Projektordner'))
    folder.setPlaceholderText(tr('Noch kein Ordner zugeordnet'))
    def choose():
        selected = QFileDialog.getExistingDirectory(dialog, tr('Lumen · Projektordner wählen'), folder.text())
        if selected:
            folder.setText(selected)
    layout.addWidget(label(tr('Lokaler Projektordner')))
    layout.addWidget(row(folder, button(tr('Wählen …'), choose, 'folder')))
    clear = button(tr('Zuordnung entfernen'), folder.clear)
    clear.setToolTip(tr('Die Erinnerungen bleiben erhalten und werden ohne Zuordnung nicht als Projektkontext verwendet.'))
    layout.addWidget(clear)
    copying = QCheckBox(tr('Ausgewählte Erinnerung als Projektkopie übernehmen'))
    copying.setChecked(bool(note))
    copying.setVisible(bool(note))
    layout.addWidget(copying)
    if note:
        layout.addWidget(label(tr('„{0}“ bleibt unverändert. Die neue Kopie ist zunächst nicht für Lumen freigegeben.', note['title']), 'muted'))
    if not info['projects']:
        layout.addWidget(label(tr('Lege zuerst ein Projekt in Lumen Projekte an.'), 'muted'))
    actions = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    actions.button(QDialogButtonBox.Save).setText(tr('Übernehmen'))
    actions.rejected.connect(dialog.reject)
    def valid():
        actions.button(QDialogButtonBox.Save).setEnabled(bool(project.currentData()) and (not copying.isChecked() or bool(folder.text())))
    def select(index):
        folder.setText(info['folders'].get(project.currentData(), ''))
        valid()
    project.currentIndexChanged.connect(select)
    folder.textChanged.connect(valid)
    copying.toggled.connect(valid)
    select(project.currentIndex())
    def save():
        values = dict(project=project.currentData(), directory=folder.text(), expected=info['folders'])
        if copying.isChecked() and note:
            values.update(path=note['path'], revision=note['hash'])
        dialog.accept()
        def done(result):
            copied = result['copied']
            if copied:
                window.notes[copied['path']] = copied
                window.after_job = lambda: window.open_profile_note(copied['path'])
            else:
                window.after_job = window.refresh
        window.work(tr('Projektzuordnung speichern …'),
                    lambda job: worker(job, window.store, 'project_configure', **values), done)
    actions.accepted.connect(lambda: window.safe(save))
    layout.addWidget(actions)
    window.memory_projects_dialog = dialog
    dialog.show()
