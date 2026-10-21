"""Reviewed native Notes handoffs; Server owns the actual notebook and editor."""
from collections import deque
import time

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
            raise ValueError(tr('Die Notizübergabe ist ungültig oder noch nicht abgeschlossen.'))
        key,value=next(iter(request.items()))
        if key=='reference':
            self.window.session.binding.reference_url(Registry().resolve(value))
        elif key!='handoff' or not isinstance(value,str) or not TOKEN.fullmatch(value):
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
            QMessageBox.warning(w,'Lumen Notes',tr('Die Notiz konnte noch nicht geöffnet werden. '
                'Serververbindung prüfen und die Übergabe anschließend erneut öffnen.'))
            return
        if self.busy or not w._loaded or not w._live or not w.session.usable or w._worker is not None:return
        self.busy=True;self.serial+=1;serial=self.serial
        try:
            if 'handoff' in request:
                self.timer.stop();self.reviewing=True
                try:ref=self.receive(request['handoff'])
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
            QMessageBox.warning(w,'Lumen Notes',str(error))

    def receive(self, token):
        registry=Registry();request=registry.request(token)
        if request['target']!='wissen' or request['action']!='wissen.import':
            raise ValueError(tr('Diese Übergabe gehört nicht zu Lumen Notes.'))
        w=self.window;session=w.session;generation=w._generation
        if w._import_running or not session.usable:raise SessionError('busy')
        def work(title,function):
            class Guard:
                def __init__(self,job):self.job=job
                def check(self):
                    self.job.check()
                    if (w._disposed or w._closing or w._import_close or w._generation!=generation
                            or w.session is not session or not session.usable or not w._pilot_current()):
                        raise SessionError('identity')
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
                choice=review(w,request,spec=spec,rows=rows)
                if choice is None:return None
            return work(tr('Lumen Notes · Notiz übernehmen …'),lambda job:
                capture(token,choice,session,revision,job,retry=retry))
        finally:
            w._import_running=False
            if not session.usable:w.block(session.state)
            if w._import_close:w._import_close=False;w.close()
