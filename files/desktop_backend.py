"""Explicit native server conversations over the existing paired-device bridge."""
import hashlib
import threading
from uuid import UUID, uuid4, uuid5
from urllib.error import HTTPError
from pathlib import Path
import os
import stat
import json

from PySide6.QtCore import QObject, Signal, Slot
from assistant_backend import OpenCodeBackend
from lumen_i18n import tr

# Daemon HTTP workers let a window/process close without cancelling the server job.
# The reply object stays alive until the worker finishes; Qt disconnects closed UIs.
_workers = set()


class Reply(QObject):
    result = Signal(object)
PREFIX = 'lumen-server/'
TERMINAL = {'completed', 'cancelled', 'failed', 'interrupted'}


def connection():
    from lumen_connect import read_config
    config = read_config()
    if not config.get('token'):
        raise ValueError('Not paired')
    binding = hashlib.sha256((config['server'] + '\0' + config['token']).encode()).hexdigest()[:24]
    return config, binding


def message_rows(rows):
    messages = []
    for row in rows:
        identity = str(row['id'])
        messages.append(dict(info=dict(id=identity, role='user'), parts=[dict(type='text', text=row['prompt'])]))
        if row.get('result'):
            messages.append(dict(info=dict(id=identity+'-answer', role='assistant', parentID=identity),
                                 parts=[dict(type='text', text=row['result'])]))
    return messages


