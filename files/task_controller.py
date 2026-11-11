"""Controller of the task page: list, inspector, execution and results of durable Lumen tasks."""
from lumen_i18n import worker_process, tr
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QProcess, QTimer, Qt, QEvent
from PySide6.QtWidgets import QFileDialog, QInputDialog, QLabel, QListWidgetItem, QMessageBox
from lumen_actions import undo
from lumen_store import Store, STATES
from plan_dialog import PlanDialog, add_item, selected, step_description


class TaskController(QObject):
    def __init__(self, window, store=None):
        super().__init__(window); self.window = window
        self.store = store or (window.chat.tracker.store if hasattr(window, 'chat') else Store())
        self.store.recover(); self.processes = []; self.task_signature = None; self.knowledge_job = None
        widget = self.build_tasks(); widget.setParent(window); self.tasks_page = widget
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh_tasks); self.timer.start(1500)
        self.refresh_tasks()

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
        self.knowledge_work('save_memory',title=task['title'],text=task['result'],source=tr('Lumen-Auftrag · ')+task['id'])

    def undo_change(self):
        task = selected(self.tasks); changes = [r for r in self.store.changes(task) if r['status'] in ('applied', 'pending')]
        if not changes: raise ValueError(tr('Keine rücknehmbaren nativen Dateiänderungen vorhanden.'))
        titles = [r['path'] + ' · ' + r['id'][:8] for r in changes]
        choice, ok = QInputDialog.getItem(self.window, tr('Änderung rückgängig'), tr('Datei'), titles, 0, False)
        if ok: undo(self.store, changes[titles.index(choice)]['id']); self.show_task()

    def knowledge_work(self,action,**values):
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
            if results and not job.cancelled.is_set():self.index_status.setText(tr('Notizordner aktualisiert.'))
        job.finished.connect(finished);job.start()

    def can_close(self):
        if any(p.state() != QProcess.NotRunning for p in self.processes):
            QMessageBox.information(self.window, tr('Auftrag läuft'), tr('Bitte den laufenden nativen Schritt beenden lassen.')); return False
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
