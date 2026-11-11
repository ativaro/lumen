"""Dialogs that prepare a Lumen task or a file action: steps, AI instruction and allowed folders."""
from lumen_i18n import tr

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget)
from lumen_actions import ACTIONS
FIELDS = {'path': tr('Zielpfad oder Webadresse'), 'source': tr('Quelldatei'), 'text': tr('Inhalt'),
          'desktop': tr('Anwendung (.desktop-Dateiname)'), 'unit': tr('Dienst (.service)'),
          'scope': tr('Dienstbereich'), 'packages': tr('Paketnamen (durch Leerzeichen getrennt)')}


def buttons(layout, entries):
    row = QHBoxLayout()
    for title, callback in entries:
        item = QPushButton(title); item.clicked.connect(callback); row.addWidget(item)
    layout.addLayout(row)


def selected(widget):
    item = widget.currentItem()
    if item is None: raise ValueError(tr('Bitte zuerst einen Eintrag auswählen.'))
    return item.data(Qt.UserRole)


def add_item(widget, title, value):
    item = QListWidgetItem(title); item.setData(Qt.UserRole, value); widget.addItem(item)


def step_description(step):
    title = ACTIONS.get(step.get('action'), (step.get('action', ''), ()))[0]
    fields = [f'{FIELDS.get(key, key)}: {value}' for key, value in step.items() if key != 'action']
    return '\n'.join([title, *fields])


class StepDialog(QDialog):
    def __init__(self, parent, step=None):
        super().__init__(parent); self.setWindowTitle(tr('Schritt hinzufügen')); self.resize(560, 350)
        box = QVBoxLayout(self); self.action = QComboBox(); self.action.setAccessibleName(tr('Aktion'))
        for key, (title, _) in ACTIONS.items(): self.action.addItem(title, key)
        box.addWidget(self.action); self.form = QFormLayout(); box.addLayout(self.form)
        self.controls = {}; self.action.currentIndexChanged.connect(self.rebuild); self.rebuild()
        if step:
            self.action.setCurrentIndex(self.action.findData(step['action']))
            for key, control in self.controls.items():
                if isinstance(control, QPlainTextEdit): control.setPlainText(step[key])
                elif isinstance(control, QComboBox): control.setCurrentIndex(control.findData(step[key]))
                else: control.setText(step[key])
        row = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        row.accepted.connect(self.accept); row.rejected.connect(self.reject); box.addWidget(row)
        if getattr(parent, 'file_action', False):
            from code_sentence_native import style_step
            style_step(self, box, step)

    def rebuild(self):
        while self.form.rowCount(): self.form.removeRow(0)
        self.controls = {}
        for key in ACTIONS[self.action.currentData()][1]:
            if key == 'text': control = QPlainTextEdit()
            elif key == 'scope':
                control = QComboBox(); control.addItem(tr('Benutzer'), 'user'); control.addItem(tr('System (Authentifizierung)'), 'system')
            else: control = QLineEdit()
            control.setAccessibleName(FIELDS[key]); self.form.addRow(FIELDS[key], control); self.controls[key] = control

    def step(self):
        return {'action': self.action.currentData(), **{key: control.toPlainText() if isinstance(control, QPlainTextEdit)
            else control.currentData() if isinstance(control, QComboBox) else control.text().strip()
            for key, control in self.controls.items()}}


