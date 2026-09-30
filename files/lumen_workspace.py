"""Native pages for durable work, selected knowledge and execution preferences."""
import json
from pathlib import Path
import sys

from PyQt5.QtCore import QObject, QProcess, QThread, QTimer, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy, QSpinBox, QSplitter, QTextBrowser, QVBoxLayout, QWidget)
from lumen_actions import ACTIONS, undo
from lumen_knowledge import index_root, search
from lumen_store import Store

STATES = {'draft': 'Entwurf', 'queued': 'Geplant', 'running': 'Läuft', 'paused': 'Pausiert',
          'interrupted': 'Unterbrochen', 'needs_input': 'Braucht dich', 'completed': 'Erledigt',
          'failed': 'Fehlgeschlagen', 'cancelled': 'Abgebrochen'}
FIELDS = {'path': 'Zielpfad oder Webadresse', 'source': 'Quelldatei', 'text': 'Inhalt',
          'desktop': 'Anwendung (.desktop-Dateiname)', 'unit': 'Dienst (.service)',
          'scope': 'Dienstbereich', 'packages': 'Paketnamen (durch Leerzeichen getrennt)'}


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
    if item is None: raise ValueError('Bitte zuerst einen Eintrag auswählen.')
    return item.data(Qt.UserRole)


def add_item(widget, title, value):
    item = QListWidgetItem(title); item.setData(Qt.UserRole, value); widget.addItem(item)


class StepDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent); self.setWindowTitle('Schritt hinzufügen'); self.resize(560, 350)
        box = QVBoxLayout(self); self.action = QComboBox(); self.action.setAccessibleName('Aktion')
        for key, (title, _) in ACTIONS.items(): self.action.addItem(title, key)
        box.addWidget(self.action); self.form = QFormLayout(); box.addLayout(self.form)
        self.controls = {}; self.action.currentIndexChanged.connect(self.rebuild); self.rebuild()
        row = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        row.accepted.connect(self.accept); row.rejected.connect(self.reject); box.addWidget(row)

    def rebuild(self):
        while self.form.rowCount(): self.form.removeRow(0)
        self.controls = {}
        for key in ACTIONS[self.action.currentData()][1]:
            if key == 'text': control = QPlainTextEdit()
            elif key == 'scope':
                control = QComboBox(); control.addItem('Benutzer', 'user'); control.addItem('System (Authentifizierung)', 'system')
            else: control = QLineEdit()
            control.setAccessibleName(FIELDS[key]); self.form.addRow(FIELDS[key], control); self.controls[key] = control

    def step(self):
        return {'action': self.action.currentData(), **{key: control.toPlainText() if isinstance(control, QPlainTextEdit)
            else control.currentData() if isinstance(control, QComboBox) else control.text().strip()
            for key, control in self.controls.items()}}