class DesktopBackend(OpenCodeBackend):
    executionChanged = Signal()
    serverModelsChanged = Signal(object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.execution = 'local'
        self.server_model = ''
        self.prepared_context = []
        self.server_origin = ''
        self.binding = ''
        self.remote_active = False
        self.remote_key = ''
        self.cancel_requested = False
        self.submitting = False
        self.server_sessions = []
        self.server_cursor = None
        self.history_rows = []
        self.history_more = False

    def set_execution(self, target):
        if self.busy or target not in ('local', 'server'):
            return False
        if target == self.execution:
            return True
        if target == 'server':
            try:
                config, binding = connection()
            except (OSError, ValueError, KeyError):
                self.failed.emit(tr('Bitte Lumen Desktop zuerst mit einem Lumen Server verbinden.'))
                return False
            self.server_origin, self.binding = config['server'], binding
        self.shutdown()
        self.execution = target
        self.new_conversation()
        self.sessionsChanged.emit([])
        self.executionChanged.emit()
        self.refresh_sessions()
        if target == 'server': self._run('models', lambda request: request('/bridge/models'))
        return True

    def pending(self):
        self.settings.sync()
        prefix = 'serverRequests/' + self.binding + '/'
        return [key.removeprefix(prefix) for key in self.settings.allKeys() if key.startswith(prefix)]

    def remember(self, key, remove=False):
        name = 'serverRequests/' + self.binding + '/' + key
        if remove:
            self.settings.remove(name)
        else:
            self.settings.setValue(name, True)
        self.settings.sync()

    def identity(self):
        prefix = PREFIX + self.binding + '/'
        if not self.session.startswith(prefix):
            raise ValueError('Different server identity')
        return str(UUID(self.session.removeprefix(prefix)))

    def _run(self, operation, function):
        generation, binding = self.generation, self.binding
        submission = (binding, self.session, self.remote_key)
        origin = self.server_origin
        def work():
            try:
                from lumen_connect import request
                config, current = connection()
                if current != binding:
                    raise ValueError('Connection changed')
                result = function(lambda path, body=None: request(config, path, body))
                return generation, operation, result, False
            except HTTPError as error:
                rejected = operation == 'submit' and bool(submission[2]) and error.code == 413 and error.geturl() == origin + '/bridge/tasks'
                error.close()
                if rejected:
                    return generation, operation, dict(rejected_submission=submission, local_context_error=tr('Die gewählten Inhalte überschreiten das Serverlimit. Bitte weniger oder kleinere Quellen auswählen.')), False
                return generation, operation, None, True
            except Exception:
                # Never expose bearer headers, provider responses or credentials.
                return generation, operation, None, True
        reply = Reply()
        reply.result.connect(self._received)
        def deliver():
            try: reply.result.emit(work())
            finally:
                reply.deleteLater()
                _workers.discard(threading.current_thread())
        thread = threading.Thread(target=deliver, daemon=True)
        _workers.add(thread)
        thread.start()

    @Slot(object)
    def _received(self, response):
        try:
            self._apply_response(response)
        except (KeyError, ValueError, TypeError, AttributeError):
            generation, operation, _, _ = response
            self._apply_response((generation, operation, None, True))

    def _apply_response(self, response):
        generation, operation, data, error = response
        if generation != self.generation or self.execution != 'server':
            return
        if operation == 'submit':
            if not error and data.get('rejected_submission') is not None and data['rejected_submission'] != (self.binding, self.session, self.remote_key):
                return
            self.submitting = False
            if not error and data.get('local_context_error'):
                self.remember(self.remote_key,remove=True);self.remote_key='';self.remote_active=False
                self.polling=False;self.timer.stop();self.set_busy(False)
                self.failed.emit(data['local_context_error']);self.statusChanged.emit(tr('Auswahl verkleinern und erneut senden.'))
                return
        if error:
            if operation in ('models','approvals','approval_reply'):
                if operation=='models':self.serverModelsChanged.emit([])
                elif operation=='approval_reply':
                    self.permission_replies.clear()
                    self.failed.emit(tr('Freigabe nicht bestätigt. Serverstatus erneut prüfen.'))
                return
            if operation in ('sessions', 'sessions_more'):
                self.failed.emit(tr('Serververlauf konnte nicht geladen werden.'))
                return
            self.polling = False
            self.timer.stop()
            self.set_busy(False)
            self.failed.emit(tr('Server nicht erreichbar oder Zugriff nicht erlaubt. Verbindung prüfen; der Auftrag wurde nicht erneut gesendet.'))
            self.statusChanged.emit(tr('Serverstatus unbekannt · Verbindung prüfen'))
            return
        if operation == 'approvals':
            self.permissions=[dict(id=item['kind']+':'+str(item['id']),permission='server',patterns=[item.get('title',''),item.get('origin',''),item.get('operation',''),json.dumps(item.get('before',{}),ensure_ascii=False),json.dumps(item.get('body',''),ensure_ascii=False)]) for item in data]
            self.permission_replies.intersection_update(item['id'] for item in self.permissions)
            self.requestsChanged.emit([item for item in self.permissions if item['id'] not in self.permission_replies],[])
            return
        if operation == 'approval_reply':
            self.poll()
            return
        if operation == 'models':
            self.serverModelsChanged.emit(data['items'])
            return
        if operation == 'history_more':
            existing = {row['id'] for row in self.history_rows}
            self.history_rows = [row for row in data if row['id'] not in existing]+self.history_rows
            self.history_more = bool(self.history_rows and self.history_rows[0].get('parent_id'))
            self.messages = message_rows(self.history_rows)
            self.messagesChanged.emit(self.messages)
            self.refresh_sessions()
            return
        if operation in ('sessions', 'sessions_more'):
            sessions = [dict(id=PREFIX+self.binding+'/'+row['id'], title=row['title']) for row in data['items']]
            self.server_sessions = (self.server_sessions if operation == 'sessions_more' else []) + sessions
            self.server_cursor = data.get('next')
            sessions = self.server_sessions[:]
            if self.server_cursor: sessions.append(dict(id=PREFIX+self.binding+'/more/'+self.server_cursor,title=tr('Weitere Gespräche laden')))
            if self.session and self.history_more: sessions.append(dict(id=PREFIX+self.binding+'/history',title=tr('Ältere Nachrichten laden')))
            sessions += [dict(id=PREFIX+self.binding+'/pending/'+key, title=tr('Übermittlung prüfen')) for key in self.pending()]
            self.sessionsChanged.emit(sessions)
            return
        if operation == 'submit' or operation == 'receipt':
            self.polling = False
            if data is None:
                self.set_busy(False)
                self.statusChanged.emit(tr('Noch keine Serverbestätigung. Verbindung erneut prüfen oder ein neues Gespräch beginnen.'))
                return
            if self.remote_key:
                self.remember(self.remote_key, remove=True)
            self.remote_key = ''
            self.session = PREFIX+self.binding+'/'+str(data['id'])
            self.sessionChanged.emit(self.session)
            self.polling = False
            self.poll()
            return
        self.polling = False
        row, history = data
        self.message_id = str(row['id'])
        latest = {item['id'] for item in history}
        self.history_rows = [item for item in self.history_rows if item['id'] not in latest]+history
        self.history_more = bool(self.history_rows and self.history_rows[0].get('parent_id'))
        self.messages = message_rows(self.history_rows)
        self.messagesChanged.emit(self.messages)
        state = row['state']
        if state in TERMINAL or state=='waiting_approval':
            self._run('approvals', lambda request: request('/bridge/tasks/'+str(row['id'])+'/approvals'))
        if state in TERMINAL:
            was_active = self.remote_active
            self.remote_active = False
            self.cancel_requested = False
            self.set_busy(False)
            self.timer.stop()
            self.statusChanged.emit(tr('Server · Abgeschlossen') if state == 'completed' else tr('Server · Auftrag beendet'))
            if was_active:
                result = row.get('result', '') if state == 'completed' else ('Abgebrochen' if state == 'cancelled' else row.get('error') or tr('Serverauftrag fehlgeschlagen. Details im Server öffnen.'))
                if state in ('failed', 'interrupted'):
                    self.failed.emit(result)
                self.completed.emit(state == 'completed', result)
            self.refresh_sessions()
        elif self.cancel_requested and operation != 'cancel':
            self._cancel()
        else:
            self.remote_active = True
            self.set_busy(True)
            self.statusChanged.emit(tr('Server · Freigabe im Server erforderlich') if state == 'waiting_approval' else tr('Server · Lumen arbeitet …'))
            self.timer.start(1200)

    def new_conversation(self, directory=None):
        if not super().new_conversation(directory):
            return False
        self.remote_active = False
        self.remote_key = ''
        self.cancel_requested = False
        self.history_rows = []
        self.history_more = False
        return True

    def select_session(self, session):
        prefix = PREFIX+self.binding+'/'
        if self.execution == 'server' and session.startswith(prefix+'more/'):
            cursor = str(UUID(session.removeprefix(prefix+'more/')))
            self._run('sessions_more', lambda request: request('/bridge/conversations?before='+cursor))
            return
        if self.execution == 'server' and session == prefix+'history':
            if self.history_rows and self.history_more:
                identity = str(UUID(self.history_rows[0]['parent_id']))
                self._run('history_more', lambda request: request('/bridge/tasks/'+identity+'/history'))
            return
        self.history_rows = []
        self.history_more = False
        if not session.startswith(PREFIX):
            if self.execution != 'local' and not self.set_execution('local'):
                return
            return super().select_session(session)
        if self.execution != 'server' and not self.set_execution('server'):
            return
        if not self.new_conversation():
            return
        prefix = PREFIX+self.binding+'/'
        if not session.startswith(prefix):
            self.failed.emit(tr('Dieses Gespräch gehört zu einer anderen Serververbindung.'))
            return
        self.session = session
        self.sessionChanged.emit(session)
        if session.startswith(prefix+'pending/'):
            try: self.remote_key = str(UUID(session.removeprefix(prefix+'pending/')))
            except ValueError: return
        self.remote_active = True
        self.set_busy(True)
        self.poll()

    def refresh_sessions(self):
        if self.execution == 'local':
            return super().refresh_sessions()
        self._run('sessions', lambda request: request('/bridge/conversations'))

    def preflight(self, paths=False):
        if self.execution != 'server':
            return True
        self.prepared_context = []
        if paths:
            try:
                if not isinstance(paths, (list,tuple)) or len(paths)>20: raise ValueError('Invalid context')
                total=0
                for value in paths:
                    path=Path(value[0] if isinstance(value,tuple) else value)
                    if path.suffix.lower() not in ('.txt','.md','.json','.csv','.log','.py','.js','.ts','.yaml','.yml','.toml'):
                        raise ValueError('Unsupported context format')
                    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                    with os.fdopen(fd,'rb') as stream:
                        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('Not a file')
                        raw=stream.read(60001)
                    total+=len(raw)
                    if total>60000:raise ValueError('Context too large')
                    self.prepared_context.append(dict(name=path.name[:180],text=raw.decode('utf-8')))
            except (OSError,ValueError,TypeError):
                self.prepared_context=[]
                self.failed.emit(tr('Für den Server bitte UTF-8-Textdateien bis insgesamt 60 KB auswählen. Andere Anhänge bleiben lokal.'))
                return False
        if self.remote_active or self.remote_key:
            self.failed.emit(tr('Den letzten Serverauftrag zuerst prüfen oder ein neues Gespräch beginnen.'))
            return False
        return True

    def send(self, text, files=None, *args, **kwargs):
        if self.session.startswith(PREFIX) and self.execution != 'server':
            # Recovery snapshots may set session directly. Never pass a server
            # identity to the local OpenCode process or silently change provider.
            self.failed.emit(tr('Das Servergespräch bitte im Serververlauf erneut öffnen.'))
            return False
        if self.execution != 'server':
            return super().send(text, files, *args, **kwargs)
        if self.busy or not text.strip() or not self.preflight(files or kwargs.get('screen_image')):
            return False
        if len(text) > 20000 or kwargs.get('proposal') or kwargs.get('project_task'):
            self.failed.emit(tr('Dieser Auftrag wird in Servergesprächen noch nicht unterstützt.'))
            return False
        try:
            parent = self.identity() if self.session else None
        except ValueError:
            self.failed.emit(tr('Dieses Gespräch gehört zu einer anderen Serververbindung.'))
            return False
        self.remote_key = str(uuid4())
        self.remember(self.remote_key)
        body = dict(prompt=text, parent_id=parent, idempotency_key=self.remote_key)
        if self.server_model: body['model']=self.server_model
        context = list(self.prepared_context)
        drive_refs=(kwargs.get('context_data') or {}).get('drive_references',[])
        if drive_refs:
            from drive_references import validate
            try:drive_refs=[validate(ref) for ref in drive_refs]
            except (ValueError,TypeError,KeyError):
                self.remember(self.remote_key,remove=True);self.remote_key=''
                self.failed.emit(tr('Die Drive-Auswahl ist ungültig. Bitte erneut auswählen.'));return False
        if kwargs.get('context_data'):
            encoded=json.dumps(kwargs['context_data'],ensure_ascii=False)
            if len(encoded.encode())+sum(len(item['text'].encode()) for item in context)>60000:
                self.remember(self.remote_key,remove=True);self.remote_key=''
                self.failed.emit(tr('Der ausgewählte Kontext ist zu groß.'));return False
            context.append(dict(name='Ausgewählte Eingaben.json',text=encoded))
        if len(context)+sum(ref['kind']=='drive_file' for ref in drive_refs)>20:
            self.remember(self.remote_key,remove=True);self.remote_key=''
            self.failed.emit(tr('Ein Servergespräch unterstützt höchstens 20 Anhänge einschließlich Auswahlbeschreibung. Bitte weniger Dateien auswählen.'));return False
        receipt = UUID(self.remote_key)
        self.remote_active = True
        self.set_busy(True)
        self.statusChanged.emit(tr('Server · Auftrag wird übergeben …'))
        self.messages.append(dict(info=dict(role='user'), parts=[dict(type='text', text=text)]))
        self.messagesChanged.emit(self.messages)
        def submit(request):
            user = request('/bridge/me')
            refs=[]
            if drive_refs:
                from drive_references import task_attachments,ContextLimit
                try:config,refs=task_attachments(drive_refs,(kwargs.get('context_data') or {}).get('intent','open'),sum(len(item['text'].encode()) for item in context))
                except ContextLimit as exc:return dict(local_context_error=str(exc))
                if config['server']!=self.server_origin or any(ref['locator']['account']!=user['id'] for ref in drive_refs) or connection()[1]!=self.binding:
                    raise ValueError('Connection changed')
            for index,item in enumerate(context):
                file=request('/bridge/context-files/'+str(uuid5(receipt,str(index))),item)
                refs.append(dict(id=file['id'],kind='file',revision=file['version']))
            if drive_refs and connection()[1]!=self.binding:raise ValueError('Connection changed')
            return request('/bridge/tasks', dict(body, attachments=refs))
        self.submitting = True
        self._run('submit', submit)
        return True

    def poll(self):
        if self.execution == 'local':
            return super().poll()
        if self.polling or self.submitting:
            return
        if self.remote_key:
            key = self.remote_key
            self.polling = True
            self._run('receipt', lambda request: request('/bridge/task-receipts/'+key))
        elif self.session:
            try: identity = self.identity()
            except ValueError:
                self.failed.emit(tr('Dieses Gespräch gehört zu einer anderen Serververbindung.')); return
            self.polling = True
            self._run('poll', lambda request: (request('/bridge/tasks/'+identity), request('/bridge/tasks/'+identity+'/history')))
        else:
            self.refresh_sessions()

    def permission_reply(self, request_id, allow):
        if self.execution != 'server':return super().permission_reply(request_id,allow)
        if request_id in self.permission_replies or not any(item['id']==request_id for item in self.permissions):return
        kind,identity=request_id.split(':',1);identity=str(UUID(identity))
        self.permission_replies.add(request_id)
        task=self.identity()
        self._run('approval_reply',lambda request:request('/bridge/tasks/'+task+'/approvals/'+kind+'/'+identity,dict(allow=bool(allow))))

    def _cancel(self):
        identity = self.identity()
        self._run('cancel', lambda request: (request('/bridge/tasks/'+identity+'/cancel', {}), request('/bridge/tasks/'+identity+'/history')))

    def stop(self):
        if self.execution == 'local':
            return super().stop()
        self.cancel_requested = True
        self.statusChanged.emit(tr('Server · Abbruch angefordert …'))
        if self.submitting:
            return
        if not self.polling and self.session and not self.remote_key:
            self._cancel()
        elif not self.polling:
            self.poll()
