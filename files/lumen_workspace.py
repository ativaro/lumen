"""Native pages for durable work, selected knowledge and execution preferences."""
from lumen_i18n import worker_process, tr
import json
from html import escape
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QProcess, QThread, QTimer, Qt, QUrl, Signal, QEvent
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QMenu, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)
from lumen_actions import ACTIONS, undo
from lumen_knowledge import index_root, search
from lumen_store import Store, STATES
FIELDS = {'path': tr('Zielpfad oder Webadresse'), 'source': tr('Quelldatei'), 'text': tr('Inhalt'),
          'desktop': tr('Anwendung (.desktop-Dateiname)'), 'unit': tr('Dienst (.service)'),
          'scope': tr('Dienstbereich'), 'packages': tr('Paketnamen (durch Leerzeichen getrennt)')}


def page(title, description):
    widget = QWidget(); layout = QVBoxLayout(widget)
    heading = QLabel(title); heading.setObjectName('heading'); heading.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed); layout.addWidget(heading)
    info = QLabel(description); info.setWordWrap(True); info.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed); layout.addWidget(info)
    return widget, layout


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
        if getattr(parent, 'workflow', False):
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
    def __init__(self, parent, task=None, workflow=False):
        super().__init__(parent)
        self.resize(760, 700); self.workflow = workflow; self.value = None
        task = task or {}; box = QVBoxLayout(self); box.setContentsMargins(24, 20, 24, 20); box.setSpacing(14)
        if workflow:
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
        self.trigger = QComboBox()
        for title, key in [(tr('Manuell'), 'manual'), (tr('Regelmäßig'), 'interval'), (tr('Bei Ordneränderung'), 'directory')]: self.trigger.addItem(title, key)
        self.interval = QSpinBox(); self.interval.setRange(1, 525600); self.interval.setSuffix(tr(' Minuten'))
        self.watch = QComboBox(); self.watch.setAccessibleName(tr('Beobachteter Ordner'))
        self.enable = QCheckBox(tr('Automatischen Ablauf aktivieren'))
        scope_box.addStretch(); tabs.addTab(scope_page, tr('Ordner'))
        if task.get('prompt'): tabs.setCurrentWidget(prompt_page)
        self.approve = QCheckBox(tr('Diese Schritte und Ordner freigeben')); box.addWidget(self.approve)
        self.approve.setToolTip(tr('Freigabe gilt für genau diese gespeicherten Schritte. KI-Werkzeuge behalten ihre eigenen Rückfragen.'))
        self.error = QLabel(); self.error.setWordWrap(True); box.addWidget(self.error)
        row = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        row.accepted.connect(self.save); row.rejected.connect(self.reject); box.addWidget(row); self.refresh_roots()
        self.trigger.setCurrentIndex(max(0, self.trigger.findData(task.get('trigger', 'manual'))))
        self.interval.setValue(max(1, int(task.get('interval', 3600)) // 60))
        self.watch.setCurrentIndex(max(0, self.watch.findText(task.get('watch', ''))))
        self.enable.setChecked(bool(task.get('enabled', False)))
        self.trigger.currentIndexChanged.connect(self.update_trigger); self.update_trigger()

    def add_root(self):
        path = QFileDialog.getExistingDirectory(self, tr('Ordner freigeben'))
        if path: add_item(self.roots, path, path); self.refresh_roots()

    def reject(self):
        if self.workflow and not self.native_sentence.can_discard(): return
        super().reject()

    def remove_root(self):
        self.roots.takeItem(self.roots.currentRow()); self.refresh_roots()

    def update_trigger(self):
        scheduled = self.trigger.currentData() != 'manual'
        self.interval.setEnabled(scheduled); self.watch.setEnabled(self.trigger.currentData() == 'directory')
        self.enable.setEnabled(scheduled)

    def refresh_roots(self):
        previous = self.watch.currentText()
        self.watch.clear()
        for i in range(self.roots.count()): self.watch.addItem(self.roots.item(i).text())
        self.watch.setCurrentIndex(max(0, self.watch.findText(previous)))

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
            self.error.setText(tr('Bitte native Schritte oder einen KI-Auftrag verwenden; beide können getrennte Abläufe sein.')); return
        self.value = dict(name=self.name.text().strip(), roots=roots, steps=steps, prompt=prompt,
                          trigger=self.trigger.currentData(), interval=self.interval.value()*60,
                          watch=self.watch.currentText() if self.trigger.currentData() == 'directory' else '',
                          enabled=self.enable.isChecked(), approved=True)
        self.accept()


class Indexer(QThread):
    outcome = Signal(str)
    def __init__(self, store, root, parent):
        super().__init__(parent); self.store = store; self.root = root
    def run(self):
        try:
            from lumen_hardware import background_reason
            def pause():
                while reason := background_reason(self.store):
                    self.outcome.emit(reason + tr(' · wird automatisch fortgesetzt'))
                    for _ in range(20):
                        if self.isInterruptionRequested(): raise InterruptedError(tr('Indexierung abgebrochen.'))
                        self.msleep(250)
            result = index_root(self.store, self.root, self.isInterruptionRequested, pause)
            self.outcome.emit(tr('{0} Dokumente aufgenommen; {1} nicht lesbar.', result['documents'], result['errors']) +
                              (tr(' Größenlimit erreicht; kleinere Ordner wählen.') if result['limited'] else ''))
        except Exception as exc: self.outcome.emit(str(exc))


class Workspace(QObject):
    def __init__(self, window, store=None, sections=None):
        super().__init__(window); self.window = window
        self.store = store or (window.chat.tracker.store if hasattr(window, 'chat') else Store())
        self.sections = set(sections or ('tasks', 'flows', 'knowledge', 'models'))
        self.model_backend = None
        self.store.recover(); self.processes = []; self.indexer = None; self.task_signature = None; self.knowledge_job = None
        for name in self.sections:
            widget = getattr(self, 'build_' + name)(); widget.setParent(window)
            setattr(self, name + '_page', widget)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh_tasks); self.timer.start(1500)
        self.refresh_tasks(); self.refresh_flows(); self.refresh_knowledge()

    def guarded(self, fn):
        def call(*_):
            try: fn()
            except Exception as exc: QMessageBox.warning(self.window, 'Lumen', str(exc))
        return call

    def build_tasks(self):
        from studio_tasks import build_task_page
        widget = build_task_page(self)
        widget.setStyleSheet(Path(__file__).with_name('studio.qss').read_text())
        return widget

    def eventFilter(self, watched, event):
        if watched is getattr(self, 'tasks_page', None) and event.type() == QEvent.Resize:
            self.task_inspector.setFixedWidth(max(260, min(342, int(watched.width() * .42))))
            QTimer.singleShot(0, self.task_split, lambda: self.task_split.setSizes([self.tasks_page.width()-self.task_inspector.width()-1, self.task_inspector.width()]))
        return super().eventFilter(watched, event)

    def refresh_tasks(self, *_):
        if 'tasks' not in self.sections: return
        rows = self.store.tasks(include_dismissed=self.show_closed.isChecked())
        query = self.task_search.text().casefold().strip()
        signature = (query, [(r['id'], r['status'], r['updated']) for r in rows])
        if signature == self.task_signature: return
        previous = self.tasks.currentItem().data(Qt.UserRole) if self.tasks.currentItem() else None
        self.task_signature = signature; self.tasks.blockSignals(True); self.tasks.clear()
        rows = [r for r in rows if query in (r['title'] + ' ' + STATES.get(r['status'], r['status']) + ' ' + r['error']).casefold()]
        groups = [(tr('Braucht dich'), ('needs_input', 'failed', 'interrupted')), (tr('In Arbeit'), ('running',)),
                  (tr('Pausiert'), ('paused',)), (tr('Vorbereitet'), ('draft', 'queued')),
                  (tr('Erledigt'), ('completed',)), (tr('Abgebrochen'), ('cancelled',))]
        first = None
        for title, states in groups:
            group = [r for r in rows if r['status'] in states]
            if not group: continue
            header = QListWidgetItem(title); header.setFlags(Qt.NoItemFlags)
            header.setData(Qt.UserRole+2, len(group))
            self.tasks.addItem(header)
            for row in group:
                add_item(self.tasks, row['title'] + '\n' + STATES.get(row['status'], row['status']), row['id'])
                item = self.tasks.item(self.tasks.count()-1); item.setToolTip(row['title'])
                item.setData(Qt.UserRole+1, row)
                if first is None: first = item
                if row['id'] == previous: self.tasks.setCurrentItem(item)
        if self.tasks.currentItem() is None and first is not None: self.tasks.setCurrentItem(first)
        self.tasks.blockSignals(False)
        self.tasks_empty.setText(tr('Keine Aufträge für diese Suche.') if query else tr('Noch keine Aufträge. Beginne ein Gespräch oder lege einen Auftrag an.'))
        self.tasks_empty.setVisible(not rows); self.show_task()

    def task_capabilities(self, task):
        if not hasattr(self.window, 'chat'):
            if not task['steps']:
                from lumen_detail_routes import task_capabilities
                remote = task_capabilities(task['id'])
                if remote is not None: return remote
            running = task['status'] in ('running', 'needs_input')
            return dict(run=task['status'] in ('draft', 'queued', 'paused', 'interrupted', 'failed', 'needs_input'),
                        pause=running and bool(task['steps']), cancel=task['status'] not in ('completed', 'cancelled') and (not running or bool(task['steps'])))
        tracker = self.window.chat.tracker; backend = tracker.backend
        active = tracker.task_id == task['id'] and backend.busy
        running = task['status'] in ('running', 'needs_input')
        return dict(run=(bool(task['steps']) or not backend.busy) and task['status'] in ('draft', 'queued', 'paused', 'interrupted', 'failed', 'needs_input'),
            pause=running and (bool(task['steps']) or active and getattr(backend, 'execution', 'local') == 'local'),
            cancel=task['status'] not in ('completed', 'cancelled') and (not running or bool(task['steps']) or active))

    def show_task(self, *_):
        item = self.tasks.currentItem(); task = self.store.task(item.data(Qt.UserRole)) if item and item.data(Qt.UserRole) else None
        status = task['status'] if task else ''
        self.close_task.setEnabled(status in ('completed', 'cancelled'))
        self.close_task.setText(tr('Löschen') if status == 'cancelled' else tr('Schließen'))
        capabilities = self.task_capabilities(task) if task else {}
        for key, control in self.task_buttons.items(): control.setVisible(bool(task) and capabilities[key])
        self.task_save.setEnabled(bool(task and task['result'])); self.task_save.setVisible(bool(task and task['result']) and status not in ('running', 'needs_input'))
        self.task_reuse.setVisible(bool(task) and status not in ('running', 'needs_input'))
        self.task_outputs.setVisible(bool(task) and status not in ('running', 'needs_input'))
        self.task_result_link.setVisible(bool(task and task['result']))
        self.task_reuse.setEnabled(bool(task) and status not in ('running', 'needs_input'))
        self.task_conversation.setVisible(bool(task and task['session']))
        self.task_details.setEnabled(bool(task)); self.undo_task.setEnabled(bool(task))
        self.task_progress.setVisible(bool(task and (task['steps'] or status == 'running')))
        if task and not task['steps']: self.task_progress.setRange(0, 0)
        self.task_error.setVisible(bool(task and task['error']))
        if not task:
            self.task_result_key = None
            self.task_title.setText(tr('Wähle einen Auftrag')); self.task_meta.clear(); self.task_state.clear(); self.task_steps.clear(); self.detail.clear(); self.task_result.clear(); return
        self.task_title.setText(task['title'])
        if item.data(Qt.UserRole+1) != task: item.setData(Qt.UserRole+1, task)
        self.task_error.setText(task['error'])
        self.task_state.setText('•  '+STATES.get(status, status))
        self.task_meta.setText('▱  '+(Path(task['directory']).name or task['directory'])); self.task_meta.setToolTip(task['directory'])
        self.task_steps.setText('\n\n'.join(('✓  ' if i < task['cursor'] else '◷  ' if i == task['cursor'] and status == 'running' else '·  ')+step_description(step).split('\n')[0] for i, step in enumerate(task['steps']))
            or (tr('Lumen arbeitet am Auftrag.') if status == 'running' else STATES.get(status, status)))
        self.task_buttons['run'].setText(tr('Ausführen') if status in ('draft', 'queued') else tr('Fortsetzen'))
        self.task_buttons['pause'].setToolTip(tr('Der laufende native Schritt wird noch beendet.') if task['steps'] else tr('Unterbricht die Antwort. Fortsetzen prüft den bisherigen Stand.'))
        if task['steps']: self.task_progress.setRange(0, len(task['steps'])); self.task_progress.setValue(task['cursor'])
        key = (task['id'], task['result'], task['error'], status)
        if key != getattr(self, 'task_result_key', None):
            if not getattr(self, 'task_result_key', None) or self.task_result_key[0] != task['id']: self.task_result_link.setChecked(False)
            self.task_result_key = key
            from PySide6.QtGui import QTextDocument
            self.task_result.document().setMarkdown(task['result'] or task['error'] or tr('Noch kein Ergebnis. Auftrag und freigegebene Schritte stehen in den Details.'),
                QTextDocument.MarkdownFeatures(QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML))
            from ui_typography import format_document
            format_document(self.task_result.document(), getattr(self.window, 'settings', None))
        events = self.store.events(task['id'])
        content = [tr('Auftrag: ') + task['id'], task['title'], STATES.get(status, status), tr('Arbeitsordner: ') + task['directory'],
                   tr('Freigegebene Ordner: ') + ', '.join(task['roots']),
                   tr('Schritte: ') + '\n\n'.join(step_description(step) for step in task['steps']) if task['steps'] else '',
                   task['prompt'], task['error'], task['result'], tr('Verlauf:')]
        content += [e['kind'] + ': ' + e['detail'] for e in events if e['kind'] != 'input']
        self.detail.setPlainText('\n\n'.join(part for part in content if part))

    def open_task_conversation(self, task_id=None):
        if not hasattr(self.window, 'chat'):
            from lumen_detail_routes import task_action
            task_action(task_id or selected(self.tasks), 'conversation'); return
        task = self.store.task(task_id or selected(self.tasks)); chat = self.window.chat
        if not task['session']: return
        if task['session'] != chat.backend.session or task['directory'] != chat.backend.directory:
            if chat.backend.busy or chat.composer.toPlainText().strip() or chat.paths:
                raise ValueError(tr('Bitte das laufende Gespräch, den Entwurf oder angehängte Dateien zuerst abschließen.'))
            chat.set_action('')
            if not chat.backend.new_conversation(task['directory']): return
            chat.backend.select_session(task['session']); chat.update_context()
        self.window.show_page(0)

    def dismiss_task(self):
        self.store.dismiss_task(selected(self.tasks))
        self.show_closed.setChecked(False); self.refresh_tasks()

    def select_task(self, task_id):
        self.task_search.clear()
        self.refresh_tasks()
        for row in range(self.tasks.count()):
            item = self.tasks.item(row)
            if item.data(Qt.UserRole) == task_id:
                self.tasks.setCurrentItem(item); self.tasks.scrollToItem(item)
                return
        try: task = self.store.task(task_id)
        except ValueError:
            self.tasks.setCurrentRow(-1); self.detail.setPlainText(tr('Dieser Auftrag ist nicht mehr vorhanden.'))
            self.task_meta.setText(tr('Dieser Auftrag ist nicht mehr vorhanden.'))
            return
        add_item(self.tasks, f"{STATES.get(task['status'], task['status'])} · {task['title']}", task_id)
        self.tasks.item(self.tasks.count()-1).setData(Qt.UserRole+1, task)
        self.tasks.setCurrentRow(self.tasks.count() - 1)

    def new_task(self):
        dialog = PlanDialog(self.window, {'roots': [self.directory()]})
        if dialog.exec():
            value = dialog.value
            task = self.store.create_task(value['name'], prompt=value['prompt'], roots=value['roots'],
                directory=value['roots'][0], steps=value['steps'], approved=True)
            self.store.event(task, 'approved', tr('Schritte und Ordner im Lumen-Dialog freigegeben.')); self.refresh_tasks()

    def run_task(self, identity=None):
        task = self.store.task(identity or selected(self.tasks))
        if not hasattr(self.window, 'chat') and not task['steps']:
            from lumen_detail_routes import task_action
            task_action(task['id'], 'run'); return
        if task['status'] in ('completed', 'running', 'cancelled'): raise ValueError(tr('Dieser Auftrag kann nicht fortgesetzt werden.'))
        if not task['approved'] and task['steps']:
            dialog = PlanDialog(self.window, task)
            if not dialog.exec(): return
            value = dialog.value
            replacement = self.store.create_task(value['name'], prompt=value['prompt'], directory=value['roots'][0], roots=value['roots'], steps=value['steps'], approved=True)
            self.store.update_task(task['id'], status='cancelled')
            self.store.event(replacement, 'approved', tr('Geprüfter Entwurf ') + task['id'])
            task = self.store.task(replacement)
        if task['status'] in ('interrupted', 'failed') and QMessageBox.question(self.window, tr('Letzten Schritt prüfen'),
            tr('Der letzte Schritt könnte bereits teilweise ausgeführt worden sein. Verlauf und Ergebnis geprüft und Wiederholung freigegeben?')) != QMessageBox.Yes: return
        if task['steps']:
            self.start_process([str(Path(__file__).with_name('lumen_tasks.py')), '--task', task['id']])
        else:
            self.window.chat.tracker.resume(task['id'], self.window.chat); self.window.show_page(0)
        self.refresh_tasks()

    def stop_task(self, state):
        if not hasattr(self.window, 'chat'):
            from lumen_detail_routes import task_action
            task = self.store.task(selected(self.tasks))
            if not task['steps'] and task['status'] in ('running','needs_input'):
                task_action(task['id'], 'pause' if state == 'paused' else 'cancel'); return
            if task['status'] not in ('completed', 'cancelled'):
                self.store.update_task(task['id'], status=state)
                self.store.event(task['id'], state, tr('Angefordert. Ein bereits laufender nativer Schritt wird noch beendet.'))
            self.refresh_tasks(); return
        task = self.store.task(selected(self.tasks)); tracker = self.window.chat.tracker
        if task['status'] in ('completed', 'cancelled'): return
        if not self.task_capabilities(task)['pause' if state == 'paused' else 'cancel']:
            raise ValueError(tr('Diese Steuerung ist für diesen Auftrag hier nicht verfügbar.'))
        if tracker.task_id == task['id'] and tracker.backend.busy:
            tracker.pause() if state == 'paused' else tracker.backend.stop()
        else:
            self.store.update_task(task['id'], status=state)
            self.store.event(task['id'], state, tr('Angefordert. Ein bereits laufender nativer Schritt wird noch beendet.'))
        self.refresh_tasks()

    def start_process(self, args):
        process = worker_process(self); self.processes.append(process)
        process.setProcessChannelMode(QProcess.MergedChannels)
        def done(code):
            output = bytes(process.readAllStandardOutput()).decode(errors='replace')
            if code and output: QMessageBox.warning(self.window, tr('Auftrag fehlgeschlagen'), output[-2000:])
            self.processes.remove(process); process.deleteLater(); self.refresh_tasks()
        process.finished.connect(done)
        process.errorOccurred.connect(lambda _: QMessageBox.warning(self.window, 'Lumen', tr('Auftragsprozess konnte nicht gestartet werden.')))
        process.start(sys.executable, args)

    def task_to_file_action(self, task_id=None):
        from file_actions import save_action
        save_action(self.window, self.store, self.store.task(task_id or selected(self.tasks)))
        self.refresh_flows()

    def task_to_tool(self, task_id=None):
        from lumen_detail_routes import launch
        task = self.store.task(task_id or selected(self.tasks))
        launch('lumen-code', ['--save-task', task['id']])

    def task_to_flow(self, task_id=None):
        task = self.store.task(task_id or selected(self.tasks)); self.flow_dialog(task)

    def export_task(self, task_id=None):
        task = self.store.task(task_id or selected(self.tasks))
        if not task['result']: raise ValueError(tr('Dieser Auftrag hat noch kein Ergebnis.'))
        path, _ = QFileDialog.getSaveFileName(self.window, tr('Ergebnis speichern'), task['directory'] + '/lumen-ergebnis.md', 'Markdown (*.md);;Text (*.txt)')
        if not path: return
        target = Path(path); step = {'action': 'write', 'path': str(target), 'text': task['result']}
        job = self.store.create_task(tr('Ergebnis: ') + task['title'][:180], directory=str(target.parent), roots=[str(target.parent)], steps=[step], approved=True)
        from lumen_tasks import run_steps
        run_steps(self.store, job); self.refresh_tasks()

    def task_to_knowledge(self, task_id=None):
        task=self.store.task(task_id or selected(self.tasks))
        if not task['result']:raise ValueError(tr('Dieser Auftrag hat noch kein Ergebnis.'))
        self.knowledge_work('save_memory',lambda _:self.refresh_knowledge(),title=task['title'],text=task['result'],source=tr('Lumen-Auftrag · ')+task['id'])

    def undo_change(self):
        task = selected(self.tasks); changes = [r for r in self.store.changes(task) if r['status'] in ('applied', 'pending')]
        if not changes: raise ValueError(tr('Keine rücknehmbaren nativen Dateiänderungen vorhanden.'))
        titles = [r['path'] + ' · ' + r['id'][:8] for r in changes]
        choice, ok = QInputDialog.getItem(self.window, tr('Änderung rückgängig'), tr('Datei'), titles, 0, False)
        if ok: undo(self.store, changes[titles.index(choice)]['id']); self.show_task()

    def build_flows(self):
        widget, box = page(tr('Abläufe'), tr('Einmal vorbereiten. Jederzeit wiederholen.'))
        box.setContentsMargins(24, 20, 24, 16); box.setSpacing(16)
        create = QPushButton(tr('Neuer Ablauf')); create.setObjectName('primary')
        create.clicked.connect(self.guarded(lambda: self.flow_dialog())); box.addWidget(create, 0, Qt.AlignLeft)
        split = QSplitter(); self.flows = QListWidget(); self.flows.setObjectName('searchResults'); self.flows.setSpacing(8)
        self.flows.setAccessibleName(tr('Wiederverwendbare Abläufe')); self.flows.setMinimumWidth(220)
        split.addWidget(self.flows)
        detail = QWidget(); details = QVBoxLayout(detail); details.setContentsMargins(20, 0, 0, 0)
        self.flow_detail = QTextBrowser(); self.flow_detail.setOpenExternalLinks(False); self.flow_detail.setFrameShape(QFrame.NoFrame)
        self.flow_detail.setAccessibleName(tr('Ablaufvorschau')); details.addWidget(self.flow_detail, 1)
        self.flow_buttons = {}
        row = QHBoxLayout()
        for key, title, callback in [('run', tr('Jetzt starten'), self.run_flow), ('edit', tr('Bearbeiten'), self.edit_flow),
                                     ('toggle', tr('Aktivieren'), self.toggle_flow), ('remove', tr('Entfernen'), self.remove_flow)]:
            control = QPushButton(title); control.clicked.connect(self.guarded(callback)); row.addWidget(control); self.flow_buttons[key] = control
        self.flow_buttons['run'].setObjectName('primary'); details.addLayout(row)
        split.addWidget(detail); split.setStretchFactor(1, 2); split.setSizes([290, 600]); box.addWidget(split, 1)
        self.flows.currentItemChanged.connect(self.show_flow)
        self.flows.itemDoubleClicked.connect(self.guarded(self.edit_flow))
        self.timer_status = QLabel(); self.timer_status.setObjectName('muted'); self.timer_status.setWordWrap(True); box.addWidget(self.timer_status)
        buttons(box, [(tr('Hintergrundprüfung aktivieren'), self.guarded(lambda: self.set_timer(True))),
                      (tr('Hintergrundprüfung stoppen'), self.guarded(lambda: self.set_timer(False))), (tr('Jetzt prüfen'), self.guarded(self.tick))])
        return widget

    def flow_dialog(self, task=None, workflow=None):
        dialog = PlanDialog(self.window, task or {'roots': [self.directory()]}, workflow=True)
        if dialog.exec():
            self.store.save_workflow(**dialog.value, workflow=workflow); self.refresh_flows()

    def edit_flow(self):
        flow = selected(self.flows); self.flow_dialog(flow, workflow=flow['id'])

    def refresh_flows(self):
        if 'flows' not in self.sections: return
        current = self.flows.currentItem().data(Qt.UserRole)['id'] if self.flows.currentItem() else None
        self.flows.clear()
        for flow in self.store.workflows():
            trigger = {'manual': tr('Manuell'), 'interval': tr('Zeitplan'), 'directory': tr('Ordneränderung')}[flow['trigger']]
            state = tr('Aktiv') if flow['enabled'] else tr('Pausiert') if flow['trigger'] != 'manual' else tr('Bereit')
            if not flow['approved']: state = tr('Freigabe erforderlich')
            add_item(self.flows, flow['name'] + '\n' + trigger + ' · ' + state, flow)
            if flow['id'] == current: self.flows.setCurrentRow(self.flows.count()-1)
        if self.flows.currentRow() < 0 and self.flows.count(): self.flows.setCurrentRow(0)
        self.show_flow()
        self.timer_status.setText(tr('Zeit- und Ordnerauslöser benötigen die Hintergrundprüfung. Laufende Schritte werden bei Pause zu Ende geführt.'))

    def show_flow(self, *_):
        item = self.flows.currentItem()
        for control in self.flow_buttons.values(): control.setEnabled(bool(item))
        if not item:
            self.flow_detail.setPlainText(tr('Dein erster Ablauf\n\nFasse wiederkehrende Handgriffe zu einer Folge zusammen oder beschreibe einen KI-Auftrag. Lege fest, wann er startet und auf welche Ordner er zugreifen darf.'))
            return
        flow = item.data(Qt.UserRole)
        self.flow_buttons['run'].setEnabled(bool(flow['approved']))
        self.flow_buttons['toggle'].setEnabled(bool(flow['approved']) and flow['trigger'] != 'manual')
        self.flow_buttons['toggle'].setText(tr('Pausieren') if flow['enabled'] else tr('Aktivieren'))
        trigger = tr('Nur wenn du ihn startest') if flow['trigger'] == 'manual' else tr('Alle {0} Minuten', flow['interval']//60)
        if flow['trigger'] == 'directory': trigger += ' · ' + flow['watch']
        html = '<h2>' + escape(flow['name']) + '</h2><p>' + escape(trigger) + '</p>'
        html += '<h3>' + tr('Freigegebene Ordner') + '</h3><p>' + '<br>'.join(escape(root) for root in flow['roots']) + '</p>'
        if flow['prompt']: html += '<h3>' + tr('KI-Auftrag') + '</h3><p>' + escape(flow['prompt']).replace('\n', '<br>') + '</p>'
        else:
            html += '<h3>' + tr('Schritt für Schritt') + '</h3><ol>'
            html += ''.join('<li><p>' + escape(step_description(step)).replace('\n', '<br>') + '</p></li>' for step in flow['steps']) + '</ol>'
        if not flow['approved']: html += '<p>' + tr('Zum Freigeben den Ablauf bearbeiten und speichern.') + '</p>'
        self.flow_detail.setHtml(html)

    def run_flow(self):
        flow = selected(self.flows)
        if not flow['approved']: raise PermissionError(tr('Ablauf ist nicht freigegeben. Neu speichern.'))
        task = self.store.create_task(flow['name'], prompt=flow['prompt'], directory=flow['roots'][0], roots=flow['roots'], steps=flow['steps'], approved=True)
        self.store.event(task, 'workflow', flow['id']); self.refresh_tasks()
        if 'tasks' not in self.sections:
            self.run_task(task)
            from lumen_detail_routes import open_tasks
            open_tasks(task); return
        for i in range(self.tasks.count()):
            if self.tasks.item(i).data(Qt.UserRole) == task: self.tasks.setCurrentRow(i)
        self.window.show_page(4); self.run_task()

    def toggle_flow(self):
        flow = selected(self.flows); self.store.set_workflow_enabled(flow['id'], not flow['enabled']); self.refresh_flows()

    def remove_flow(self):
        flow = selected(self.flows)
        if QMessageBox.question(self.window, tr('Ablauf entfernen'), tr('„{0}“ entfernen? Bisherige Aufträge bleiben erhalten.', flow['name'])) != QMessageBox.Yes: return
        with self.store.connect() as db: db.execute('DELETE FROM workflows WHERE id=?', (flow['id'],))
        self.refresh_flows()

    def set_timer(self, enabled):
        from lumen_actions import command
        command(['systemctl', '--user', 'enable' if enabled else 'disable', '--now', 'lumen-jobs.timer'])
        self.timer_status.setText(tr('Hintergrundprüfung aktiv.') if enabled else tr('Hintergrundprüfung gestoppt.'))

    def tick(self): self.start_process([str(Path(__file__).with_name('lumen_tasks.py')), '--tick'])

    def build_knowledge(self):
        widget, box = page(tr('Dokumentquellen'), tr('Freigegebene Ordner durchsuchen und ausgewählte Quellen im Gespräch verwenden.'))
        box.setContentsMargins(24, 20, 24, 16); box.setSpacing(16)
        self.knowledge_status = QLabel(); self.knowledge_status.setWordWrap(True); self.knowledge_status.setObjectName('muted'); box.addWidget(self.knowledge_status)
        source_box = box
        info = QLabel(tr('Nur ausgewählte Ordner werden lokal indexiert. Quellen werden erst mit „Im Gespräch verwenden“ an das gewählte Modell übergeben.')); info.setWordWrap(True); source_box.addWidget(info)
        self.roots = QListWidget(); self.roots.setMaximumHeight(85); self.roots.setAccessibleName(tr('Notizordner')); source_box.addWidget(self.roots)
        buttons(source_box, [(tr('Ordner aufnehmen'), self.guarded(self.add_knowledge)), (tr('Neu indexieren'), self.guarded(lambda: self.start_index(selected(self.roots)))),
                      (tr('Freigabe entfernen'), self.guarded(self.remove_knowledge)), (tr('Indexierung stoppen'), self.cancel_index)])
        self.index_status = QLabel(); self.index_status.setWordWrap(True); source_box.addWidget(self.index_status)
        self.query = QLineEdit(); self.query.setPlaceholderText(tr('Dokumente durchsuchen …')); self.query.setAccessibleName(tr('Notizsuche'))
        self.query.returnPressed.connect(self.guarded(self.search)); source_box.addWidget(self.query)
        self.results = QListWidget(); self.results.setAccessibleName(tr('Dokumente mit Quellen')); source_box.addWidget(self.results, 1)
        buttons(source_box, [(tr('Suchen'), self.guarded(self.search)), (tr('Quelle öffnen'), self.guarded(self.open_source)),
                      (tr('Im Gespräch verwenden'), self.guarded(self.use_source))])
        return widget

    def refresh_knowledge(self):
        if 'knowledge' not in self.sections: return
        self.roots.clear()
        for row in self.store.rows('SELECT * FROM roots ORDER BY path'): add_item(self.roots, row['path'], row['path'])
        notebook = self.store.setting('knowledge/notebook', '')
        self.knowledge_status.setText(tr('Notizbuch: {0}', notebook) if notebook else tr('Beim ersten Öffnen wird dein Notizbuch eingerichtet. Vorhandene Erinnerungen bleiben erhalten.'))

    def knowledge_work(self,action,done,**values):
        from tools_ui import Job
        from wissen_data import worker
        if self.knowledge_job:raise ValueError(tr('Den laufenden Notizvorgang kurz abwarten.'))
        job=Job(lambda job:worker(job,self.store,action,**values),self);self.knowledge_job=job;results=[]
        if not hasattr(self, 'index_status'):
            self.index_status = getattr(self.window, 'status', None)
            if self.index_status is None:
                self.index_status = QLabel(self.tasks_page)
                self.tasks_page.layout().addWidget(self.index_status)
        self.index_status.setText(tr('Notizordner wird verarbeitet …'))
        job.result.connect(results.append);job.failed.connect(lambda message:self.index_status.setText(message))
        def finished():
            self.knowledge_job=None;job.deleteLater()
            if results and not job.cancelled.is_set():self.index_status.setText(tr('Notizordner aktualisiert.'));self.guarded(lambda:done(results[0]))()
        job.finished.connect(finished);job.start()

    def open_notebook(self, area='user'):
        from lumen_apps import launch
        launch('wissen', area=area)

    def add_knowledge(self):
        root = QFileDialog.getExistingDirectory(self.window, tr('Notizordner freigeben'))
        if root: self.start_index(root)

    def start_index(self, root):
        if self.indexer and self.indexer.isRunning(): raise ValueError(tr('Die laufende Indexierung zuerst beenden.'))
        self.index_status.setText(tr('Indexierung läuft …')); self.indexer = Indexer(self.store, root, self)
        self.indexer.outcome.connect(self.index_status.setText)
        self.indexer.finished.connect(self.refresh_knowledge); self.indexer.start()

    def cancel_index(self):
        if self.indexer: self.indexer.requestInterruption()

    def remove_knowledge(self):
        if self.indexer and self.indexer.isRunning(): raise ValueError(tr('Vor dem Entfernen die Indexierung beenden.'))
        self.store.remove_root(selected(self.roots)); self.results.clear(); self.refresh_knowledge()

    def search(self):
        self.results.clear()
        for row in search(self.store, self.query.text()):
            add_item(self.results, tr('{0} · Seite {1}\n{2}\n{3}', Path(row['path']).name, row['page'], row['snippet'], row['path']), row)

    def open_source(self): QDesktopServices.openUrl(QUrl.fromLocalFile(selected(self.results)['path']))

    def use_source(self):
        row = selected(self.results)
        self.to_chat(tr('Quelle: {0} (Seite {1})\nAuszug: {2}\n\n', row['path'], row['page'], row['snippet']), [row['path']])

    def to_chat(self, text, paths=None):
        if not hasattr(self.window, 'chat'):
            from lumen_detail_routes import launch
            launch('lumen-agent-app', ['--prompt', text] + [arg for p in paths or [] for arg in ('--file', p)])
            return
        if self.window.chat.backend.busy: raise ValueError(tr('Bitte den laufenden Auftrag zuerst pausieren.'))
        self.window.chat.begin_context(paths=paths or [])
        self.window.chat.composer.setPlainText(text); self.window.show_page(0)

    def build_models(self):
        widget, box = page(tr('Modelle & Ressourcen'), tr('Wähle, welche Modelle Lumen verwenden darf. „Lokaler Dienst“ erzwingt eine Loopback-Adresse; dessen eigene Weiterleitungen bleiben dessen Verantwortung.'))
        form = QFormLayout(); box.addLayout(form); policy = self.store.setting('modelPolicy', {})
        self.privacy = QComboBox(); self.privacy.addItem(tr('Konfigurierte Anbieter (auch Cloud)'), 'configured'); self.privacy.addItem(tr('Nur lokaler Dienst'), 'local')
        self.privacy.setCurrentIndex(1 if policy.get('privacy') == 'local' else 0); form.addRow(tr('Verarbeitung'), self.privacy)
        self.model_controls = {}
        for key, title in [('model', tr('Standardmodell')), ('background_model', tr('Modell für wiederkehrende KI-Aufträge')), ('local_model', tr('Lokales Modell'))]:
            control = QComboBox(); control.setEditable(True); control.addItem(policy.get(key, '')); control.setAccessibleName(title)
            form.addRow(title, control); self.model_controls[key] = control
        self.timeout = QSpinBox(); self.timeout.setRange(1, 120); self.timeout.setValue(int(policy.get('timeout_seconds', 900))//60); self.timeout.setSuffix(tr(' Minuten')); form.addRow(tr('Zeitlimit pro KI-Auftrag'), self.timeout)
        self.gpu = QSpinBox(); self.gpu.setRange(1,100); self.gpu.setValue(int(policy.get('gpu_limit',90))); self.gpu.setSuffix(' %'); form.addRow(tr('Hintergrundarbeit pausiert ab GPU-Auslastung'), self.gpu)
        self.pause_background = QCheckBox(tr('Alle Hintergrundaufträge pausieren')); self.pause_background.setChecked(policy.get('pause_background',False)); box.addWidget(self.pause_background)
        self.model_status = QLabel(tr('GPU-Prüfung verwendet NVIDIA-SMI, wenn verfügbar. 100 % deaktiviert die GPU-Grenze.')); self.model_status.setWordWrap(True); box.addWidget(self.model_status)
        buttons(box, [(tr('Verfügbare Modelle laden'), self.load_models), (tr('Speichern'), self.guarded(self.save_models))]); box.addStretch(); return widget

    def load_models(self):
        if hasattr(self.window, 'chat'): backend = self.window.chat.backend
        else:
            if self.model_backend is None:
                from desktop_backend import DesktopBackend
                self.model_backend = DesktopBackend(self.directory(), self)
            backend = self.model_backend
        def loaded(data):
            names = [p['id'] + '/' + model for p in data.get('providers', []) for model in p.get('models', {})]
            for control in self.model_controls.values():
                old = control.currentText(); control.clear(); control.addItem(''); control.addItems(names); control.setCurrentText(old)
            self.model_status.setText(tr('{0} Modelle verfügbar. Lokale Anbieter in den Verbindungseinstellungen konfigurieren.', len(names)))
        backend.ensure_server(lambda: backend.request('GET','/config/providers',callback=loaded))

    def save_models(self):
        policy = self.store.setting('modelPolicy', {})
        policy.update({key: c.currentText().strip() for key,c in self.model_controls.items()})
        if self.privacy.currentData() == 'local' and '/' not in policy['local_model']: raise ValueError(tr('Lokales Modell als anbieter/modell auswählen.'))
        policy.update(privacy=self.privacy.currentData(),timeout_seconds=self.timeout.value()*60,gpu_limit=self.gpu.value(),pause_background=self.pause_background.isChecked())
        from PySide6.QtCore import QSettings
        settings = self.window.chat.settings if hasattr(self.window, 'chat') else getattr(self.window, 'assistant', None) or QSettings('Lumen', 'Assistant')
        if hasattr(self.window, 'preferencesChanged'): self.window.save(settings, {'model': policy['model']})
        else: settings.setValue('model', policy['model']); settings.sync()
        self.store.set_setting('modelPolicy',policy)
        self.model_status.setText(tr('Gespeichert. Die Richtlinie gilt ab dem nächsten Auftrag.'))

    def can_close(self):
        if any(p.state() != QProcess.NotRunning for p in self.processes):
            QMessageBox.information(self.window, tr('Auftrag läuft'), tr('Bitte den laufenden nativen Schritt beenden lassen.')); return False
        if self.indexer and self.indexer.isRunning():
            self.indexer.requestInterruption(); self.indexer.wait(5000)
            if self.indexer.isRunning(): return False
        if self.knowledge_job:
            self.knowledge_job.cancelled.set();self.knowledge_job.wait(3000)
            if self.knowledge_job.isRunning():return False
        return True

    def directory(self):
        if hasattr(self.window, 'chat'): return self.window.chat.backend.directory
        from PySide6.QtCore import QSettings
        return QSettings('Lumen', 'Assistant').value('workdir', str(Path.home()))

    def shutdown(self):
        self.timer.stop()
        if self.model_backend is not None: self.model_backend.shutdown()
