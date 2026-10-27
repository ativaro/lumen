"""Bounded asynchronous notebook context and read-only memory learning."""
from lumen_i18n import tr
from lumen_qt import QObject,QTimer
from lumen_jobs import Job
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from memory_agent import PROMPT
from memory_agent_config import prepare as prepare_engine
from lumen_store import Store
from lumen_memory import worker,options,stamp


class MemoryBridge(QObject):
    def __init__(self,backend):
        super().__init__(backend);self.backend=backend;self.store=Store();self.jobs=set();self.learner=None;self.queue=[];self.closed=False;self.account_events=set()

    def job(self,action,done,failed,**values):
        job=Job(lambda job:worker(job,self.store,action,**values),self);self.jobs.add(job);results=[];errors=[]
        job.result.connect(results.append);job.failed.connect(errors.append)
        def finish():
            self.jobs.discard(job);job.deleteLater()
            if self.closed or job.cancelled.is_set():return
            if errors:failed(errors[-1])
            elif results:done(results[0])
        job.finished.connect(finish);job.start()

    def prepare(self,text,directory,done):
        def ready(result):
            self.backend.memoryStatus.emit(result.get('warning') or (tr('Gedächtnis · {0} passende Quellen',len(result['notes'])) if result['notes'] else tr('Gedächtnis · keine passende Erinnerung')))
            done(result)
        def failed(message):
            self.backend.memoryStatus.emit(tr('Gedächtnis nicht erreichbar · Anfrage läuft ohne zusätzliche Erinnerungen'))
            done(dict(stamp=stamp(self.store),revision=-1,context='',notes=[],candidates=[]))
        self.job('prepare',ready,failed,query=text[:6000],directory=directory)

    def learn(self,text,directory,source,prepared,context=None,event_id=None):
        settings=options(self.store)
        if self.closed or not settings['enabled'] or not settings['learn']:return
        if not isinstance(text,str) or not 1<=len(text.strip())<=6000:return
        if prepared.get('remote'):
            self.learn_account(text,prepared,context or {},event_id);return
        if prepared.get('revision',-1)<0:return
        if len(self.queue)>=4:self.backend.memoryStatus.emit(tr('Gedächtnis ausgelastet · diesen Gedanken bei Bedarf ausdrücklich merken'));return
        self.queue.append(dict(text=text,directory=directory,source=source,prepared=prepared,context=context or {}));self.next()

    def learn_account(self,text,prepared,context,event_id):
        if not event_id or event_id in self.account_events:return
        if len(self.account_events)>=4:
            self.backend.memoryStatus.emit(tr('Gedächtnis ausgelastet · diesen Gedanken bei Bedarf ausdrücklich merken'));return
        self.account_events.add(event_id);started=time.monotonic()
        def failed(_):
            self.account_events.discard(event_id)
            self.backend.memoryStatus.emit(tr('Server-Lernstatus nicht verfügbar · nichts automatisch wiederholt'))
        def ready(result):
            if self.closed:return
            state=result['state']
            if state in ('queued','running'):
                self.backend.memoryStatus.emit(tr('Lumen prüft deine Aussage auf dem Server …'))
                if time.monotonic()-started<60:
                    QTimer.singleShot(2000,lambda:None if self.closed else self.job('account_learning_status',ready,failed,remote=prepared['remote'],task_id=result['task_id']))
                    return
                message=tr('Lernprüfung auf dem Server noch offen · im Server-Gedächtnis überprüfbar')
            elif state=='completed':
                count=result['saved'] or result['pending']
                message=(tr('{0} Erinnerungen auf dem Server gespeichert',count) if result['saved'] else tr('{0} Gedächtnisvorschläge warten im Server-Gedächtnis',count)) if count else tr('Geprüft · keine neue Erinnerung übernommen')
            elif state=='disabled':message=tr('Lernen im Serverkonto ausgeschaltet · nichts übertragen')
            elif state=='local':message=tr('Nur lokales Modell erlaubt · nichts zum Server-Lernen übertragen')
            else:message=tr('Lernfreigabe geändert oder Lernen fehlgeschlagen · nichts automatisch wiederholt')
            self.account_events.discard(event_id);self.backend.memoryStatus.emit(message)
        self.job('learn_account',ready,failed,text=text,prepared=prepared,event_id=event_id,context=context)

    def next(self):
        if self.closed or self.learner or not self.queue:return
        request=self.queue.pop(0);settings=options(self.store)
        if not settings['enabled'] or not settings['learn'] or stamp(self.store)!=request['prepared']['stamp']:self.queue.clear();return
        from assistant_backend import OpenCodeBackend
        temporary=TemporaryDirectory(prefix='lumen-learning-')
        engine=OpenCodeBackend(temporary.name,self,project_config=False)
        engine.learning_temporary=temporary
        self.learner=engine;engine.selected_model=self.backend.selected_model;engine.read_only=True
        candidates=request['prepared']['candidates']
        prompt=PROMPT
        self.backend.memoryStatus.emit(tr('Lumen prüft deine Aussage …'))
        def completed(success,result):
            if self.learner is not engine:return
            self.learner=None;engine.shutdown();engine.deleteLater()
            try:items=json.loads((Path(temporary.name)/'result.json').read_text()) if success else None
            except (OSError,ValueError):items=None
            finally:temporary.cleanup()
            if self.closed:return
            if success:
                if isinstance(items,list) and len(items)<=3:
                    if not items:
                        self.backend.memoryStatus.emit(tr('Geprüft · keine neue Erinnerung übernommen'))
                        QTimer.singleShot(0,self.next);return
                    def saved(count):
                        if count:self.backend.memoryStatus.emit(tr('{0} Gedächtnisvorschläge warten im Lumen-Gedächtnis',count) if not options(self.store)['automatic'] else tr('{0} Erinnerungen gespeichert · im Lumen-Gedächtnis überprüfbar',count))
                        else:self.backend.memoryStatus.emit(tr('Geprüft · keine neue Erinnerung übernommen'))
                        QTimer.singleShot(0,self.next)
                    def failed(_):
                        self.backend.memoryStatus.emit(tr('Lernen zuletzt nicht möglich · nichts automatisch wiederholt'))
                        QTimer.singleShot(0,self.next)
                    self.job('apply',saved,failed,items=items,user_text=request['text'],directory=request['directory'],source=request['source'],candidates=candidates,revision=request['prepared']['revision'],context=request['context'],prepared_stamp=request['prepared']['stamp']);return
            self.backend.memoryStatus.emit(tr('Lernen zuletzt nicht möglich · nichts automatisch wiederholt'))
            QTimer.singleShot(0,self.next)
        engine.completed.connect(completed)
        def configured(config):
            if self.closed or self.learner is not engine:return
            if stamp(self.store)!=request['prepared']['stamp']:engine.fail('Learning consent changed');return
            try:
                model=self.backend.selected_model or self.backend.settings.value('model','') or config.get('model','')
                policy=self.store.setting('modelPolicy',{})
                if policy.get('privacy')=='local':
                    from lumen_models import loopback
                    model=policy.get('local_model','')
                    if not isinstance(model,str) or '/' not in model:
                        raise ValueError('Learning requires a configured local model')
                    provider=config.get('provider',{}).get(model.split('/',1)[0],{})
                    if not loopback(provider.get('options',{}).get('baseURL','')):
                        raise ValueError('Learning requires the configured loopback provider')
                engine.learning_environment=prepare_engine(temporary.name,config,model,
                    dict(text=request['text'],candidates=candidates,context=request['context'],solutions=settings['solutions'],store=str(self.store.directory),stamp=request['prepared']['stamp']))
                engine.selected_model=model
                engine.send(prompt,proposal=True);engine.deadline.start(60000)
            except (OSError,ValueError,TypeError):engine.fail('Learning configuration unavailable')
        engine.deadline.start(60000)
        self.backend.request('GET','/config',callback=configured,error=lambda _:engine.fail('Learning configuration unavailable'))

    def shutdown(self):
        self.closed=True;self.queue.clear()
        if self.learner:
            engine,self.learner=self.learner,None;engine.shutdown();engine.learning_temporary.cleanup();engine.deleteLater()
        for job in list(self.jobs):job.cancelled.set()
        for job in list(self.jobs):job.wait(3000)
