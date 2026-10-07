"""Persist native-engine tasks without owning the engine or changing approvals."""
from lumen_i18n import tr
import json
import os
from pathlib import Path
from lumen_qt import QObject, Signal
from lumen_store import Store


class TaskTracker(QObject):
    changed = Signal()

    def __init__(self, backend, parent=None, store=None):
        super().__init__(parent)
        self.store = store or Store()
        self.backend = backend
        self.lease = None
        self.task_id = ''
        self.resume_id = ''
        self.stop_status = 'cancelled'
        backend.started.connect(self.started)
        backend.sessionChanged.connect(self.session_changed)
        backend.completed.connect(self.finished)
        backend.requestsChanged.connect(self.requests)

    def started(self, text, files, agent):
        self.backend.tracking_error = ''
        try: self._started(text, files, agent)
        except Exception as exc:
            self.backend.tracking_error = tr('Auftrag konnte nicht gesichert werden: ') + str(exc)
            if self.lease is not None: os.close(self.lease); self.lease = None
            self.task_id = self.resume_id = ''

    def _started(self, text, files, agent):
        self.backend.model_policy = self.store.setting('modelPolicy', {})
        if self.resume_id:
            self.task_id, self.resume_id = self.resume_id, ''
            self.lease = self.store.acquire(self.task_id)
            self.store.update_task(self.task_id, status='running', error='')
        else:
            self.task_id = self.store.create_task(text.splitlines()[0][:200], prompt=text,
                directory=self.backend.directory, roots=[self.backend.directory])
            self.lease = self.store.acquire(self.task_id)
            self.store.update_task(self.task_id, status='running')
        self.store.event(self.task_id, 'input', json.dumps({'files': files, 'agent': agent}, ensure_ascii=False))
        self.stop_status = 'cancelled'
        self.changed.emit()

    def session_changed(self, session):
        if self.task_id and self.lease is not None and session: self.store.update_task(self.task_id, session=session)

    def requests(self, permissions, questions):
        if self.task_id and self.backend.busy:
            self.store.update_task(self.task_id, status='needs_input' if permissions or questions else 'running')
            self.changed.emit()

    def finished(self, success, result):
        if not self.task_id or self.lease is None: return
        state = 'completed' if success else self.stop_status if result == 'Abgebrochen' else 'failed'
        self.store.update_task(self.task_id, status=state, result=result,
                               error='' if success or state in ('paused', 'cancelled') else result)
        self.store.event(self.task_id, state, result)
        if self.lease is not None:
            os.close(self.lease); self.lease = None
        self.changed.emit()

    def pause(self):
        self.stop_status = 'paused'
        self.backend.stop()

    def interrupt(self):
        if self.task_id and self.backend.busy:
            self.store.update_task(self.task_id, status='interrupted', error=tr('Lumen wurde während der Ausführung geschlossen.'))
            if self.lease is not None:
                os.close(self.lease); self.lease = None
            self.changed.emit()

    def resume(self, task_id, panel):
        if self.backend.busy: raise ValueError(tr('Bitte den laufenden Auftrag zuerst pausieren.'))
        task = self.store.task(task_id)
        if task['steps']: raise ValueError(tr('Diesen Ablauf über „Ausführen“ starten.'))
        if task['status'] == 'completed': raise ValueError(tr('Dieser Auftrag ist bereits abgeschlossen.'))
        if not Path(task['directory']).is_dir(): raise ValueError(tr('Der Arbeitsordner ist nicht mehr erreichbar.'))
        self.backend.new_conversation(task['directory'])
        self.backend.session = task['session']
        self.resume_id = task_id
        self.backend.background_task = any(e['kind'] == 'workflow' for e in self.store.events(task_id))
        events = [json.loads(e['detail']) for e in self.store.events(task_id) if e['kind'] == 'input']
        previous = events[-1] if events else {'files': [], 'agent': 'build'}
        prompt = (tr('Setze den unterbrochenen Auftrag fort. Prüfe zuerst, welche Schritte bereits erledigt sind, und wiederhole keine bereits bestätigten Änderungen.\n\n') + task['prompt'])
        panel.set_action('')
        self.backend.send(prompt, previous['files'], agent=previous['agent'])
