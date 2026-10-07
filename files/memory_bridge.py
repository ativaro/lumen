"""Bounded asynchronous notebook context and read-only memory learning."""
from lumen_i18n import tr
from lumen_qt import QObject,QTimer
from lumen_jobs import Job
from tools_data import parse_answer
from memory_learning import extraction_prompt
from lumen_store import Store
from lumen_memory import worker,options,stamp


class MemoryBridge(QObject):
    def __init__(self,backend):
        super().__init__(backend);self.backend=backend;self.store=Store();self.jobs=set();self.learner=None;self.queue=[];self.closed=False

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

    def learn(self,text,directory,source,prepared,context=None):
        settings=options(self.store)
        if self.closed or not settings['enabled'] or not settings['learn'] or prepared.get('revision',-1)<0:return
        if not isinstance(text,str) or not 1<=len(text.strip())<=6000:return
        if len(self.queue)>=4:self.backend.memoryStatus.emit(tr('Gedächtnis ausgelastet · diesen Gedanken bei Bedarf ausdrücklich merken'));return
        self.queue.append(dict(text=text,directory=directory,source=source,prepared=prepared,context=context or {}));self.next()

    def next(self):
        if self.closed or self.learner or not self.queue:return
        request=self.queue.pop(0);settings=options(self.store)
        if not settings['enabled'] or not settings['learn'] or stamp(self.store)!=request['prepared']['stamp']:self.queue.clear();return
        from assistant_backend import OpenCodeBackend
        engine=OpenCodeBackend(request['directory'],self,server_url=self.backend.url,password=self.backend.password,project_config=False)
        self.learner=engine;engine.selected_model=self.backend.selected_model;engine.read_only=True
        candidates=request['prepared']['candidates']
        prompt=extraction_prompt(request['text'],candidates,request['context'])
        def completed(success,result):
            if self.learner is not engine:return
            self.learner=None;engine.shutdown();engine.deleteLater()
            if self.closed:return
            if success:
                try:items=parse_answer(result)['memories']
                except (ValueError,KeyError,TypeError):items=None
                if items:
                    def saved(count):
                        if count:self.backend.memoryStatus.emit(tr('{0} Erinnerung gespeichert · in Lumen Wissen überprüfbar',count) if count==1 else tr('{0} Erinnerungen gespeichert · in Lumen Wissen überprüfbar',count))
                        QTimer.singleShot(0,self.next)
                    self.job('apply',saved,lambda _:QTimer.singleShot(0,self.next),items=items,user_text=request['text'],directory=request['directory'],source=request['source'],candidates=candidates,revision=request['prepared']['revision'],context=request['context']);return
            QTimer.singleShot(0,self.next)
        engine.completed.connect(completed);engine.send(prompt,proposal=True);engine.deadline.start(60000)

    def shutdown(self):
        self.closed=True;self.queue.clear()
        if self.learner:
            engine,self.learner=self.learner,None;engine.shutdown();engine.deleteLater()
        for job in list(self.jobs):job.cancelled.set()
        for job in list(self.jobs):job.wait(3000)
