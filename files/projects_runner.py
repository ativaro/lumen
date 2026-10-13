"""Bounded project runs; the same runner is used by the UI and the user timer."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import shutil
import sqlite3
from PySide6.QtCore import QObject, Signal, QTimer, QCoreApplication
from lumen_i18n import tr
from lumen_jobs import Job
from tools_data import Library, document_text, web_url
from projects_data import Projects


def lease(projects, task):
    # Validate before constructing a lock path from an external reference.
    if len(task)!=32 or any(c not in '0123456789abcdef' for c in task): raise ValueError('Invalid task')
    path=projects.library.root/('run-'+task+'.lock')
    fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError: os.close(fd); raise ValueError(tr('Diese Aufgabe läuft bereits.')) from None
    return fd


def recover(projects):
    with projects.library.connect() as db:
        rows=db.execute("SELECT id,task FROM project_runs WHERE status='running'").fetchall()
    for run in rows:
        try: fd=lease(projects,run['task'])
        except ValueError: continue
        try: projects.finish_run(run['id'],'paused',error=tr('Die Ausführung wurde unterbrochen. Zum Fortsetzen erneut starten.'))
        finally: os.close(fd)


def snapshot(projects, task, job):
    from interop_paths import moves,mapped
    sources=[]; seen=set(); total=0
    for item in projects.source_chain(task):
        job.check()
        if item.get('notes','').strip():
            content=item['notes']; sources.append(dict(title=item['title'],text=content,revision='SHA256 '+hashlib.sha256(content.encode()).hexdigest()))
            total+=len(content)
        changes=moves(projects.library.root.parent,item.get('interop_path_revision',0))
        for resource in item.get('resources',[]):
            job.check(); target=resource['target']
            if resource['kind']=='folder':
                sources.append(dict(title=resource['title'],path=target,text='',revision=tr('Ordnerverweis · Dateien einzeln anheften')))
                continue
            if resource['kind']=='file':target=mapped(target,changes)
            if target in seen:continue
            seen.add(target)
            if resource['kind']=='url':
                sources.append(dict(title=resource['title'],url=web_url(target),revision=tr('Webadresse · Inhalt wird bei Recherche abgerufen')));continue
            if target.startswith('lumen:'):
                from interop_data import Registry
                ref=Registry(projects.library.root.parent).resolve(target)
                if ref['app'] in ('wissen','files') and ref.get('path'):target=ref['path']
                elif ref['app']=='reader':
                    book=Library('reader',projects.library.root.parent); record=book.get(ref['id'])
                    target=str(book.asset(record['asset']))
                else:raise ValueError(tr('Diese Verknüpfung bitte als Text oder Dokument anheften: {0}',resource['title']))
            path=Path(target)
            if not path.is_file():raise ValueError(tr('Datei nicht erreichbar oder Ordner angeheftet: {0}',resource['title']))
            if path.stat().st_size>32*1024**2:raise ValueError(tr('Für diese Aufgabe bitte einen Auszug unter 32 MB anheften.'))
            before=path.stat(); digest=hashlib.sha256()
            with path.open('rb') as stream:
                while chunk:=stream.read(1024*1024):job.check(); digest.update(chunk)
            if path.suffix.lower() in ('.html','.htm'):
                from tools_data import ArticleParser
                parser=ArticleParser(); parser.feed(path.read_text(encoding='utf-8',errors='replace')); content=parser.text()
            elif path.suffix.lower()=='.epub':
                from reader_data import worker
                value=worker(job,'text',path)
                if value.get('locked'):raise ValueError(tr('Bitte das Dokument zuerst in Lumen Reader entsperren.'))
                content=value['text']
            else:content=document_text(path,job)
            after=path.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError(tr('Eine Quelle wurde während des Einlesens geändert. Bitte erneut starten.'))
            total+=len(content)
            sources.append(dict(title=resource['title'],path=str(path),text=content,revision='SHA256 '+digest.hexdigest(),modified=after.st_mtime))
        if total>120000:raise ValueError(tr('Die Quellen sind zu umfangreich. Bitte kürzere Auszüge anheften.'))
    value=projects.get(task)
    return dict(title=value['title'],goal=value.get('goal',''),sources=sources,captured=time.time(),kind=value['kind'],operation=value.get('operation','analysis'),deep=value.get('deep',False))


class Runner(QObject):
    status=Signal(str)
    finished=Signal(bool,str)

    def __init__(self,projects,parent=None,background=False):
        super().__init__(parent); self.projects=projects; self.background=background
        self.busy=False; self.fd=None; self.job=None; self.engine=None; self.run=''; self.cancelled=False; self.phase=0; self.answers=[]

    def start(self,task,expected_updated=None):
        if self.busy:raise ValueError(tr('Bitte den laufenden Vorgang abwarten.'))
        self.phase=0; self.answers=[]; self.stages=[]; self.cancelled=False
        if self.engine:self.engine.deleteLater(); self.engine=None
        self.fd=lease(self.projects,task)
        try:
            for previous in self.projects.runs(task):
                if previous['status']=='running':self.projects.finish_run(previous['id'],'paused',error=tr('Unterbrochene Ausführung'))
            self.run=self.projects.begin_run(task,{},scheduled=self.background,expected_updated=expected_updated)
        except Exception:os.close(self.fd); self.fd=None; raise
        self.busy=True; self.task=task; self.status.emit(tr('Angeheftete Quellen werden gelesen …'))
        self.job=Job(lambda job:snapshot(self.projects,task,job),self)
        self.prepared_value=None; self.prepare_error=''
        self.job.result.connect(lambda value:setattr(self,'prepared_value',value))
        self.job.failed.connect(lambda message:setattr(self,'prepare_error',message))
        self.job.finished.connect(lambda:self.guard(self.prepared)); self.job.start()

    def guard(self,callback,*args):
        try:callback(*args)
        except Exception as error:self.finish(False,str(error))

    def prepared(self):
        self.job.deleteLater(); self.job=None
        if self.cancelled or self.prepare_error:
            self.finish(False,self.prepare_error or tr('Abgebrochen'));return
        self.input=self.prepared_value
        self.research=self.input['kind']=='research' or (self.input['kind']=='automation' and self.input['operation']=='research')
        self.phases=[tr('Recherche'),tr('Gegenprüfung'),tr('Ergebnis')] if self.research and self.input['deep'] else [tr('Recherche') if self.research else tr('Analyse')]
        self.projects.update_run(self.run,snapshot=self.input)
        from assistant_backend import OpenCodeBackend
        self.engine=OpenCodeBackend(self.projects.library.root,self,project_config=False); self.engine.read_only=True; self.engine.background_task=self.background
        self.engine.completed.connect(lambda *args:self.guard(self.completed,*args)); self.engine.requestsChanged.connect(self.requests)
        self.next_phase()

    def next_phase(self):
        if self.cancelled:self.finish(False,tr('Abgebrochen'));return
        web=self.research and (len(self.phases)==1 or self.phase<2)
        self.status.emit(self.phases[self.phase]+' · '+str(self.phase+1)+'/'+str(len(self.phases)))
        instruction=[tr('Untersuche die Aufgabenfrage. Suche Primärquellen im Web, lies sie und vergleiche ihre Aussagen. Nenne Links, Belege und offene Punkte.'),
                     tr('Prüfe die bisherigen Rechercheergebnisse gegen weitere unabhängige Quellen. Suche Widersprüche und Informationslücken.'),
                     tr('Erstelle das gewünschte Endergebnis aus den bisherigen Belegen. Trenne gesicherte Aussagen, Unsicherheiten und Empfehlungen. Gib Quellenlinks an.')]
        prompt=(instruction[min(self.phase,2)] if self.research else tr('Analysiere ausschließlich die angehefteten Inhalte und liefere das gewünschte Ergebnis. Nicht gelesene Webadressen sind keine Belege.'))
        prompt+='\n\n'+tr('Aufgabe')+': '+self.input['title']+'\n'+tr('Gewünschtes Ergebnis')+': '+self.input['goal']
        context=dict(sources=self.input['sources'],previous=self.answers)
        self.engine.send(prompt,agent='plan',title=self.input['title'],context_data=context,project_task=True,web_research=web)

    def requests(self,permissions,questions):
        if permissions or questions:
            # Project runs never silently approve a wider tool scope.
            self.engine.stop(); self.finish(False,tr('Die Ausführung benötigt weitere Angaben oder Berechtigungen. Aufgabe ergänzen und erneut starten.'))

    def completed(self,success,result):
        if not self.busy:return
        if self.cancelled or not success:self.finish(False,result);return
        if self.research and (len(self.phases)==1 or self.phase<2):
            used=any(part.get('type')=='tool' and part.get('tool') in ('webfetch','websearch') and part.get('state',{}).get('status')=='completed' for message in self.engine.messages for part in message.get('parts',[]))
            if not used:self.finish(False,tr('Die Recherche hat keine Webquelle abgerufen. Provider und Websuche prüfen; es wurde kein Rechercheergebnis als abgeschlossen gespeichert.'));return
        if not result.strip():self.finish(False,tr('Die Ausführung hat kein Ergebnis geliefert.'));return
        if len(result)>120000:self.finish(False,tr('Das Ergebnis ist zu umfangreich. Die Aufgabe bitte enger eingrenzen.'));return
        web_sources=[dict(tool=part['tool'],input=part.get('state',{}).get('input',{}),output=part.get('state',{}).get('output','')[:20000]) for message in self.engine.messages for part in message.get('parts',[]) if part.get('type')=='tool' and part.get('tool') in ('webfetch','websearch') and part.get('state',{}).get('status')=='completed']
        self.stages.append(dict(title=self.phases[self.phase],result=result,web_sources=web_sources,finished=time.time()))
        self.projects.update_run(self.run,stages=self.stages)
        self.answers.append(result); self.phase+=1
        if self.phase<len(self.phases):QTimer.singleShot(0,lambda:self.guard(self.next_phase))
        else:self.finish(True,result)

    def finish(self,success,result):
        if not self.busy:return
        status='cancelled' if self.cancelled else 'done' if success else 'failed'
        self.projects.finish_run(self.run,status,result=result if success else '',error='' if success else result)
        self.busy=False
        if self.engine:self.engine.shutdown()
        if self.fd is not None:os.close(self.fd); self.fd=None
        if self.background:
            previous=self.projects.runs(self.task)[1:]
            changed=not previous or previous[0].get('result')!=result or not success
            if changed:
                try:
                    from lumen_notifications import publish
                    from interop_data import Registry
                    task=self.projects.get(self.task)
                    target=Registry(self.projects.library.root.parent).register(dict(app='workbench', kind='record',
                        id=task['project'], title=task['title'], position={'part':'item:'+self.task}))
                    publish('Lumen Projekte', self.run, task['title'],
                        tr('Neues Ergebnis' if success else 'Ausführung fehlgeschlagen'), target=target, attention=not success)
                except (OSError, sqlite3.Error, ValueError):pass
        self.finished.emit(success,result)

    def cancel(self):
        self.cancelled=True
        if self.job:self.job.cancelled.set()
        elif self.engine:self.engine.stop()
        else:self.finish(False,tr('Abgebrochen'))


def install_timer(root):
    directory=Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'systemd/user'; directory.mkdir(parents=True,exist_ok=True)
    paths=[sys.executable,str(Path(__file__).resolve()),str(Path(root).resolve())]
    if any(any(c in p for c in '\n\r%"\\') for p in paths):raise ValueError(tr('Dieser Installationspfad wird vom Zeitplan nicht unterstützt.'))
    unit='lumen-projects-'+hashlib.sha256(paths[2].encode()).hexdigest()[:12]
    (directory/(unit+'.service')).write_text('[Unit]\nDescription=Lumen project tasks\n[Service]\nType=oneshot\nNice=10\nTimeoutStartSec=infinity\nExecStart="'+paths[0]+'" "'+paths[1]+'" --tick --root "'+paths[2]+'"\n',encoding='utf-8')
    (directory/(unit+'.timer')).write_text('[Unit]\nDescription=Lumen project schedules\n[Timer]\nOnBootSec=2min\nOnUnitActiveSec=1min\n[Install]\nWantedBy=timers.target\n',encoding='utf-8')
    for args in (['daemon-reload'],['enable','--now',unit+'.timer']):
        result=subprocess.run(['systemctl','--user',*args],capture_output=True,text=True,timeout=15)
        if result.returncode:raise ValueError(tr('Zeitplan konnte nicht aktiviert werden: {0}',result.stderr[-1500:]))


def main():
    import argparse
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--tick',action='store_true'); mode.add_argument('--task')
    parser.add_argument('--expected-updated'); parser.add_argument('--root'); args=parser.parse_args()
    app=QCoreApplication.instance() or QCoreApplication(sys.argv)
    projects=Projects(Library('workbench',args.root))
    if args.task:
        if not args.expected_updated: parser.error('--task requires --expected-updated')
        runner=Runner(projects)
        runner.finished.connect(lambda *_:QTimer.singleShot(0,app.quit))
        try:
            runner.start(args.task,expected_updated=args.expected_updated)
        except (ValueError,OSError,sqlite3.Error) as error:
            print(json.dumps(dict(error=str(error))),flush=True); return 1
        print(json.dumps(dict(task=args.task,run=runner.run,status='running')),flush=True)
        app.exec(); return 0
    from lumen_tasks import defer_background
    from lumen_store import Store
    if defer_background(Store()):return
    recover(projects)
    queue=[]
    for project in projects.library.all():
        for item in projects.items(project['id']):
            if item['kind'] in ('research','analysis','automation') and item.get('enabled') and item.get('next_run',0)<=time.time():queue.append(item['id'])
    runner=Runner(projects,background=True)
    def advance(*_):
        if not queue:app.quit();return
        task=queue.pop(0)
        try:runner.start(task)
        except ValueError:QTimer.singleShot(0,advance)
    runner.finished.connect(lambda *_:QTimer.singleShot(0,advance)); QTimer.singleShot(0,advance); app.exec()


if __name__=='__main__':sys.exit(main())