class PlanDialog(QDialog):
    def __init__(self, parent, task=None, file_action=False):
        super().__init__(parent)
        self.resize(760, 700); self.file_action = file_action; self.value = None
        task = task or {}; box = QVBoxLayout(self); box.setContentsMargins(24, 20, 24, 20); box.setSpacing(14)
        if file_action:
            from code_sentence_native import NativeSentence
            self.native_sentence = NativeSentence(self, task, box)
            return
        self.setWindowTitle(tr('Auftrag vorbereiten'))
        heading = QLabel(tr('Auftrag vorbereiten')); heading.setObjectName('heading'); box.addWidget(heading)
        self.name = QLineEdit(task.get('title', task.get('name', ''))); self.name.setPlaceholderText(tr('Name')); self.name.setAccessibleName(tr('Name')); box.addWidget(self.name)
        tabs = QTabWidget(); box.addWidget(tabs, 1)
        steps_page = QWidget(); steps_box = QVBoxLayout(steps_page); steps_box.setContentsMargins(16, 16, 16, 16); steps_box.setSpacing(12)
        intro = QLabel(tr('Native Schritte werden in dieser Reihenfolge ausgeführt.')); intro.setWordWrap(True); steps_box.addWidget(intro)
        self.steps = QListWidget(); self.steps.setObjectName('searchResults'); self.steps.setSpacing(5); steps_box.addWidget(self.steps, 2)
        self.steps.setAccessibleName(tr('Native Schritte'))
        self.step_preview = QPlainTextEdit(); self.step_preview.setReadOnly(True)
        self.step_preview.setAccessibleName(tr('Vollständiger ausgewählter Schritt')); steps_box.addWidget(self.step_preview, 1)
        self.steps.currentItemChanged.connect(lambda current, previous: self.step_preview.setPlainText(step_description(current.data(Qt.UserRole)) if current else ''))
        for step in task.get('steps', []): self.add_step_item(step)
        buttons(steps_box, [(tr('Hinzufügen'), self.add_step), (tr('Bearbeiten'), self.edit_step), (tr('Nach oben'), lambda: self.move_step(-1)), (tr('Nach unten'), lambda: self.move_step(1)), (tr('Entfernen'), lambda: self.steps.takeItem(self.steps.currentRow()))])
        self.steps.itemDoubleClicked.connect(lambda _: self.edit_step())
        tabs.addTab(steps_page, tr('Schritte'))
        prompt_page = QWidget(); prompt_box = QVBoxLayout(prompt_page); prompt_box.setContentsMargins(16, 16, 16, 16); prompt_box.setSpacing(12)
        intro = QLabel(tr('Verwende entweder feste Schritte oder einen KI-Auftrag. KI-Werkzeuge behalten ihre eigenen Rückfragen.')); intro.setWordWrap(True); prompt_box.addWidget(intro)
        self.prompt = QPlainTextEdit(task.get('prompt', '')); self.prompt.setAccessibleName(tr('KI-Auftrag'))
        self.prompt.setPlaceholderText(tr('Was soll Lumen für dich erledigen?')); prompt_box.addWidget(self.prompt, 1)
        tabs.addTab(prompt_page, tr('KI-Auftrag'))
        scope_page = QWidget(); scope_box = QVBoxLayout(scope_page); scope_box.setContentsMargins(16, 16, 16, 16); scope_box.setSpacing(12)
        scope_box.addWidget(QLabel(tr('Freigegebene Ordner')))
        self.roots = QListWidget(); self.roots.setObjectName('searchResults'); self.roots.setMaximumHeight(150); scope_box.addWidget(self.roots)
        for root in task.get('roots', []): add_item(self.roots, root, root)
        buttons(scope_box, [(tr('Ordner hinzufügen'), self.add_root), (tr('Ordner entfernen'), self.remove_root)])
        scope_box.addStretch(); tabs.addTab(scope_page, tr('Ordner'))
        if task.get('prompt'): tabs.setCurrentWidget(prompt_page)
        self.approve = QCheckBox(tr('Diese Schritte und Ordner freigeben')); box.addWidget(self.approve)
        self.approve.setToolTip(tr('Freigabe gilt für genau diese gespeicherten Schritte. KI-Werkzeuge behalten ihre eigenen Rückfragen.'))
        self.error = QLabel(); self.error.setWordWrap(True); box.addWidget(self.error)
        row = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        row.accepted.connect(self.save); row.rejected.connect(self.reject); box.addWidget(row)

    def add_root(self):
        path = QFileDialog.getExistingDirectory(self, tr('Ordner freigeben'))
        if path: add_item(self.roots, path, path)

    def reject(self):
        if self.file_action and not self.native_sentence.can_discard(): return
        super().reject()

    def remove_root(self):
        self.roots.takeItem(self.roots.currentRow())

    def add_step_item(self, step):
        summary = ACTIONS[step['action']][0] + '\n' + ', '.join(f'{FIELDS[k]}: {v}' for k, v in step.items() if k not in ('action', 'text'))
        if 'text' in step: summary += '\n' + step['text'][:300]
        add_item(self.steps, summary, step)
        self.steps.setCurrentRow(self.steps.count()-1)

    def add_step(self):
        dialog = StepDialog(self)
        if dialog.exec():
            from lumen_actions import validate_steps
            try: step = dialog.step(); validate_steps([step]); self.add_step_item(step)
            except ValueError as exc: self.error.setText(str(exc))

    def edit_step(self):
        item = self.steps.currentItem()
        if not item: return
        dialog = StepDialog(self, item.data(Qt.UserRole))
        if dialog.exec():
            from lumen_actions import validate_steps
            try:
                step = dialog.step(); validate_steps([step])
                item.setData(Qt.UserRole, step); item.setText(step_description(step))
                self.step_preview.setPlainText(step_description(step))
            except ValueError as error: self.error.setText(str(error))

    def move_step(self, offset):
        current = self.steps.currentRow(); target = current + offset
        if current < 0 or not 0 <= target < self.steps.count(): return
        item = self.steps.takeItem(current); self.steps.insertItem(target, item); self.steps.setCurrentRow(target)

    def save(self):
        roots = [self.roots.item(i).data(Qt.UserRole) for i in range(self.roots.count())]
        steps = [self.steps.item(i).data(Qt.UserRole) for i in range(self.steps.count())]
        prompt = self.prompt.toPlainText().strip()
        if not self.name.text().strip() or not roots or not (steps or prompt) or not self.approve.isChecked():
            self.error.setText(tr('Name, mindestens ein Ordner, Schritte oder KI-Auftrag und deine Freigabe sind erforderlich.')); return
        if steps and prompt:
            self.error.setText(tr('Bitte native Schritte oder einen KI-Auftrag verwenden; beide können getrennte Aufträge sein.')); return
        self.value = dict(name=self.name.text().strip(), roots=roots, steps=steps, prompt=prompt, approved=True)
        self.accept()