class PlanDialog(QDialog):
    def __init__(self, parent, task=None, workflow=False):
        super().__init__(parent); self.setWindowTitle('Ablauf speichern' if workflow else 'Auftrag vorbereiten')
        self.resize(650, 680); self.workflow = workflow; self.value = None
        task = task or {}; box = QVBoxLayout(self); form = QFormLayout(); box.addLayout(form)
        self.name = QLineEdit(task.get('title', task.get('name', ''))); form.addRow('Name', self.name)
        self.prompt = QPlainTextEdit(task.get('prompt', '')); self.prompt.setMaximumHeight(90)
        self.prompt.setPlaceholderText('Optional: einen KI-Auftrag beschreiben. Ohne native Schritte wird er im Gespräch ausgeführt.')
        form.addRow('KI-Auftrag', self.prompt)
        self.roots = QListWidget(); self.roots.setMaximumHeight(85); form.addRow('Freigegebene Ordner', self.roots)
        for root in task.get('roots', []): add_item(self.roots, root, root)
        buttons(box, [('Ordner hinzufügen', self.add_root), ('Ordner entfernen', lambda: self.roots.takeItem(self.roots.currentRow()))])
        box.addWidget(QLabel('Native Schritte werden in dieser Reihenfolge ausgeführt.'))
        self.steps = QListWidget(); box.addWidget(self.steps)
        self.step_preview = QPlainTextEdit(); self.step_preview.setReadOnly(True)
        self.step_preview.setAccessibleName('Vollständiger ausgewählter Schritt'); box.addWidget(self.step_preview)
        self.steps.currentItemChanged.connect(lambda current, previous: self.step_preview.setPlainText(
            json.dumps(current.data(Qt.UserRole), ensure_ascii=False, indent=2) if current else ''))
        for step in task.get('steps', []): self.add_step_item(step)
        buttons(box, [('Schritt hinzufügen', self.add_step), ('Schritt entfernen', lambda: self.steps.takeItem(self.steps.currentRow()))])
        self.trigger = QComboBox()
        for title, key in [('Manuell', 'manual'), ('Regelmäßig', 'interval'), ('Bei Ordneränderung', 'directory')]: self.trigger.addItem(title, key)
        self.interval = QSpinBox(); self.interval.setRange(1, 525600); self.interval.setValue(60); self.interval.setSuffix(' Minuten')
        self.watch = QComboBox(); self.watch.setAccessibleName('Beobachteter Ordner')
        self.enable = QCheckBox('Automatischen Ablauf aktivieren')
        if workflow:
            form.addRow('Auslöser', self.trigger); form.addRow('Intervall / Prüfintervall', self.interval)
            form.addRow('Beobachteter Ordner', self.watch); box.addWidget(self.enable)
            box.addWidget(QLabel('Ordnerauslöser erkennen Änderungen an direkten Einträgen.\nKI-Aufträge und Desktop-/Systemaktionen warten auf Lumen im Vordergrund.'))
        self.approve = QCheckBox('Diese Schritte und Ordner freigeben'); box.addWidget(self.approve)
        self.approve.setToolTip('Freigabe gilt für genau diese gespeicherten Schritte. KI-Werkzeuge behalten ihre eigenen Rückfragen.')
        self.error = QLabel(); self.error.setWordWrap(True); box.addWidget(self.error)
        row = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        row.accepted.connect(self.save); row.rejected.connect(self.reject); box.addWidget(row); self.refresh_roots()

    def add_root(self):
        path = QFileDialog.getExistingDirectory(self, 'Ordner freigeben')
        if path: add_item(self.roots, path, path); self.refresh_roots()

    def refresh_roots(self):
        self.watch.clear()
        for i in range(self.roots.count()): self.watch.addItem(self.roots.item(i).text())

    def add_step_item(self, step):
        summary = ACTIONS[step['action']][0] + '\n' + ', '.join(f'{FIELDS[k]}: {v}' for k, v in step.items() if k not in ('action', 'text'))
        if 'text' in step: summary += '\n' + step['text'][:300]
        add_item(self.steps, summary, step)
        self.steps.setCurrentRow(self.steps.count()-1)

    def add_step(self):
        dialog = StepDialog(self)
        if dialog.exec_():
            from lumen_actions import validate_steps
            try: step = dialog.step(); validate_steps([step]); self.add_step_item(step)
            except ValueError as exc: self.error.setText(str(exc))

    def save(self):
        roots = [self.roots.item(i).data(Qt.UserRole) for i in range(self.roots.count())]
        steps = [self.steps.item(i).data(Qt.UserRole) for i in range(self.steps.count())]
        prompt = self.prompt.toPlainText().strip()
        if not self.name.text().strip() or not roots or not (steps or prompt) or not self.approve.isChecked():
            self.error.setText('Name, mindestens ein Ordner, Schritte oder KI-Auftrag und deine Freigabe sind erforderlich.'); return
        if steps and prompt:
            self.error.setText('Bitte native Schritte oder einen KI-Auftrag verwenden; beide können getrennte Abläufe sein.'); return
        self.value = dict(name=self.name.text().strip(), roots=roots, steps=steps, prompt=prompt,
                          trigger=self.trigger.currentData(), interval=self.interval.value()*60,
                          watch=self.watch.currentText() if self.trigger.currentData() == 'directory' else '',
                          enabled=self.enable.isChecked(), approved=True)
        self.accept()


