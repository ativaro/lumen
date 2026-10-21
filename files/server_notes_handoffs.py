"""Reviewed native Notes handoffs; Server owns the actual notebook and editor."""
from collections import deque
import time
from uuid import UUID

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QMessageBox
from interop_data import Registry, TOKEN
from interop_dialogs import run_job
from interop_ui import review
from lumen_activation import present
from lumen_i18n import tr
from server_app_session import SessionError
from server_note_capture import capture, collections


class Requests(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window=window;self.pending=deque();self.busy=False;self.reviewing=False;self.serial=0
        self.timer=QTimer(self);self.timer.setInterval(200);self.timer.timeout.connect(self.next)

    def activate(self, request):
        present(self.window)
        if not request:return
        if not isinstance(request,dict) or len(request)!=1 or len(self.pending)>=16:
            raise ValueError(tr('Die Übergabe ist ungültig oder noch nicht abgeschlossen.'))
        key,value=next(iter(request.items()))
        if key=='reference':
            self.window.session.binding.reference_url(Registry().resolve(value))
        elif key=='save_task' and self.window._binding.app=='code':
            if not isinstance(value,str) or value not in (str(UUID(value)),UUID(value).hex):raise ValueError(tr('Ungültiger Auftrag.'))
        elif key=='mode' and self.window._binding.app=='audio':
            if value not in ('meeting','radio'):raise ValueError(tr('Ungültige Audioansicht.'))
        elif key!='handoff' or self.window._binding.app not in ('notes','projects','audio') or not isinstance(value,str) or not TOKEN.fullmatch(value):
            raise ValueError(tr('Ungültige Notizübergabe.'))
        self.pending.append((dict(request),time.monotonic()+30))
        if not self.reviewing:self.timer.start()

    def next(self):
        w=self.window
        if self.reviewing:return
        if w._disposed or w._closing:self.timer.stop();return
        if not self.pending:self.timer.stop();return
        request,deadline=self.pending[0]
        if time.monotonic()>deadline:
            self.serial+=1;self.busy=False;self.pending.popleft()
            QMessageBox.warning(w,w._app_title,tr('Der Inhalt konnte noch nicht geöffnet werden. '
                'Serververbindung prüfen und die Übergabe anschließend erneut öffnen.'))
            return
        if self.busy or not w._loaded or not w._live or not w.session.usable or w._worker is not None:return
        self.busy=True;self.serial+=1;serial=self.serial
        try:
            if 'mode' in request:
                import json
                value=json.dumps(request['mode'])
                from server_app_window import QWebEngineScript
                def selected(accepted):
                    if self.serial!=serial:return
                    self.busy=False
                    if accepted is not None:self.pending.popleft()
                w.page.runJavaScript("window.__lumenAudioMode?.("+value+") ?? null",QWebEngineScript.ScriptWorldId.MainWorld,selected)
                return
            if 'handoff' in request or 'save_task' in request:
                self.timer.stop();self.reviewing=True
                try:
                    if 'save_task' in request:
                        from server_code_capture import capture
                        ref=capture(w,request['save_task'])
                    else:ref=self.receive(request['handoff'])
                finally:self.reviewing=False
                if ref is None:self.pending.popleft();self.busy=False;self.timer.start();return
                request.clear();request['reference']=Registry().register(ref)
                self.pending[0]=(request,time.monotonic()+30);self.timer.start()
            reference=Registry().resolve(request['reference'])
            def completed(accepted):
                if self.serial!=serial:return
                self.busy=False
                if accepted is not None:self.pending.popleft()
            w.open_reference(reference,completed)
        except (ValueError,OSError,RuntimeError) as error:
            self.pending.popleft();self.busy=False;self.timer.start()
            QMessageBox.warning(w,w._app_title,str(error))

    def receive(self, token):
        if self.window._binding.app=='projects':
            from server_project_capture import receive
            return receive(self.window,token)
        if self.window._binding.app=='audio':
            from server_audio_capture import receive
            return receive(self.window,token)
        registry=Registry();request=registry.request(token)
        if request['target']!='wissen' or request['action']!='wissen.import':
            raise ValueError(tr('Diese Übergabe gehört nicht zu Lumen Notes.'))
        w=self.window;session=w.session;generation=w._generation
        if w._import_running or not session.usable:raise SessionError('busy')
        def current():
            if (w._disposed or w._closing or w._import_close or w._generation!=generation
                    or w.session is not session or not session.usable or not w._pilot_current()):
                raise SessionError('identity')
        def work(title,function):
            class Guard:
                def __init__(self,job):self.job=job
                def check(self):
                    self.job.check()
                    current()
            return run_job(w,title,lambda job:function(Guard(job)))
        def prepare(job):
            from server_notes_app import context
            config,binding,stamp,revision=context(job)
            if binding!=w._binding or stamp!=w._pilot_connection:raise SessionError('identity')
            if not session.check():raise SessionError(session.state)
            job.check()
            return revision,collections(session,revision,job)
        w._import_running=True
        try:
            prepared=work(tr('Lumen Notes · Sammlungen laden …'),prepare)
            if prepared is None:return None
            revision,rows=prepared
            parent=None
            if request['payload'].get('paths'):
                import threading
                from types import SimpleNamespace
                import server_notes_files as files
                from server_file_import_ui import start_import
                parent=token;gui_thread=threading.get_ident()
                plan=work(tr('Lumen Notes · Dateiauswahl prüfen …'),lambda job:files.begin(parent,session,revision,job))
                if plan is None:return None
                if request['state']!='done':
                    def accepted(*_):
                        if threading.get_ident()!=gui_thread:raise SessionError('thread')
                        current()
                    lease=SimpleNamespace(window=w,binding=session.binding,permissions_revision=revision,
                                          check=current,accept_import=accepted)
                    for child in plan['children']:
                        current()
                        if start_import(w,lease,child['token']) is None:return None
                request=work(tr('Lumen Notes · Notizinhalt vorbereiten …'),lambda job:files.note_request(parent,session,revision,job))
                if request is None:return None
                token=request['id']
            stored=request['choice'];retry=False
            if stored.get('note_capture'):
                choice={key:stored[key] for key in ('id','title','mode','due','token')}
                if stored['note_capture'].get('attempted') and not stored['note_capture'].get('receipt'):
                    if QMessageBox.question(w,'Lumen Notes',tr('Das vorherige Ergebnis ist unklar. '
                            'Dieselbe Übernahme erneut prüfen? Es wird dieselbe Anfrage verwendet.'),
                            QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Yes:return None
                    retry=True
            else:
                from interop_targets import ACTIONS
                spec=dict(ACTIONS['wissen.import'],heading='Als Notiz speichern',
                    description='Eine private Notiz auf deinem verbundenen Server anlegen. Die Quelle bleibt unverändert.')
                preview=request
                if parent:
                    spec.update(modes=['link'],description=tr('Die bestätigten Dateikopien bleiben in Lumen Drive. Eine private Notiz mit Drive-Verweisen und bearbeitbarem Text aus Textdateien speichern. Die Originale bleiben unverändert.'))
                    preview=dict(request,payload={k:v for k,v in request['payload'].items() if k!='references'})
                choice=review(w,preview,spec=spec,rows=rows)
                if choice is None:return None
            result=work(tr('Lumen Notes · Notiz übernehmen …'),lambda job:
                capture(token,choice,session,revision,job,retry=retry))
            if result is None or not parent:return result
            return work(tr('Lumen Notes · Übernahme bestätigen …'),lambda job:files.complete(parent,result,session,revision,job))
        finally:
            w._import_running=False
            if not session.usable:w.block(session.state)
            if w._import_close:w._import_close=False;w.close()
