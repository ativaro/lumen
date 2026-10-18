"""Headless execution of approved triggers using the same durable runs and AI contract."""
import json
import os
import time


def run_pending(collection):
    from code_blocks_run import Runs
    from code_triggers import Triggers
    triggers=Triggers(collection);triggers.poll();runs=Runs(collection)
    rows=collection.store.rows("""SELECT id FROM code_block_runs
      WHERE json_extract(data,'$.event.background')=1 AND
      (status='running' OR (status='paused' AND json_extract(data,'$.queued')=1))
      ORDER BY updated LIMIT 20""")
    for row in rows:
        try:fd=collection.store.acquire('block-'+row['id'])
        except BlockingIOError:continue
        try:execute(runs,row['id'])
        finally:os.close(fd)


def execute(runs,identity):
    deadline=time.monotonic()+300
    class Check:
        def check(self):
            if time.monotonic()>deadline:raise ValueError('Zeitbudget erreicht. Durchlauf in Lumen fortsetzen.')
            with runs.store.connect() as db:
                run=runs.get(identity,db);runs.fence(run,db)
                if run['status']!='running':raise ValueError('Durchlauf angehalten.')
    try:
        runs.resume(identity)
        while runs.get(identity)['status']=='running':
            Check().check();request=runs.advance(identity,Check())
            if request:answer(runs,identity,request,Check())
    except (ValueError,OSError,RuntimeError) as error:runs.fail(identity,str(error))


def answer(runs,identity,request,job):
    from PySide6.QtCore import QCoreApplication,QEventLoop,QTimer
    from assistant_backend import OpenCodeBackend
    app=QCoreApplication.instance() or QCoreApplication([])
    loop=QEventLoop();folder=runs.store.directory/'block-background';folder.mkdir(exist_ok=True,mode=0o700)
    backend=OpenCodeBackend(folder,project_config=False);poll=QTimer();poll.setInterval(250)
    outcome=[]
    def completed(success,result):outcome.append((success,result));loop.quit()
    def check():
        try:job.check()
        except (ValueError,OSError) as error:
            outcome.append((False,str(error)));backend.stop();loop.quit()
    backend.completed.connect(completed);poll.timeout.connect(check)
    try:
        poll.start();backend.send(request['prompt'],proposal=True,title='Lumen Automation')
        if not outcome:loop.exec()
        success,result=outcome[0]
        job.check()
        if success:runs.ai_done(identity,result,request['attempt'])
        else:runs.fail(identity,result,request['attempt'])
    finally:poll.stop();backend.shutdown()