class Indexer(QThread):
    outcome = pyqtSignal(str)
    def __init__(self, store, root, parent):
        super().__init__(parent); self.store = store; self.root = root
    def run(self):
        try:
            result = index_root(self.store, self.root, self.isInterruptionRequested)
            self.outcome.emit(f"{result['documents']} Dokumente aufgenommen; {result['errors']} nicht lesbar." +
                              (' Größenlimit erreicht; kleinere Ordner wählen.' if result['limited'] else ''))
        except Exception as exc: self.outcome.emit(str(exc))


class Workspace(QObject):
    def __init__(self, window):
        super().__init__(window); self.window = window; self.store = window.chat.tracker.store
        self.store.recover(); self.processes = []; self.indexer = None; self.task_signature = None
        self.tasks_page = self.build_tasks(); self.flows_page = self.build_flows()
        self.knowledge_page = self.build_knowledge(); self.models_page = self.build_models()
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh_tasks); self.timer.start(1500)
        self.refresh_tasks(); self.refresh_flows(); self.refresh_knowledge()

    def guarded(self, fn):
        def call(*_):
            try: fn()
            except Exception as exc: QMessageBox.warning(self.window, 'Lumen', str(exc))
        return call

    def build_tasks(self):
        widget, box = page('Aufträge', 'Aufträge bleiben nach einem Neustart erhalten. Unterbrochene Schritte vor dem Fortsetzen prüfen.')
        split = QSplitter(); self.tasks = QListWidget(); self.tasks.setAccessibleName('Gespeicherte Aufträge')
        self.detail = QPlainTextEdit(); self.detail.setReadOnly(True); self.detail.setAccessibleName('Auftrag, Ergebnis und Verlauf')
        split.addWidget(self.tasks); split.addWidget(self.detail); split.setStretchFactor(1, 2); box.addWidget(split, 1)
        self.tasks.currentItemChanged.connect(self.show_task)
        buttons(box, [('Neuer Auftrag', self.guarded(self.new_task)), ('Ausführen / Fortsetzen', self.guarded(self.run_task)),
                      ('Pausieren', self.guarded(lambda: self.stop_task('paused'))), ('Abbrechen', self.guarded(lambda: self.stop_task('cancelled')))])
        buttons(box, [('Als Ablauf speichern', self.guarded(self.task_to_flow)), ('Ergebnis speichern', self.guarded(self.export_task)),
                      ('Änderung rückgängig', self.guarded(self.undo_change))])
        return widget

    def refresh_tasks(self):
        rows = self.store.tasks(); signature = [(r['id'], r['status'], r['updated']) for r in rows]
        if signature == self.task_signature: return
        previous = self.tasks.currentItem().data(Qt.UserRole) if self.tasks.currentItem() else None
        self.task_signature = signature; self.tasks.clear()
        for row in rows:
            add_item(self.tasks, f"{STATES.get(row['status'], row['status'])} · {row['title']}", row['id'])
            if row['id'] == previous: self.tasks.setCurrentRow(self.tasks.count()-1)
        if self.tasks.currentRow() < 0 and self.tasks.count(): self.tasks.setCurrentRow(0)

    def show_task(self, *_):
        if not self.tasks.currentItem(): self.detail.clear(); return
        task = self.store.task(selected(self.tasks)); events = self.store.events(task['id'])
        content = [task['title'], STATES.get(task['status'], task['status']), 'Arbeitsordner: ' + task['directory'],
                   'Fortschritt: ' + str(task['cursor']) + '/' + str(len(task['steps'])) if task['steps'] else '',
                   'Freigegebene Ordner: ' + ', '.join(task['roots']),
                   'Schritte: ' + json.dumps(task['steps'], ensure_ascii=False, indent=2) if task['steps'] else '',
                   task['prompt'], task['error'], task['result'], '\nVerlauf:']
        content += [e['kind'] + ': ' + e['detail'] for e in events if e['kind'] != 'input']
        self.detail.setPlainText('\n\n'.join(part for part in content if part))

    def new_task(self):
        dialog = PlanDialog(self.window, {'roots': [self.window.chat.backend.directory]})
        if dialog.exec_():
            value = dialog.value
            task = self.store.create_task(value['name'], prompt=value['prompt'], roots=value['roots'],
                directory=value['roots'][0], steps=value['steps'], approved=True)
            self.store.event(task, 'approved', 'Schritte und Ordner im Lumen-Dialog freigegeben.'); self.refresh_tasks()

    def run_task(self):
        task = self.store.task(selected(self.tasks))
        if task['status'] in ('completed', 'running', 'cancelled'): raise ValueError('Dieser Auftrag kann nicht fortgesetzt werden.')
        if not task['approved'] and task['steps']:
            dialog = PlanDialog(self.window, task)
            if not dialog.exec_(): return
            value = dialog.value
            replacement = self.store.create_task(value['name'], prompt=value['prompt'], directory=value['roots'][0], roots=value['roots'], steps=value['steps'], approved=True)
            self.store.update_task(task['id'], status='cancelled')
            self.store.event(replacement, 'approved', 'Geprüfter Entwurf ' + task['id'])
            task = self.store.task(replacement)
        if task['status'] in ('interrupted', 'failed') and QMessageBox.question(self.window, 'Letzten Schritt prüfen',
            'Der letzte Schritt könnte bereits teilweise ausgeführt worden sein. Verlauf und Ergebnis geprüft und Wiederholung freigegeben?') != QMessageBox.Yes: return
        if task['steps']:
            self.start_process([str(Path(__file__).with_name('lumen_tasks.py')), '--task', task['id']])
        else:
            self.window.chat.tracker.resume(task['id'], self.window.chat); self.window.show_page(0)
        self.refresh_tasks()

    def stop_task(self, state):
        task = self.store.task(selected(self.tasks)); tracker = self.window.chat.tracker
        if task['status'] in ('completed', 'cancelled'): return
        if tracker.task_id == task['id'] and tracker.backend.busy:
            tracker.pause() if state == 'paused' else tracker.backend.stop()
        else:
            self.store.update_task(task['id'], status=state)
            self.store.event(task['id'], state, 'Angefordert. Ein bereits laufender nativer Schritt wird noch beendet.')
        self.refresh_tasks()

    def start_process(self, args):
        process = QProcess(self); self.processes.append(process)
        process.setProcessChannelMode(QProcess.MergedChannels)
        def done(code):
            output = bytes(process.readAllStandardOutput()).decode(errors='replace')
            if code and output: QMessageBox.warning(self.window, 'Auftrag fehlgeschlagen', output[-2000:])
            self.processes.remove(process); process.deleteLater(); self.refresh_tasks()
        process.finished.connect(done)
        process.errorOccurred.connect(lambda _: self.window.chat.show_error('Auftragsprozess konnte nicht gestartet werden.'))
        process.start(sys.executable, args)

    def task_to_flow(self):
        task = self.store.task(selected(self.tasks)); self.flow_dialog(task)

    def export_task(self):
        task = self.store.task(selected(self.tasks))
        if not task['result']: raise ValueError('Dieser Auftrag hat noch kein Ergebnis.')
        path, _ = QFileDialog.getSaveFileName(self.window, 'Ergebnis speichern', task['directory'] + '/lumen-ergebnis.md', 'Markdown (*.md);;Text (*.txt)')
        if not path: return
        target = Path(path); step = {'action': 'write', 'path': str(target), 'text': task['result']}
        job = self.store.create_task('Ergebnis: ' + task['title'][:180], directory=str(target.parent), roots=[str(target.parent)], steps=[step], approved=True)
        from lumen_tasks import run_steps
        run_steps(self.store, job); self.refresh_tasks()

    def undo_change(self):
        task = selected(self.tasks); changes = [r for r in self.store.changes(task) if r['status'] in ('applied', 'pending')]
        if not changes: raise ValueError('Keine rücknehmbaren nativen Dateiänderungen vorhanden.')
        titles = [r['path'] + ' · ' + r['id'][:8] for r in changes]
        choice, ok = QInputDialog.getItem(self.window, 'Änderung rückgängig', 'Datei', titles, 0, False)
        if ok: undo(self.store, changes[titles.index(choice)]['id']); self.show_task()

    def build_flows(self):
        widget, box = page('Abläufe', 'Gespeicherte Schritte lassen sich wiederholen. Zeit- und Ordnerauslöser laufen nur mit aktivierter Hintergrundprüfung.')
        self.flows = QListWidget(); self.flows.setAccessibleName('Wiederverwendbare Abläufe'); box.addWidget(self.flows, 1)
        buttons(box, [('Neuer Ablauf', self.guarded(lambda: self.flow_dialog())), ('Jetzt starten', self.guarded(self.run_flow)),
                      ('Aktivieren / Pausieren', self.guarded(self.toggle_flow)), ('Entfernen', self.guarded(self.remove_flow))])
        self.timer_status = QLabel(); self.timer_status.setWordWrap(True); box.addWidget(self.timer_status)
        buttons(box, [('Hintergrundprüfung aktivieren', self.guarded(lambda: self.set_timer(True))),
                      ('Hintergrundprüfung stoppen', self.guarded(lambda: self.set_timer(False))), ('Jetzt prüfen', self.guarded(self.tick))])
        return widget

    def flow_dialog(self, task=None):
        dialog = PlanDialog(self.window, task or {'roots': [self.window.chat.backend.directory]}, workflow=True)
        if dialog.exec_(): self.store.save_workflow(**dialog.value); self.refresh_flows()

    def refresh_flows(self):
        self.flows.clear()
        for flow in self.store.workflows():
            add_item(self.flows, flow['name'] + ' · ' + ('aktiv' if flow['enabled'] else 'manuell / pausiert') +
                     ' · ' + {'manual': 'manuell', 'interval': 'Zeitplan', 'directory': 'Ordneränderung'}[flow['trigger']], flow)
        self.timer_status.setText('Die Benutzer-Timer prüfen einmal pro Minute. Laufende Schritte werden bei Pause zu Ende geführt.')

    def run_flow(self):
        flow = selected(self.flows)
        if not flow['approved']: raise PermissionError('Ablauf ist nicht freigegeben. Neu speichern.')
        task = self.store.create_task(flow['name'], prompt=flow['prompt'], directory=flow['roots'][0], roots=flow['roots'], steps=flow['steps'], approved=True)
        self.store.event(task, 'workflow', flow['id']); self.refresh_tasks()
        for i in range(self.tasks.count()):
            if self.tasks.item(i).data(Qt.UserRole) == task: self.tasks.setCurrentRow(i)
        self.window.show_page(4); self.run_task()

    def toggle_flow(self):
        flow = selected(self.flows); self.store.set_workflow_enabled(flow['id'], not flow['enabled']); self.refresh_flows()

    def remove_flow(self):
        flow = selected(self.flows)
        with self.store.connect() as db: db.execute('DELETE FROM workflows WHERE id=?', (flow['id'],))
        self.refresh_flows()

    def set_timer(self, enabled):
        from lumen_actions import command
        command(['systemctl', '--user', 'enable' if enabled else 'disable', '--now', 'lumen-jobs.timer'])
        self.timer_status.setText('Hintergrundprüfung aktiv.' if enabled else 'Hintergrundprüfung gestoppt.')

    def tick(self): self.start_process([str(Path(__file__).with_name('lumen_tasks.py')), '--tick'])

    def build_knowledge(self):
        widget, box = page('Wissen', 'Nur ausgewählte Ordner werden lokal indexiert. Quellen werden erst mit „Im Gespräch verwenden“ an das gewählte Modell übergeben.')
        self.roots = QListWidget(); self.roots.setMaximumHeight(100); self.roots.setAccessibleName('Wissensordner'); box.addWidget(self.roots)
        buttons(box, [('Ordner aufnehmen', self.guarded(self.add_knowledge)), ('Neu indexieren', self.guarded(lambda: self.start_index(selected(self.roots)))),
                      ('Freigabe entfernen', self.guarded(self.remove_knowledge)), ('Indexierung stoppen', self.cancel_index)])
        self.index_status = QLabel(); self.index_status.setWordWrap(True); box.addWidget(self.index_status)
        self.query = QLineEdit(); self.query.setPlaceholderText('Dokumente durchsuchen …'); self.query.setAccessibleName('Wissenssuche')
        self.query.returnPressed.connect(self.guarded(self.search)); box.addWidget(self.query)
        self.results = QListWidget(); self.results.setAccessibleName('Dokumente mit Quellen'); box.addWidget(self.results, 1)
        buttons(box, [('Suchen', self.guarded(self.search)), ('Quelle öffnen', self.guarded(self.open_source)),
                      ('Im Gespräch verwenden', self.guarded(self.use_source))])
        box.addWidget(QLabel('Persönliche Erinnerungen — du bestimmst, was Lumen verwendet.'))
        self.memories = QListWidget(); self.memories.setMaximumHeight(130); self.memories.setAccessibleName('Erinnerungen'); box.addWidget(self.memories)
        buttons(box, [('Erinnerung hinzufügen', self.guarded(lambda: self.edit_memory())),
                      ('Bearbeiten', self.guarded(lambda: self.edit_memory(selected(self.memories)))),
                      ('Löschen', self.guarded(self.delete_memory)), ('Verwenden', self.guarded(self.use_memory))])
        return widget

    def refresh_knowledge(self):
        self.roots.clear(); self.memories.clear()
        for row in self.store.rows('SELECT * FROM roots ORDER BY path'): add_item(self.roots, row['path'], row['path'])
        for row in self.store.memories(): add_item(self.memories, row['title'] + ' — ' + row['text'][:100], row)

    def add_knowledge(self):
        root = QFileDialog.getExistingDirectory(self.window, 'Wissensordner freigeben')
        if root: self.start_index(root)

    def start_index(self, root):
        if self.indexer and self.indexer.isRunning(): raise ValueError('Die laufende Indexierung zuerst beenden.')
        self.index_status.setText('Indexierung läuft …'); self.indexer = Indexer(self.store, root, self)
        self.indexer.outcome.connect(self.index_status.setText)
        self.indexer.finished.connect(self.refresh_knowledge); self.indexer.start()

    def cancel_index(self):
        if self.indexer: self.indexer.requestInterruption()

    def remove_knowledge(self):
        if self.indexer and self.indexer.isRunning(): raise ValueError('Vor dem Entfernen die Indexierung beenden.')
        self.store.remove_root(selected(self.roots)); self.results.clear(); self.refresh_knowledge()

    def search(self):
        self.results.clear()
        for row in search(self.store, self.query.text()):
            add_item(self.results, f"{Path(row['path']).name} · Seite {row['page']}\n{row['snippet']}\n{row['path']}", row)

    def open_source(self): QDesktopServices.openUrl(QUrl.fromLocalFile(selected(self.results)['path']))

    def use_source(self):
        row = selected(self.results)
        self.to_chat(f"Quelle: {row['path']} (Seite {row['page']})\nAuszug: {row['snippet']}\n\n", [row['path']])

    def to_chat(self, text, paths=None):
        if self.window.chat.backend.busy: raise ValueError('Bitte den laufenden Auftrag zuerst pausieren.')
        self.window.chat.begin_context(paths=paths or [])
        self.window.chat.composer.setPlainText(text); self.window.show_page(0)

    def edit_memory(self, memory=None):
        memory = memory or {}; dialog = QDialog(self.window); dialog.setWindowTitle('Erinnerung'); dialog.resize(520, 380)
        form = QFormLayout(dialog); title = QLineEdit(memory.get('title', '')); content = QPlainTextEdit(memory.get('text', ''))
        source = QLineEdit(memory.get('source', 'Von mir')); form.addRow('Titel', title); form.addRow('Inhalt', content); form.addRow('Quelle', source)
        row = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); form.addRow(row)
        row.accepted.connect(dialog.accept); row.rejected.connect(dialog.reject)
        if dialog.exec_(): self.store.save_memory(title.text(), content.toPlainText(), source.text(), memory.get('id')); self.refresh_knowledge()

    def delete_memory(self): self.store.delete_memory(selected(self.memories)['id']); self.refresh_knowledge()
    def use_memory(self):
        memory = selected(self.memories); self.to_chat(f"Meine Erinnerung: {memory['title']}\n{memory['text']}\nQuelle: {memory['source']}\n\n")

    def build_models(self):
        widget, box = page('Modelle & Ressourcen', 'Wähle, welche Modelle Lumen verwenden darf. „Lokaler Dienst“ erzwingt eine Loopback-Adresse; dessen eigene Weiterleitungen bleiben dessen Verantwortung.')
        form = QFormLayout(); box.addLayout(form); policy = self.store.setting('modelPolicy', {})
        self.privacy = QComboBox(); self.privacy.addItem('Konfigurierte Anbieter (auch Cloud)', 'configured'); self.privacy.addItem('Nur lokaler Dienst', 'local')
        self.privacy.setCurrentIndex(1 if policy.get('privacy') == 'local' else 0); form.addRow('Verarbeitung', self.privacy)
        self.model_controls = {}
        for key, title in [('model', 'Standardmodell'), ('background_model', 'Modell für wiederkehrende KI-Aufträge'), ('local_model', 'Lokales Modell')]:
            control = QComboBox(); control.setEditable(True); control.addItem(policy.get(key, '')); control.setAccessibleName(title)
            form.addRow(title, control); self.model_controls[key] = control
        self.timeout = QSpinBox(); self.timeout.setRange(1, 120); self.timeout.setValue(int(policy.get('timeout_seconds', 900))//60); self.timeout.setSuffix(' Minuten'); form.addRow('Zeitlimit pro KI-Auftrag', self.timeout)
        self.gpu = QSpinBox(); self.gpu.setRange(1,100); self.gpu.setValue(int(policy.get('gpu_limit',90))); self.gpu.setSuffix(' %'); form.addRow('Hintergrundarbeit pausiert ab GPU-Auslastung', self.gpu)
        self.pause_background = QCheckBox('Alle Hintergrundaufträge pausieren'); self.pause_background.setChecked(policy.get('pause_background',False)); box.addWidget(self.pause_background)
        self.model_status = QLabel('GPU-Prüfung verwendet NVIDIA-SMI, wenn verfügbar. 100 % deaktiviert die GPU-Grenze.'); self.model_status.setWordWrap(True); box.addWidget(self.model_status)
        buttons(box, [('Verfügbare Modelle laden', self.load_models), ('Speichern', self.guarded(self.save_models))]); box.addStretch(); return widget

    def load_models(self):
        backend = self.window.chat.backend
        def loaded(data):
            names = [p['id'] + '/' + model for p in data.get('providers', []) for model in p.get('models', {})]
            for control in self.model_controls.values():
                old = control.currentText(); control.clear(); control.addItem(''); control.addItems(names); control.setCurrentText(old)
            self.model_status.setText(f'{len(names)} Modelle verfügbar. Lokale Anbieter in den Verbindungseinstellungen konfigurieren.')
        backend.ensure_server(lambda: backend.request('GET','/config/providers',callback=loaded))

    def save_models(self):
        policy = {key: c.currentText().strip() for key,c in self.model_controls.items()}
        if self.privacy.currentData() == 'local' and '/' not in policy['local_model']: raise ValueError('Lokales Modell als anbieter/modell auswählen.')
        policy.update(privacy=self.privacy.currentData(),timeout_seconds=self.timeout.value()*60,gpu_limit=self.gpu.value(),pause_background=self.pause_background.isChecked())
        self.store.set_setting('modelPolicy',policy)
        self.window.chat.settings.setValue('model', policy['model']); self.window.chat.settings.sync()
        self.model_status.setText('Gespeichert. Die Richtlinie gilt ab dem nächsten Auftrag.')

    def can_close(self):
        if any(p.state() != QProcess.NotRunning for p in self.processes):
            QMessageBox.information(self.window, 'Auftrag läuft', 'Bitte den laufenden nativen Schritt beenden lassen.'); return False
        if self.indexer and self.indexer.isRunning():
            self.indexer.requestInterruption(); self.indexer.wait(5000)
            if self.indexer.isRunning(): return False
        return True
